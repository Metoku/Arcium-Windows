#!/usr/bin/env python3
"""Run pinned Helium-Windows preparation through GN generation, without Ninja.

This is a separate *manual* experiment from the lightweight PR source checks.
It downloads complete Chromium source when explicitly executed. Any error is
recorded; it never launches, packages, signs, or publishes a browser.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

# Support both module and direct-script invocation on Windows CI.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.windows_port import ROOT, audit_staged
from scripts.windows_version_compat import adapt_builder_version_api, assert_arcium_version_api


GN_ANCHOR = (
    "    # Ninja commandline\n"
    "    os.environ.setdefault('SISO_PATH',"
)
GN_EXIT = (
    "    # Arcium-Windows GN-only validation gate. Ninja must NEVER run.\n"
    "    gn_output = source_tree / 'out' / 'Default' / 'build.ninja'\n"
    "    if not gn_output.is_file():\n"
    "        raise RuntimeError('GN did not create out/Default/build.ninja')\n"
    "    (_ROOT_DIR / 'ARCIUM_GN_GENERATED.marker').write_text(\n"
    "        'PINNED_WINDOWS_GN_GENERATED\\n', encoding='utf-8')\n"
    "    print('ARCIUM_WINDOWS_GN_GENERATION_PASSED', flush=True)\n"
    "    return\n\n"
)
BUILDER_IDENTIFIER = "Helium build script for Windows"
RESTORE_ANCHOR = (
    "        if not args.dev:\n"
    "            # Apply patches\n"
)
RESTORE_STEP = (
    "        if not args.dev:\n"
    "            # Restore test files omitted from prepared Chromium tarballs.\n"
    "            from scripts.restore_chromium_fixtures import restore_chromium_test_fixtures\n"
    "            restore_chromium_test_fixtures(source_tree)\n"
    "            from scripts.restore_patch_webui_tests import restore_missing_webui_patch_targets\n"
    "            restore_missing_webui_patch_targets(\n"
    "                source_tree, _ROOT_DIR / 'helium-chromium' / 'patches')\n"
    "            # Apply patches\n"
)



def create_gn_only_builder(upstream: str) -> str:
    """Fail closed if the pinned upstream script structure changes."""
    if BUILDER_IDENTIFIER not in upstream:
        raise ValueError("Unexpected Windows builder identity")
    if upstream.count(GN_ANCHOR) != 1:
        raise ValueError("Expected one GN/Ninja gate in pinned builder")
    if "gn.exe" not in upstream or "gen" not in upstream:
        raise ValueError("Upstream GN invocation not found")
    if "patches.generate_patches_from_series" not in upstream:
        raise ValueError("Upstream patch stage missing")
    if upstream.count(RESTORE_ANCHOR) != 1:
        raise ValueError("Expected one Chromium patch-stage entry")
    # Never skip failing Arcium patches. Fetch the exact unmodified
    # Chromium test files omitted by the prepared tarball before patching.
    candidate = adapt_builder_version_api(upstream)
    candidate = candidate.replace(RESTORE_ANCHOR, RESTORE_STEP, 1)
    candidate = candidate.replace(GN_ANCHOR, GN_EXIT + GN_ANCHOR, 1)
    compile(candidate, "arcium_gn_only.py", "exec")
    return candidate


def run_gn(platform: Path, report_path: Path, *, execute: bool, max_minutes: int) -> int:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = report_path.with_suffix(".log")
    status = {
        "status": "VALIDATING",
        "kind": "GN_GENERATION_ONLY",
        "source_download_attempted": False,
        "full_patch_application_verified": False,
        "gn_generation_verified": False,
        "native_compile_attempted": False,
        "browser_launch_attempted": False,
        "note": "GN success does not imply Chromium compilation or runtime support.",
    }

    def save() -> None:
        report_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    try:
        if not 1 <= max_minutes <= 160:
            raise ValueError("max_minutes must be between 1 and 160")
        audit = audit_staged(platform)
        status.update({
            "chromium_version": audit["chromium_version"],
            "core_commit": audit["arcium_commit"],
            "platform_commit": audit["platform_commit"],
            "expected_core_patches": audit["shared_patch_count"],
            "expected_windows_patches": audit["windows_patch_count"],
        })
        assert_arcium_version_api(
            platform / "helium-chromium" / "utils" / "helium_version.py"
        )
        builder = create_gn_only_builder(
            (platform / "build.py").read_text(encoding="utf-8")
        )
        status["status"] = "VALIDATED"
        save()
        if not execute:
            print("Pinned GN adapter validated; no downloads, compilation, or GN run.")
            return 0

        fixture_helper = ROOT / "scripts" / "restore_chromium_fixtures.py"
        if not fixture_helper.is_file():
            raise FileNotFoundError(
                "Pinned Chromium fixture helper is not merged yet; "
                "merge the independently verified full-source PR first."
            )
        additional_helper = ROOT / "scripts" / "restore_patch_webui_tests.py"
        if not additional_helper.is_file():
            raise FileNotFoundError(
                "Missing dynamic WebUI restore helper; merge PR #7 first."
            )
        marker = platform / "ARCIUM_GN_GENERATED.marker"
        generated = platform / "arcium_gn_only.py"
        if marker.exists() or generated.exists():
            raise FileExistsError("Refusing to reuse or overwrite GN experiment")
        if (platform / "build" / "src" / "BUILD.gn").exists():
            raise FileExistsError(
                "A Chromium source is already present: this GN experiment "
                "requires a fresh source tree so it cannot reapply patches."
            )
        free_gib = shutil.disk_usage(platform).free / (1024 ** 3)
        status["initial_free_disk_gib"] = round(free_gib, 2)
        if free_gib < 95:
            raise RuntimeError("At least 95 GiB free disk required for source extraction")
        generated.write_text(builder, encoding="utf-8")
        status.update({
            "status": "RUNNING",
            "source_download_attempted": True,
            "diagnostic_log": str(log_path),
        })
        save()
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        begin = time.monotonic()
        print("Running complete source preparation, both patch series and GN gen.",
              flush=True)
        with log_path.open("wb") as stream:
            process = subprocess.Popen(
                [sys.executable, str(generated), "--tarball"],
                cwd=platform, env=env, stdout=stream,
                stderr=subprocess.STDOUT
            )
            while True:
                try:
                    exit_code = process.wait(timeout=25)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = (time.monotonic() - begin) / 60
                    remaining = shutil.disk_usage(platform).free / (1024 ** 3)
                    print(
                        f"GN prep: {elapsed:.1f} minutes elapsed, "
                        f"{remaining:.1f} GiB remaining",
                        flush=True
                    )
                    if elapsed > max_minutes:
                        process.kill()
                        process.wait(timeout=30)
                        status["status"] = "TIMEOUT"
                        status["elapsed_minutes"] = round(elapsed, 2)
                        save()
                        return 124

        with log_path.open("rb") as stream:
            try:
                stream.seek(-30000, os.SEEK_END)
            except OSError:
                stream.seek(0)
            tail = stream.read().decode("utf-8", errors="replace").splitlines()[-70:]
        print("\n".join(tail[-40:]), flush=True)
        gn_ninja = platform / "build" / "src" / "out" / "Default" / "build.ninja"
        passed = (
            exit_code == 0 and gn_ninja.is_file() and marker.is_file() and
            marker.read_text(encoding="utf-8") == "PINNED_WINDOWS_GN_GENERATED\n"
        )
        status["elapsed_seconds"] = round(time.monotonic() - begin, 2)
        status["exit_code"] = exit_code
        status["final_free_disk_gib"] = round(
            shutil.disk_usage(platform).free / (1024 ** 3), 2
        )
        if passed:
            status["status"] = "GN_GENERATED"
            status["full_patch_application_verified"] = True
            status["gn_generation_verified"] = True
            save()
            print("GN generation passed after full source preparation.")
            print("Ninja compilation and browser launch were NOT attempted.")
            return 0
        status["status"] = "FAILED"
        status["log_tail"] = tail[-40:]
        save()
        return exit_code or 2
    except Exception as error:
        status["status"] = "ERROR"
        status["error"] = f"{type(error).__name__}: {error}"
        save()
        print(status["error"], file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform-dir", type=Path,
                        default=ROOT / "work" / "windows-platform")
    parser.add_argument("--report", type=Path,
                        default=ROOT / "work" / "gn-generation.json")
    args = parser.add_mutually_exclusive_group(required=True)
    args.add_argument("--validate", action="store_true",
                      help="Validate adapter on pinned source, no downloads")
    args.add_argument("--execute", action="store_true",
                      help="Full source download, patching, GN generation")
    parser.add_argument("--max-minutes", type=int, default=65)
    options = parser.parse_args()
    return run_gn(
        options.platform_dir.resolve(), options.report.resolve(),
        execute=options.execute, max_minutes=options.max_minutes
    )


if __name__ == "__main__":
    raise SystemExit(main())
