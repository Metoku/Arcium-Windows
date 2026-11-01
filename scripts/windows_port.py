#!/usr/bin/env python3
"""Stage Helium's Windows build machinery with an exact Arcium core revision.

IMPORTANT: Staging and static auditing DO NOT compile or validate the browser.
The resulting platform checkout is an experimental build workspace only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PIN_DIR = ROOT / "upstream"
ARCIUM_URL = "https://github.com/dr-baker/Arcium.git"
HELIUM_WINDOWS_URL = "https://github.com/imputnet/helium-windows.git"
WINDOWS_PLATFORM_TAG = "0.20.1.1"


def read_pin(name: str) -> str:
    value = (PIN_DIR / name).read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[a-f0-9]{40}", value):
        raise ValueError(f"Invalid 40-character Git commit SHA in {name}")
    return value


def chromium_version() -> str:
    version = (PIN_DIR / "chromium-version.txt").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version):
        raise ValueError("Invalid pinned Chromium version")
    return version


def git(*args: object) -> str:
    completed = subprocess.run(
        ["git", *(str(a) for a in args)],
        text=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return completed.stdout.strip()


def clone_pinned(url: str, revision: str, target: Path, branch: str = "main") -> None:
    """Fetch an explicit revision, without initializing unrelated submodules."""
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Refusing to overwrite existing checkout: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    git("clone", "--depth=1", "--filter=blob:none", "--no-checkout",
        "--branch", branch, url, target)
    current = git("-C", target, "rev-parse", "HEAD")
    if current != revision:
        # The pinned revision can be older than the current branch tip.
        git("-C", target, "fetch", "--depth=1", "origin", revision)
    git("-C", target, "checkout", "--detach", revision)
    actual = git("-C", target, "rev-parse", "HEAD")
    if actual != revision:
        raise RuntimeError(f"Checkout mismatch at {target}: {actual} != {revision}")


def read_series(series_file: Path) -> list[Path]:
    """Resolve and verify every patch referenced by a platform or core series."""
    if not series_file.is_file():
        raise FileNotFoundError(f"Missing patch series: {series_file}")
    patches: list[Path] = []
    for line_no, line in enumerate(series_file.read_text(encoding="utf-8").splitlines(), 1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        # Quilt series can append options. They are unsupported for now; fail closed.
        if any(char.isspace() for char in entry):
            raise ValueError(f"Unexpected patch series options at {series_file}:{line_no}")
        candidate = series_file.parent / entry
        if not candidate.is_file():
            raise FileNotFoundError(f"Missing series patch {candidate}")
        patches.append(candidate)
    if not patches:
        raise ValueError(f"Empty patch series: {series_file}")
    return patches


def patch_targets(content: str) -> set[str]:
    """Find patched Chromium paths in git and quilt-style unified diffs."""
    results: set[str] = set()
    for line in content.splitlines():
        # Paths in the shared Arcium series are often prefixed with src/.
        match = re.match(r"^(?:Index: |--- a/|diff --git a/)(\S+)", line)
        if not match:
            continue
        path = match.group(1)
        if path.startswith("src/"):
            path = path[4:]
        if path.startswith("src.orig/"):
            path = path[9:]
        if path and path != "/dev/null":
            results.add(path)
    return results


def audit_staged(platform: Path) -> dict:
    core = platform / "helium-chromium"
    expected_platform = read_pin("helium-windows.sha")
    expected_core = read_pin("arcium-core.sha")
    if git("-C", platform, "rev-parse", "HEAD") != expected_platform:
        raise ValueError("Helium Windows staging commit does not match pin")
    if git("-C", core, "rev-parse", "HEAD") != expected_core:
        raise ValueError("Arcium core staging commit does not match pin")

    actual_chromium = (core / "chromium_version.txt").read_text(
        encoding="utf-8").strip()
    expected_chromium = chromium_version()
    if actual_chromium != expected_chromium:
        raise ValueError(
            f"Chromium mismatch: Arcium {actual_chromium}, "
            f"expected compatible Windows baseline {expected_chromium}"
        )

    required = [
        platform / "build.py",
        platform / "flags.windows.gn",
        platform / "downloads.x64.ini",
        core / "utils" / "patches.py",
        core / "utils" / "downloads.py",
        core / "flags.gn",
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"Required build input missing: {path}")

    core_patches = read_series(core / "patches" / "series")
    win_patches = read_series(platform / "patches" / "series")
    core_targets: set[str] = set()
    win_targets: set[str] = set()
    mac_only_hints: set[str] = set()

    for patch in core_patches:
        contents = patch.read_text(encoding="utf-8", errors="replace")
        core_targets.update(patch_targets(contents))
        if "BUILDFLAG(IS_MAC)" in contents or re.search(r"\.mm(?:\s|$)", contents, re.M):
            mac_only_hints.add(patch.relative_to(core / "patches").as_posix())
    for patch in win_patches:
        win_targets.update(patch_targets(
            patch.read_text(encoding="utf-8", errors="replace")))

    overlap = sorted(core_targets & win_targets)
    return {
        "status": "STATIC_SOURCE_AUDIT_ONLY",
        "platform": "imputnet/helium-windows",
        "platform_commit": expected_platform,
        "arcium_core": "dr-baker/Arcium",
        "arcium_commit": expected_core,
        "chromium_version": actual_chromium,
        "shared_patch_count": len(core_patches),
        "windows_patch_count": len(win_patches),
        "overlapping_target_count": len(overlap),
        "overlapping_targets": overlap,
        "mac_code_hints_count": len(mac_only_hints),
        "mac_code_hint_patches": sorted(mac_only_hints),
        "build_executed": False,
        "windows_patch_application_verified": False,
        "browser_launch_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "stage", "audit"))
    parser.add_argument("--platform-dir", type=Path,
                        default=ROOT / "work" / "windows-platform")
    parser.add_argument("--report", type=Path,
                        default=ROOT / "work" / "windows-audit.json")
    args = parser.parse_args()
    platform = args.platform_dir.resolve()
    core_revision = read_pin("arcium-core.sha")
    win_revision = read_pin("helium-windows.sha")

    if args.command == "plan":
        print(json.dumps({
            "platform_source": HELIUM_WINDOWS_URL,
            "platform_commit": win_revision,
            "platform_tag": WINDOWS_PLATFORM_TAG,
            "core_source": ARCIUM_URL,
            "core_commit": core_revision,
            "chromium_baseline": chromium_version(),
            "browser_build_available": False
        }, indent=2))
        return 0

    if args.command == "stage":
        clone_pinned(HELIUM_WINDOWS_URL, win_revision, platform,
                     branch=WINDOWS_PLATFORM_TAG)
        # The platform tracks Helium as a gitlink. Instead, populate its expected
        # helium-chromium directory with the exact Arcium shared core revision.
        # Never run git submodule update here: it would replace Arcium with Helium.
        core = platform / "helium-chromium"
        clone_pinned(ARCIUM_URL, core_revision, core)
    report = audit_staged(platform)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(args.report),
        "chromium_version": report["chromium_version"],
        "shared_patches": report["shared_patch_count"],
        "windows_patches": report["windows_patch_count"],
        "overlapping_target_count": report["overlapping_target_count"],
        "mac_code_hints_count": report["mac_code_hints_count"],
        "build_executed": False
    }, indent=2))
    if report["overlapping_target_count"]:
        print("WARNING: Shared and Windows patches modify overlapping files. "
              "This is an audit finding, NOT evidence that patch application fails.")
    print("Source staging passed. No Chromium patch application or compilation was run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
