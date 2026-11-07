#!/usr/bin/env python3
"""Opt-in native Windows Chromium *browser-only* compilation experiment.

Never invoke the inherited Helium installer targets, code signing, updates,
installation or distribution. The output (if any) is a technical prototype.
Arcium's separate Windows identity and first-run integration are applied before GN.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.gn_smoke import RESTORE_ANCHOR, RESTORE_STEP
from scripts.windows_port import ROOT, audit_staged, git
from scripts.windows_sdk_compat import adapt_windows_vcvars, select_windows_sdk
from scripts.chromium_sdk_pin import inject_chromium_sdk_pin
from scripts.windows_release_integrations import (
    RELEASE_INTEGRATIONS_ANCHOR, RELEASE_INTEGRATIONS_STEP,
    inject_release_integrations,
)
from scripts.windows_version_compat import (
    adapt_builder_version_api, assert_arcium_version_api
)


ORIGINAL_RELEASE_TARGETS = (
    "    ninja_commandline.extend(['chrome', 'chromedriver', 'setup', 'mini_installer'])"
)
BROWSER_ONLY_TARGETS = "    ninja_commandline.append('chrome')"
ONBOARDING_ANCHOR = "    # Enter source tree to run build commands\n"
ONBOARDING_STEP = (
    "    # Keep first-run/profile identity separate from installed Helium.\n"
    "    from scripts.apply_windows_arc_workflow import (\n"
    "        ONBOARDING_PATCH, PASSWORD_PATCH, SERVICES_PATCH, PROFILE_KEEP_ALIVE_PATCH, TAB_TOOLS_PATCH, integrate_bundle)\n"
    "    integrate_bundle(source_tree, catalogs=(PASSWORD_PATCH, ONBOARDING_PATCH, SERVICES_PATCH, PROFILE_KEEP_ALIVE_PATCH, TAB_TOOLS_PATCH), apply=True)\n\n"
)


# The pinned upstream builder automatically inserts `cc_wrapper = "sccache"`
# when the sccache executable is on PATH. Require that wrapper when a runner
# opts into cross-run caching to avoid paying for an uncached cold compile.
NINJA_PROGRESS = re.compile(rb"\[(\d+)/(\d+)\]")


def latest_build_progress(log_path: Path) -> tuple[int, int] | None:
    """Read only the log tail; Siso can generate many MB of status output."""
    if not log_path.is_file():
        return None
    with log_path.open("rb") as stream:
        try:
            stream.seek(-131072, os.SEEK_END)
        except OSError:
            stream.seek(0)
        matches = NINJA_PROGRESS.findall(stream.read())
    if not matches:
        return None
    completed, total = matches[-1]
    return int(completed), int(total)


def require_compilation_cache() -> None:
    """Fail early if this build expects a persistent compiler cache."""
    if not shutil.which("sccache"):
        raise EnvironmentError(
            "Missing sccache executable on PATH: install sccache before "
            "running a cache-required native Windows browser build."
        )


def stop_build_tree(process: subprocess.Popen) -> None:
    """Stop the Windows builder and its Siso/clang children on timeout."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    if process.poll() is None:
        process.kill()
    process.wait(timeout=30)


REQUIRED_NATIVE_CHROMIUM_SDK = "10.0.28000.0"


def require_native_chromium_sdk(selected: str) -> None:
    """Prevent an expensive C++ build with a GN-only SDK compatibility path.

    Pinned Chromium 156 explicitly #errors when the 28000 Windows SDK's
    NTDDI_WIN11_BR declaration is absent (base/win/windows_version.cc).
    SDK 26100 can configure GN but cannot compile this native source.
    """
    if selected != REQUIRED_NATIVE_CHROMIUM_SDK:
        raise EnvironmentError(
            f"Chromium 156 native build requires SDK {REQUIRED_NATIVE_CHROMIUM_SDK}, "
            f"not {selected}. Provision it on an authorized disposable Windows "
            "build runner using scripts/provision_chromium_sdk.ps1 -Install "
            "before attempting browser-only compilation."
        )



def print_diagnostic(text: str) -> None:
    """Write compiler diagnostics safely even on Windows cp1252 consoles.

    Siso's log may contain Unicode glyphs outside the current Windows console
    encoding. Preserve the raw UTF-8 log and JSON; escape only console output.
    """
    print(text.encode("ascii", errors="backslashreplace").decode("ascii"),
          flush=True)


def first_compiler_failure(log_path: Path, limit: int = 24) -> list[str]:
    """Extract the first Siso/Ninja FAILED block, not only the log's tail.

    A C++ failure can be followed by thousands of unrelated Siso status
    lines; the last 55 lines alone often hide the real compiler error.
    """
    result: list[str] = []
    with log_path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not result:
                if not line.startswith("FAILED:"):
                    continue
            result.append(line.rstrip("\r\n")[:3500])
            if len(result) >= limit:
                break
    return result


def make_browser_only_builder(upstream: str, *, release_candidate: bool = False) -> str:
    """Convert exact pinned Windows build.py to an ephemeral browser-only builder."""
    if upstream.count(RESTORE_ANCHOR) != 1:
        raise ValueError("Unknown pinned Windows patch-stage entry")
    if upstream.count(ORIGINAL_RELEASE_TARGETS) != 1:
        raise ValueError("Unknown Windows Ninja target list; no installer may run")
    if upstream.count(ONBOARDING_ANCHOR) != 1:
        raise ValueError("Unknown Windows pre-GN onboarding entry")
    if release_candidate and upstream.count(RELEASE_INTEGRATIONS_ANCHOR) != 1:
        raise ValueError("Unknown Windows pre-branding integration entry")
    builder = adapt_builder_version_api(upstream)
    builder = adapt_windows_vcvars(builder)
    builder = inject_chromium_sdk_pin(builder)
    builder = builder.replace(RESTORE_ANCHOR, RESTORE_STEP, 1)
    builder = builder.replace(ORIGINAL_RELEASE_TARGETS, BROWSER_ONLY_TARGETS, 1)
    if release_candidate:
        builder = inject_release_integrations(builder)
    else:
        builder = builder.replace(ONBOARDING_ANCHOR,
                                  ONBOARDING_STEP + ONBOARDING_ANCHOR, 1)
    if "ninja_commandline.extend(['chrome', 'chromedriver', 'setup', 'mini_installer'])" in builder:
        raise AssertionError("Installer command remains in generated builder")
    compile(builder, "arcium_browser_only_builder.py", "exec")
    return builder


def run_experiment(
    platform: Path, report_path: Path, *,
    execute: bool, jobs: int, max_minutes: int, require_cache: bool = False,
    release_candidate: bool = False
) -> int:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = report_path.with_suffix(".log")
    report: dict = {
        "status": "VALIDATING",
        "kind": "EXPERIMENTAL_CHROMIUM_BROWSER_ONLY_BUILD",
        "installer_enabled": False,
        "signing_enabled": False,
        "updater_enabled": False,
        "browser_compiled": False,
        "browser_launched": False,
        "browser_distributed": False,
        "release_candidate_integrations": release_candidate,
        "danger": (
            "Browser-only prototype. The separate Arcium identity is applied "
            "before GN; native isolation and release packaging still need "
            "runtime acceptance."
        ),
    }

    def save() -> None:
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    try:
        if not 1 <= jobs <= 32:
            raise ValueError("Parallel jobs must be between 1 and 32")
        if not 5 <= max_minutes <= 310:
            raise ValueError("max_minutes must be between 5 and 310")
        audit = audit_staged(platform)
        assert_arcium_version_api(
            platform / "helium-chromium" / "utils" / "helium_version.py"
        )
        script = make_browser_only_builder(
            (platform / "build.py").read_text(encoding="utf-8"),
            release_candidate=release_candidate,
        )
        report.update({
            "status": "VALIDATED",
            "chromium_version": audit["chromium_version"],
            "arcium_commit": audit["arcium_commit"],
            "windows_platform_commit": audit["platform_commit"],
            "source_patches": audit["shared_patch_count"],
            "windows_patches": audit["windows_patch_count"],
            "compilation_jobs": jobs,
            "integration_commit": git("-C", ROOT, "rev-parse", "HEAD"),
        })
        save()
        if not execute:
            print("Browser-only adapter valid. No Chromium source downloaded, GN or Ninja run.")
            return 0

        if os.environ.get("WINSPARKLE_ED_KEY") or os.environ.get(
            "WINSPARKLE_AUTHENTICODE_ORG"
        ):
            raise EnvironmentError("Signing/updater configuration is forbidden in prototype")
        if (platform / "build" / "src" / "BUILD.gn").exists():
            raise FileExistsError(
                "Build workspace already contains Chromium. Refusing to "
                "apply pinned patches a second time."
            )
        temp_script = platform / "arcium_browser_only_builder.py"
        if temp_script.exists():
            raise FileExistsError("Refusing to reuse an existing browser builder")
        free = shutil.disk_usage(platform).free / (1024 ** 3)
        report["initial_free_disk_gib"] = round(free, 2)
        if free < 105:
            raise RuntimeError("Need >=105 GiB free for initial native Chromium build attempt")
        # Fail before creating an experimental builder or downloading a
        # full Chromium archive if only SDK 26100 is installed. GN alone can
        # pass on that older SDK; native Chromium 156 compilation cannot.
        selected_sdk = select_windows_sdk()
        require_native_chromium_sdk(selected_sdk)
        if require_cache:
            require_compilation_cache()
        report["compiler_cache_required"] = require_cache
        report["compiler_cache_available"] = bool(shutil.which("sccache"))
        temp_script.write_text(script, encoding="utf-8")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT) + os.pathsep + environment.get(
            "PYTHONPATH", ""
        )
        environment["PYTHONUNBUFFERED"] = "1"
        # Force a fully installed x64 SDK instead of incomplete runner defaults.
        report["windows_sdk_version"] = selected_sdk
        environment["ARCIUM_WINDOWS_SDK"] = selected_sdk
        environment.pop("WINSPARKLE_ED_KEY", None)
        environment.pop("WINSPARKLE_AUTHENTICODE_ORG", None)
        started = time.monotonic()
        report["status"] = "BUILDING"
        report["browser_build_attempted"] = True
        save()
        command = [
            sys.executable, str(temp_script), "--tarball", "-j", str(jobs)
        ]
        with log_path.open("wb") as log:
            proc = subprocess.Popen(
                command, cwd=platform, env=environment,
                stdout=log, stderr=subprocess.STDOUT
            )
            while True:
                try:
                    code = proc.wait(timeout=30)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = (time.monotonic() - started) / 60
                    remaining = shutil.disk_usage(platform).free / (1024 ** 3)
                    progress = latest_build_progress(log_path)
                    if progress:
                        report["last_completed_build_steps"] = progress[0]
                        report["last_reported_build_steps"] = progress[1]
                        progress_label = (
                            f"; Ninja/Siso {progress[0]:,}/{progress[1]:,} steps"
                        )
                    else:
                        progress_label = "; preparing Chromium/GN"
                    print(
                        f"Native Chromium experiment: {elapsed:.1f} min elapsed; "
                        f"{remaining:.1f} GiB free{progress_label}", flush=True
                    )
                    if elapsed > max_minutes:
                        stop_build_tree(proc)
                        report["status"] = "TIMEOUT"
                        report["elapsed_minutes"] = round(elapsed, 2)
                        report["remaining_disk_gib"] = round(remaining, 2)
                        report["timeout_reason"] = (
                            "Reached configured native compilation time limit; "
                            "no compiler error necessarily occurred."
                        )
                        save()
                        return 124
        report["exit_code"] = code
        report["elapsed_minutes"] = round(
            (time.monotonic() - started) / 60, 2
        )
        report["remaining_disk_gib"] = round(
            shutil.disk_usage(platform).free / (1024 ** 3), 2
        )
        with log_path.open("rb") as log:
            try:
                log.seek(-25000, os.SEEK_END)
            except OSError:
                log.seek(0)
            tail = log.read().decode(
                "utf-8", errors="replace"
            ).splitlines()[-55:]
        print_diagnostic("\n".join(tail[-30:]))
        if code != 0:
            first_failure = first_compiler_failure(log_path)
            if first_failure:
                report["first_compiler_failure"] = first_failure
                print_diagnostic("First actual compiler error:\n" +
                                 "\n".join(first_failure))
        browser = platform / "build" / "src" / "out" / "Default" / "chrome.exe"
        if code == 0 and browser.is_file():
            report["status"] = "BROWSER_BINARY_CREATED_NOT_LAUNCHED"
            report["browser_compiled"] = True
            report["browser_binary_bytes"] = browser.stat().st_size
            save()
            print("Browser target built; not launched, installed or distributed.")
            return 0
        report["status"] = "FAILED_OR_BINARY_MISSING"
        report["log_tail"] = tail
        save()
        return code or 2
    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = f"{type(exc).__name__}: {exc}"
        save()
        print(report["error"], file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform-dir", type=Path,
        default=ROOT / "work" / "windows-platform"
    )
    parser.add_argument(
        "--report", type=Path,
        default=ROOT / "work" / "browser-only-build.json"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate", action="store_true")
    group.add_argument("--execute", action="store_true")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--max-minutes", type=int, default=250)
    parser.add_argument(
        "--require-cache", action="store_true",
        help="Require sccache on PATH before downloading/building Chromium"
    )
    parser.add_argument(
        "--release-candidate", action="store_true",
        help="Apply all reviewed Windows catalogs and optional Mac buttons before branding"
    )
    args = parser.parse_args()
    return run_experiment(
        args.platform_dir.resolve(), args.report.resolve(),
        execute=args.execute, jobs=args.jobs, max_minutes=args.max_minutes,
        require_cache=args.require_cache, release_candidate=args.release_candidate,
    )


if __name__ == "__main__":
    raise SystemExit(main())
