"""Replay optional Windows Arc patches against the exact pinned source files.

Only a temporary, partial source fixture is created. This does not compile
Chromium, create a browser profile, or touch an existing build workspace.
Run as: python -m scripts.check_windows_arc_import_patch --core-dir PATH
"""

from __future__ import annotations

import argparse
import hashlib
import json
from itertools import permutations
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from scripts.apply_windows_arc_workflow import (
    APPEARANCE_CSS_SOURCE, LEGACY_APPEARANCE_CSS, PATCH, ROOT,
    appearance_css_addition, git_apply, integrate, patch_targets,
)
from scripts.check_patch_overlaps import discover_patch_paths, download_original, select_patch_sections
from scripts.windows_port import audit_staged, chromium_version, git, read_pin, read_series


IMPORT_PATCH = ROOT / "patches/windows/arc-import-windows.patch"
PASSWORD_PATCH = ROOT / "patches/windows/arc-password-import-windows.patch"
APPEARANCE_PATCH = ROOT / "patches/windows/arc-appearance-windows.patch"


def normalize_headers(diff: str) -> str:
    diff = re.sub(r"^--- (?:src\.orig|src|a)/", "--- a/", diff, flags=re.MULTILINE)
    return re.sub(r"^\+\+\+ (?:src|b)/", "+++ b/", diff, flags=re.MULTILINE)


def check(core: Path, platform: Path | None = None,
          typescript: Path | None = None) -> dict:
    expected = read_pin("arcium-core.sha")
    if git("-C", core, "rev-parse", "HEAD") != expected:
        raise ValueError("The Arc import fixture requires the pinned Arcium core revision")
    patches = read_series(core / "patches/series")
    if platform is not None:
        audit_staged(platform)
        patches += read_series(platform / "patches/series")
    catalogs = (PATCH, IMPORT_PATCH, PASSWORD_PATCH, APPEARANCE_PATCH)
    targets = set().union(*(patch_targets(p.read_text(encoding="utf-8")) for p in catalogs))
    _, created = discover_patch_paths(patches)
    original_hashes = {}
    with tempfile.TemporaryDirectory(prefix="arcium-arc-import-replay-") as temporary:
        temporary = Path(temporary)
        source = temporary / "src"
        source.mkdir()
        # This marker satisfies the helper's source-root check; the fixture
        # contains only selected files and is deliberately not a build tree.
        (source / "BUILD.gn").write_text("# Partial patch replay fixture; not buildable.\n")
        for target in sorted(targets - created):
            original_hashes[target] = download_original(
                chromium_version(), target, source / target, mirror_first=True)
        replayed = []
        selected_patch = temporary / "selected.patch"
        for patch in patches:
            selected = select_patch_sections(patch.read_text(encoding="utf-8"), targets)
            if not selected:
                continue
            selected_patch.write_text(normalize_headers(selected), encoding="utf-8", newline="\n")
            result = git_apply(source, selected_patch, reverse=False, check=False)
            if result.returncode:
                raise RuntimeError(f"Pinned source replay failed at {patch}:\n{result.stderr}")
            replayed.append(patch.name)
        originals = {target: (source / target).read_bytes() for target in targets}
        sentinel = source / "out/Default/retained.obj"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_bytes(b"existing compiled output")
        sentinel_time = sentinel.stat().st_mtime_ns
        checks = []
        webui_report = None
        legacy_css_upgrade_checked = False
        lint_config = temporary / "stylelint.config_base.mjs"
        if typescript is not None:
            download_original(chromium_version(),
                "ui/webui/resources/tools/stylelint.config_base.mjs", lint_config,
                mirror_first=True)
        for style in ("LF", "CRLF", "mixed", "missing-final-newline"):
            for index, (target, data) in enumerate(sorted(originals.items())):
                normalized = data.replace(b"\r\n", b"\n")
                if style == "CRLF" or (style == "mixed" and index % 2):
                    normalized = normalized.replace(b"\n", b"\r\n")
                if style == "missing-final-newline":
                    normalized = normalized.removesuffix(b"\n")
                (source / target).write_bytes(normalized)
            baseline = {target: (source / target).read_bytes() for target in targets}
            for order in permutations(catalogs):
                for catalog in order:
                    before = {target: (source / target).stat().st_mtime_ns for target in targets}
                    if integrate(source, patch=catalog) != "READY":
                        raise RuntimeError(f"Fresh {catalog.name} was not ready")
                    if before != {target: (source / target).stat().st_mtime_ns for target in targets}:
                        raise RuntimeError("Read-only applicability check touched source timestamps")
                    if integrate(source, apply=True, patch=catalog) != "APPLIED":
                        raise RuntimeError(f"Could not apply {catalog.name}")
                if not legacy_css_upgrade_checked:
                    css = source / APPEARANCE_CSS_SOURCE
                    corrected_css = css.read_bytes()
                    fixed_block = appearance_css_addition(APPEARANCE_PATCH.read_bytes())
                    if corrected_css.count(fixed_block) != 1:
                        raise RuntimeError("Expected exactly one corrected appearance CSS block")
                    css.write_bytes(corrected_css.replace(fixed_block, LEGACY_APPEARANCE_CSS, 1))
                    upgrade_times = {target: (source / target).stat().st_mtime_ns for target in targets}
                    if integrate(source, patch=APPEARANCE_PATCH) != "UPDATE_AVAILABLE":
                        raise RuntimeError("Legacy appearance CSS was not recognized")
                    if upgrade_times != {target: (source / target).stat().st_mtime_ns for target in targets}:
                        raise RuntimeError("CSS upgrade check rewrote source")
                    integrate(source, patch=APPEARANCE_PATCH, apply=True)
                    if css.read_bytes() != corrected_css:
                        raise RuntimeError("Legacy CSS did not upgrade to the corrected block")
                    if any((source / target).stat().st_mtime_ns != stamp
                           for target, stamp in upgrade_times.items()
                           if target != APPEARANCE_CSS_SOURCE):
                        raise RuntimeError("CSS upgrade changed unrelated source")
                    legacy_css_upgrade_checked = True
                ET.parse(source / "chrome/app/settings_strings.grdp")
                if typescript is not None and webui_report is None:
                    result = subprocess.run(
                        ["node", str(ROOT / "scripts/check_windows_appearance_ui.cjs"),
                         "--source-dir", str(source), "--typescript", str(typescript.resolve())],
                        text=True, encoding="utf-8", capture_output=True)
                    if result.returncode:
                        raise RuntimeError("Appearance WebUI checks failed:\n" +
                                           result.stdout + result.stderr)
                    webui_report = json.loads(result.stdout)
                    css_result = subprocess.run(
                        ["node", str(ROOT / "scripts/check_windows_appearance_css.cjs"),
                         "--source-dir", str(source), "--config", str(lint_config),
                         "--node-modules", str(typescript.resolve().parent)],
                        text=True, encoding="utf-8", capture_output=True)
                    if css_result.returncode:
                        raise RuntimeError("Chromium appearance CSS lint failed:\n" +
                                           css_result.stdout + css_result.stderr)
                    webui_report["css_lint"] = json.loads(css_result.stdout)
                applied_times = {target: (source / target).stat().st_mtime_ns for target in targets}
                applied_hashes = {target: hashlib.sha256((source / target).read_bytes()).hexdigest()
                                  for target in targets}
                for catalog in catalogs:
                    if integrate(source, apply=True, patch=catalog) != "APPLIED":
                        raise RuntimeError("Optional patches do not coexist")
                if applied_times != {target: (source / target).stat().st_mtime_ns for target in targets}:
                    raise RuntimeError("Repeated application rewrote source files")
                for catalog in reversed(order):
                    if integrate(source, revert=True, patch=catalog) != "READY":
                        raise RuntimeError(f"Could not revert {catalog.name}")
                if any((source / target).read_bytes() != data for target, data in baseline.items()):
                    raise RuntimeError("Reversion did not restore exact source bytes")
                if (sentinel.read_bytes() != b"existing compiled output" or
                        sentinel.stat().st_mtime_ns != sentinel_time):
                    raise RuntimeError("The helper changed retained compilation output")
                checks.append({"source_endings": style,
                               "order": [p.name for p in order],
                               "applied_sha256": applied_hashes})
        return {"status": "PATCH_REPLAY_VERIFIED_NOT_COMPILED",
                "arcium_core": expected, "chromium_version": chromium_version(),
                "windows_platform_replayed": platform is not None,
                "targets": sorted(targets), "original_sha256": original_hashes,
                "upstream_patch_sections": len(replayed), "checks": checks,
                "build_output_preserved": True, "legacy_css_upgrade_verified": legacy_css_upgrade_checked,
                "browser_compiled": False,
                "browser_launch_verified": False, "appearance_webui": webui_report}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-dir", type=Path, required=True)
    parser.add_argument("--platform-dir", type=Path)
    parser.add_argument("--typescript", type=Path,
                        help="TypeScript module for optional isolated appearance WebUI checks")
    parser.add_argument("--report", type=Path, default=ROOT / "work/windows-arc-import-replay.json")
    args = parser.parse_args()
    report = check(args.core_dir.resolve(),
                   args.platform_dir.resolve() if args.platform_dir else None,
                   args.typescript)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"ARCIUM_WINDOWS_ARC_IMPORT_PATCH_REPLAY_PASSED: {len(report['targets'])} targets; "
          f"{len(report['checks'])} apply/revert combinations. C++ compilation and UI testing pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
