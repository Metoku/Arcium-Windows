#!/usr/bin/env python3
"""Prepare complete Windows Chromium sources and apply all pinned patch series.

This adapter creates a temporary copy of Helium-Windows build.py modified ONLY
to exit after both full patch stacks have returned successfully. It does not
run GN, Ninja, any browser executable, signing, packaging, or updates.

The large download and extraction happen only when --execute is explicitly
passed; --validate is a fast, network-free structural check.
"""

from __future__ import annotations

import argparse
from collections import deque
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

# Support both "python scripts/prepare_full_chromium.py" and "python -m ..." usage.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.windows_port import ROOT, audit_staged, read_series


ANCHOR = (
    "        else:\n"
    "            print(\"Apply patches using quilt, then press Enter\")\n"
    "            input()\n"
)
INSERTION = (
    "            # Arcium-Windows: all upstream shared patches AND Windows\n"
    "            # patches have been applied if control reached this point.\n"
    "            (_ROOT_DIR / 'ARCIUM_PATCHES_APPLIED.marker').write_text(\n"
    "                'ALL_PINNED_PATCHES_APPLIED\\n', encoding='utf-8')\n"
    "            print('ARCIUM_WINDOWS_FULL_PATCH_APPLICATION_PASSED', flush=True)\n"
    "            return\n"
)
VERSION_MARKER = "Helium build script for Windows"
RESTORE_ANCHOR = (
    "        if not args.dev:\n"
    "            # Apply patches\n"
)
RESTORE_STEP = (
    "        if not args.dev:\n"
    "            # Restore exact Chromium WebUI test fixtures omitted by base tarballs.\n"
    "            from scripts.restore_chromium_fixtures import restore_chromium_test_fixtures\n"
    "            restore_chromium_test_fixtures(source_tree)\n"
    "            from scripts.restore_patch_webui_tests import restore_missing_webui_patch_targets\n"
    "            restore_missing_webui_patch_targets(\n"
    "                source_tree, _ROOT_DIR / 'helium-chromium' / 'patches')\n"
    "            # Apply patches\n"
)



def generate_prepare_only_script(upstream_text: str) -> str:
    """Fail closed if the reviewed upstream source layout ever changes."""
    if VERSION_MARKER not in upstream_text:
        raise ValueError("Unexpected upstream build script identity")
    if upstream_text.count(ANCHOR) != 1:
        raise ValueError("Expected exactly one upstream patch-stage exit anchor")
    if upstream_text.count("patches.generate_patches_from_series") < 2:
        raise ValueError("Upstream no longer appears to use both patch series")
    if upstream_text.count(RESTORE_ANCHOR) != 1:
        raise ValueError("Expected exactly one upstream Chromium patch-start anchor")
    position = upstream_text.index(ANCHOR)
    prefix = upstream_text[:position]
    if not prefix.rstrip().endswith(")"):
        raise ValueError("Unexpected code immediately before patch-stage exit")
    generated = prefix + INSERTION + upstream_text[position:]
    generated = generated.replace(RESTORE_ANCHOR, RESTORE_STEP, 1)
    compile(generated, "arcium_prepare_only.py", "exec")
    return generated


def create_report_path(report: Path) -> None:
    report.parent.mkdir(parents=True, exist_ok=True)


def prepare(platform: Path, report: Path, *, execute: bool,
            max_minutes: int = 65) -> int:
    create_report_path(report)
    log = report.with_suffix(".log")
    marker = platform / "ARCIUM_PATCHES_APPLIED.marker"
    result: dict = {
        "status": "NOT_STARTED",
        "kind": "FULL_CHROMIUM_PATCH_APPLICATION",
        "full_source_download_attempted": False,
        "shared_patch_application_verified": False,
        "windows_patch_application_verified": False,
        "gn_generated": False,
        "browser_compiled": False,
        "browser_launched": False,
        "notes": (
            "Full source preparation is not proof of build or Windows UI compatibility."
        ),
    }

    def persist() -> None:
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    try:
        if max_minutes < 1 or max_minutes > 150:
            raise ValueError("max_minutes must be between 1 and 150")
        audit = audit_staged(platform)
        result.update({
            "platform_sha": audit["platform_commit"],
            "core_sha": audit["arcium_commit"],
            "chromium_version": audit["chromium_version"],
            "expected_shared_patches": audit["shared_patch_count"],
            "expected_windows_patches": audit["windows_patch_count"],
        })
        core = platform / "helium-chromium"
        core_patches = read_series(core / "patches" / "series")
        win_patches = read_series(platform / "patches" / "series")
        if len(core_patches) < 100 or len(win_patches) < 20:
            raise ValueError("Suspiciously short patch lists")
        original = (platform / "build.py").read_text(encoding="utf-8")
        temporary_script = generate_prepare_only_script(original)
        result["status"] = "VALIDATED"
        persist()
        if not execute:
            print(
                f"Validated source-preparation insertion point; "
                f"{len(core_patches)} core patches + {len(win_patches)} Windows patches."
            )
            print("No Chromium source was downloaded or patched (--validate only).")
            return 0

        if marker.exists():
            raise FileExistsError(
                "A previous successful patch marker exists; "
                "remove the entire throwaway build workspace to rerun safely."
            )
        if (platform / "build" / "src" / "BUILD.gn").exists():
            raise FileExistsError("A Chromium source tree is already present; "
                                  "refusing to apply patches twice.")

        free_gib = shutil.disk_usage(platform).free / (1024 ** 3)
        result["available_gib_at_start"] = round(free_gib, 2)
        if free_gib < 95:
            raise RuntimeError(
                f"Only {free_gib:.1f} GiB free; require >=95 GiB "
                "before attempting full Chromium source extraction."
            )
        temp_path = platform / "arcium_prepare_only.py"
        if temp_path.exists():
            raise FileExistsError("Refusing to overwrite previous generated adapter")
        temp_path.write_text(temporary_script, encoding="utf-8")
        result["status"] = "PREPARING"
        result["full_source_download_attempted"] = True
        result["log_path"] = str(log)
        result["timeout_minutes"] = max_minutes
        persist()
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        # The temporary Windows-platform builder imports our verified
        # Chromium source fixture helper before applying Arcium patches.
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        command = [sys.executable, str(temp_path), "--tarball"]
        print(
            "Preparing full pinned Chromium source and applying BOTH patch series. "
            "This can download many gigabytes; the log is saved locally.",
            flush=True
        )
        start = time.monotonic()
        tail: deque[str] = deque(maxlen=100)
        with log.open("wb") as handle:
            process = subprocess.Popen(
                command, cwd=platform, env=env, stdout=handle,
                stderr=subprocess.STDOUT
            )
            while True:
                try:
                    exit_code = process.wait(timeout=25)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = (time.monotonic() - start) / 60
                    size_mib = log.stat().st_size / (1024 ** 2)
                    remaining_gib = shutil.disk_usage(platform).free / (1024 ** 3)
                    print(
                        f"Full-source preparation: {elapsed:.1f} min; "
                        f"log {size_mib:.1f} MiB; free disk {remaining_gib:.1f} GiB",
                        flush=True
                    )
                    if elapsed > max_minutes:
                        process.kill()
                        process.wait(timeout=30)
                        result["status"] = "TIMEOUT"
                        result["exit_code"] = None
                        persist()
                        return 124

        result["exit_code"] = exit_code
        result["elapsed_seconds"] = round(time.monotonic() - start, 2)
        result["free_gib_at_end"] = round(
            shutil.disk_usage(platform).free / (1024 ** 3), 2
        )

        # Tail is bounded to prevent leaking massive download logs to Actions UI.
        with log.open("rb") as handle:
            try:
                handle.seek(-25000, os.SEEK_END)
            except OSError:
                handle.seek(0)
            tail_lines = handle.read().decode(
                "utf-8", errors="replace"
            ).splitlines()[-80:]
        print("\n".join(tail_lines[-45:]), flush=True)
        success = (
            exit_code == 0 and marker.is_file() and
            marker.read_text(encoding="utf-8") == "ALL_PINNED_PATCHES_APPLIED\n"
        )
        if success:
            result["status"] = "ALL_PINNED_PATCHES_APPLIED"
            result["shared_patch_application_verified"] = True
            result["windows_patch_application_verified"] = True
            persist()
            print("Confirmed: both FULL patch stacks applied to Chromium source.")
            print("GN generation and native compilation have NOT run.")
            return 0
        result["status"] = "FAILED"
        result["log_tail"] = tail_lines[-45:]
        persist()
        print(
            "Source preparation failed or completion marker missing. "
            "Inspect the saved log artifact for the first error.",
            file=sys.stderr
        )
        return exit_code if exit_code else 2
    except Exception as error:
        result["status"] = "ERROR"
        result["error"] = f"{type(error).__name__}: {error}"
        persist()
        print(result["error"], file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform-dir", type=Path, default=ROOT / "work" / "windows-platform"
    )
    parser.add_argument(
        "--report", type=Path, default=ROOT / "work" / "full-source-prepare.json"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate", action="store_true",
                       help="Verify source layout and patch configuration; no downloads")
    group.add_argument("--execute", action="store_true",
                       help="Download full Chromium source and apply all patch series")
    parser.add_argument("--max-minutes", type=int, default=65)
    args = parser.parse_args()
    return prepare(
        args.platform_dir.resolve(), args.report.resolve(),
        execute=args.execute, max_minutes=args.max_minutes
    )


if __name__ == "__main__":
    raise SystemExit(main())
