#!/usr/bin/env python3
"""Opt-in isolated headless launch check for a locally compiled Arcium browser.

This never installs, registers, signs, updates or distributes a browser.
It does NOT establish Arc-style UI correctness, packaging safety or identity.
Requires an existing chrome.exe from a prior separate browser-only build.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from scripts.windows_port import ROOT


DEFAULT_BROWSER = (
    ROOT / "work" / "windows-platform" / "build" / "src" /
    "out" / "Default" / "chrome.exe"
)


def smoke_command(browser: Path, profile: Path) -> list[str]:
    """No inherited browser profiles, normal desktop navigation, or installer."""
    return [
        str(browser),
        "--headless=new",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-sync",
        "--no-proxy-server",
        "--user-data-dir=" + str(profile),
        "--dump-dom",
        "about:blank",
    ]


def run_smoke(browser: Path, report: Path, *, timeout: int = 45) -> int:
    report.parent.mkdir(parents=True, exist_ok=True)
    result: dict = {
        "kind": "ISOLATED_WINDOWS_BROWSER_HEADLESS_LAUNCH",
        "status": "VALIDATING",
        "browser_launch_attempted": False,
        "browser_launched": False,
        "installer_executed": False,
        "updater_executed": False,
        "browser_distributed": False,
        "test_url": "about:blank",
        "note": "Headless launch alone does not verify Windows/Arc UI or app identity.",
    }

    def save() -> None:
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    try:
        if not 5 <= timeout <= 120:
            raise ValueError("Headless smoke timeout must be between 5 and 120 seconds")
        if sys.platform != "win32":
            raise OSError("This test runs only on an actual Windows host")
        browser = browser.resolve(strict=True)
        if not browser.is_file() or browser.name.lower() != "chrome.exe":
            raise ValueError("Expected an existing compiled chrome.exe")
        # Avoid passing browser arguments from an external source.
        with tempfile.TemporaryDirectory(
            prefix="arcium-browser-smoke-", ignore_cleanup_errors=True
        ) as directory:
            profile = Path(directory) / "test-profile"
            profile.mkdir()
            command = smoke_command(browser, profile)
            result["status"] = "LAUNCHING"
            result["browser_launch_attempted"] = True
            save()
            proc = subprocess.run(
                command, capture_output=True, text=True,
                timeout=timeout, check=False,
                errors="replace",
            )
            result["exit_code"] = proc.returncode
            result["stdout_has_html"] = "<html" in proc.stdout.lower()
            result["stderr_tail"] = proc.stderr[-2000:]
            result["browser_launched"] = (
                proc.returncode == 0 and result["stdout_has_html"]
            )
        result["isolated_profile_deleted"] = not profile.exists()
        result["status"] = (
            "HEADLESS_LAUNCH_PASSED"
            if result["browser_launched"] and result["isolated_profile_deleted"]
            else "FAILED"
        )
        save()
        return 0 if result["status"] == "HEADLESS_LAUNCH_PASSED" else 2
    except (Exception, subprocess.TimeoutExpired) as exc:
        result["status"] = "ERROR"
        result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        save()
        print(result["error"], file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, default=DEFAULT_BROWSER)
    parser.add_argument(
        "--report", type=Path, default=ROOT / "work" / "browser-launch-smoke.json"
    )
    parser.add_argument("--timeout", type=int, default=45)
    arguments = parser.parse_args()
    return run_smoke(
        arguments.browser, arguments.report, timeout=arguments.timeout
    )


if __name__ == "__main__":
    raise SystemExit(main())
