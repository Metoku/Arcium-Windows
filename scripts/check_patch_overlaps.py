#!/usr/bin/env python3
"""Apply selected portions of pinned Arcium and Windows Chromium patch stacks.

Downloads original files touched by both stacks or by Windows platform patches
from a matching Chromium tag, then applies relevant hunks in real series order.
This is focused compatibility testing, not complete patch application,
C++ compilation, or proof of Windows runtime support.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

from scripts.windows_port import audit_staged, chromium_version, read_series


MAX_SOURCE_BYTES = 12 * 1024 * 1024
SOURCE_URL_BASE = "https://chromium.googlesource.com/chromium/src/+/"


def normalize_patch_path(path: str) -> str | None:
    """Remove the one strip component expected by upstream GNU patch -p1."""
    path = path.strip().split("\t", 1)[0].split(" ", 1)[0]
    if path == "/dev/null":
        return None
    segments = PurePosixPath(path).parts
    if len(segments) < 2 or segments[0] not in ("a", "b", "src", "src.orig"):
        return None
    value = PurePosixPath(*segments[1:])
    if value.is_absolute() or ".." in value.parts or not value.parts:
        return None
    return value.as_posix()


def select_patch_sections(diff: str, targets: set[str]) -> str:
    """Select full unified-diff sections whose target file is in targets.

    Upstream patches use two formats:
    - GNU quilt: Index: src/path followed by --- src.orig/path and +++ src/path
    - Git style: diff --git ... followed by --- a/path and +++ b/path

    Preserve the ---/+++ lines and hunks as GNU patch -p1 expects. Other files
    are intentionally omitted so this audit only needs 9 source files.
    """
    lines = diff.splitlines(keepends=True)
    sections: list[str] = []
    i = 0
    while i + 1 < len(lines):
        if not (lines[i].startswith("--- ") and lines[i + 1].startswith("+++ ")):
            i += 1
            continue
        new_path = normalize_patch_path(lines[i + 1][4:])
        old_path = normalize_patch_path(lines[i][4:])
        target = new_path or old_path
        if target is None:
            i += 2
            continue

        start = i
        i += 2
        while i < len(lines):
            # A new file's Index/diff header belongs to the *next*
            # section. Leaving it in the previous patch confuses GNU patch.
            if lines[i].startswith(("Index: ", "diff --git ")):
                break
            if i + 1 < len(lines) and (
                lines[i].startswith("--- ") and lines[i + 1].startswith("+++ ")
            ):
                break
            i += 1
        if target in targets:
            sections.extend(lines[start:i])
    return "".join(sections)


def discover_patch_paths(patch_files: list[Path]) -> tuple[set[str], set[str]]:
    """Return patched paths and paths created by a /dev/null unified-diff hunk."""
    touched: set[str] = set()
    created: set[str] = set()
    for patch_file in patch_files:
        lines = patch_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for idx in range(len(lines) - 1):
            if not (lines[idx].startswith("--- ") and
                    lines[idx + 1].startswith("+++ ")):
                continue
            old_raw = lines[idx][4:].split(maxsplit=1)[0]
            old_path = normalize_patch_path(old_raw)
            new_path = normalize_patch_path(lines[idx + 1][4:])
            target = new_path or old_path
            if target is None:
                continue
            touched.add(target)
            if old_raw == "/dev/null":
                created.add(target)
    return touched, created


def chromium_source_url(version: str, path: str) -> str:
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version):
        raise ValueError("Expected a pinned Chromium version")
    parsed = PurePosixPath(path)
    if (parsed.is_absolute() or ".." in parsed.parts or len(parsed.parts) < 2
            or "\\" in path or ":" in path or path != parsed.as_posix()):
        raise ValueError("Unsafe Chromium source path")
    return (SOURCE_URL_BASE + "refs/tags/" + version + "/" +
            urllib.parse.quote(path, safe="/") + "?format=TEXT")


def chromium_dependency_revisions(version: str) -> dict[str, str]:
    """Read exact ANGLE/Dawn checkout SHAs from the pinned Chromium DEPS file."""
    chromium_source_url(version, "chrome/BUILD.gn")  # Validate version.
    url = ("https://raw.githubusercontent.com/chromium/chromium/" +
           version + "/DEPS")
    request = urllib.request.Request(
        url, headers={"User-Agent": "Arcium-Windows-dependency-audit/1.0"}
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = response.read(3 * 1024 * 1024 + 1)
    if len(payload) > 3 * 1024 * 1024:
        raise ValueError("Chromium DEPS unexpectedly large")
    contents = payload.decode("utf-8")
    revisions: dict[str, str] = {}
    for key in ("angle_revision", "dawn_revision"):
        match = re.search(
            r"['\"]" + re.escape(key) + r"['\"]\s*:\s*['\"]([0-9a-f]{40})['\"]",
            contents
        )
        if not match:
            raise ValueError(f"Chromium DEPS did not specify {key}")
        revisions[key] = match.group(1)
    return revisions


def download_original(version: str, path: str, dest: Path,
                      mirror_first: bool = False,
                      external_revisions: dict[str, str] | None = None) -> str:
    """Get a pinned source file from Chromium or a DEPS-pinned external repo."""
    gitiles = chromium_source_url(version, path)  # Validates path.
    github_raw = (
        "https://raw.githubusercontent.com/chromium/chromium/" + version +
        "/" + urllib.parse.quote(path, safe="/")
    )
    sources: list[tuple[str, str, bool]]
    if path.startswith("third_party/angle/"):
        if external_revisions is None or "angle_revision" not in external_revisions:
            raise ValueError("Need Chromium DEPS ANGLE revision for external source")
        revision = external_revisions["angle_revision"]
        relative = path.removeprefix("third_party/angle/")
        sources = [
            ("angle-github", "https://raw.githubusercontent.com/google/angle/" +
             revision + "/" + urllib.parse.quote(relative, safe="/"), False),
            ("angle-gitiles", "https://chromium.googlesource.com/angle/angle/+/" +
             revision + "/" + urllib.parse.quote(relative, safe="/") +
             "?format=TEXT", True),
        ]
    elif path.startswith("third_party/dawn/"):
        if external_revisions is None or "dawn_revision" not in external_revisions:
            raise ValueError("Need Chromium DEPS Dawn revision for external source")
        revision = external_revisions["dawn_revision"]
        relative = path.removeprefix("third_party/dawn/")
        sources = [
            ("dawn-gitiles", "https://dawn.googlesource.com/dawn/+/" +
             revision + "/" + urllib.parse.quote(relative, safe="/") +
             "?format=TEXT", True),
            ("dawn-github", "https://raw.githubusercontent.com/google/dawn/" +
             revision + "/" + urllib.parse.quote(relative, safe="/"), False),
        ]
    else:
        sources = (
            [("chromium-github", github_raw, False),
             ("chromium-gitiles", gitiles, True)] if mirror_first else
            [("chromium-gitiles", gitiles, True),
             ("chromium-github", github_raw, False)]
        )

    errors: list[str] = []
    for provider, url, is_base64 in sources:
        request = urllib.request.Request(
            url, headers={"User-Agent": "Arcium-Windows-patch-compatibility/1.0"}
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                encoded = response.read(4 * MAX_SOURCE_BYTES + 1)
            if len(encoded) > 4 * MAX_SOURCE_BYTES:
                raise ValueError(f"Chromium source unexpectedly large: {path}")
            raw = (base64.b64decode(encoded, validate=True)
                   if is_base64 else encoded)
            if len(raw) > MAX_SOURCE_BYTES:
                raise ValueError(f"Decoded source exceeds size cap: {path}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            print(f"  Verified {provider} at pinned revision: {path}", flush=True)
            return hashlib.sha256(raw).hexdigest()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            errors.append(f"{provider}: {exc}")
            print(f"  Source mirror error: {errors[-1]}", flush=True)
    raise RuntimeError(f"Could not retrieve {path} at {version}: {'; '.join(errors)}")


def apply_sections(worktree: Path, source: str, patch_name: str, filtered: str) -> dict:
    proc = subprocess.run(
        [
            "patch", "-p1", "--batch", "--forward",
            "--ignore-whitespace", "--fuzz=0", "--no-backup-if-mismatch",
            "-d", str(worktree),
        ],
        input=filtered, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "source": source,
        "patch": patch_name,
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def check_overlaps(platform: Path, workspace: Path, report_file: Path,
                   scope: str = "overlap") -> int:
    original = audit_staged(platform)
    core = platform / "helium-chromium"
    version = chromium_version()
    core_patches = read_series(core / "patches" / "series")
    win_patches = read_series(platform / "patches" / "series")
    if scope == "overlap":
        targets = set(original["overlapping_targets"])
    elif scope == "windows":
        targets, _ = discover_patch_paths(win_patches)
    else:
        raise ValueError(f"Unsupported patch audit scope: {scope}")
    # Some paths are introduced by the first patch that touches them;
    # there is no original Chromium file to download for those additions.
    _, newly_created = discover_patch_paths(core_patches + win_patches)
    if not targets or len(targets) > 180:
        raise ValueError(f"Unexpected source target count: {len(targets)}")
    if not shutil.which("patch"):
        raise EnvironmentError("GNU patch is required")

    report: dict = {
        "status": "STARTED",
        "scope": "OVERLAPPING_FILES_ONLY" if scope == "overlap" else "WINDOWS_PATCH_TARGETS_ONLY",
        "warning": (
            "Only selected Chromium patch targets are tested. "
            "Passing is NOT equivalent to full patch application or a browser build."
        ),
        "platform_revision": original["platform_commit"],
        "core_revision": original["arcium_commit"],
        "chromium_version": version,
        "files": sorted(targets),
        "newly_created_paths": sorted(targets & newly_created),
        "original_sha256": {},
        "source_mirrors": [
            "https://chromium.googlesource.com/chromium/src",
            "https://github.com/chromium/chromium",
        ],
        "applied": [],
        "failure": None,
        "chromium_build_executed": False,
    }

    def persist() -> None:
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    try:
        if workspace.exists() and any(workspace.iterdir()):
            raise FileExistsError(f"Refusing to overwrite workspace: {workspace}")
        workspace.mkdir(parents=True, exist_ok=True)
        external_revisions = (
            chromium_dependency_revisions(version)
            if any(p.startswith(("third_party/angle/", "third_party/dawn/"))
                   for p in targets - newly_created)
            else {}
        )
        report["external_revisions"] = external_revisions
        for path in sorted(targets):
            if path in newly_created:
                print(f"Patch stack creates new file: {path}", flush=True)
                continue
            print(f"Fetching Chromium {version}: {path}", flush=True)
            report["original_sha256"][path] = download_original(
                version, path, workspace / path,
                mirror_first=(scope == "windows"),
                external_revisions=external_revisions
            )

        series = (
            [("Arcium", core / "patches", p) for p in core_patches] +
            [("Windows", platform / "patches", p) for p in win_patches]
        )
        for origin, root, patch_file in series:
            diff = patch_file.read_text(encoding="utf-8", errors="replace")
            selected = select_patch_sections(diff, targets)
            if not selected:
                continue
            name = patch_file.relative_to(root).as_posix()
            print(f"{origin} patch: {name}", flush=True)
            result = apply_sections(workspace, origin, name, selected)
            report["applied"].append(result)
            if not result["passed"]:
                report["status"] = "FAILED"
                report["failure"] = result
                persist()
                print(json.dumps(result, indent=2), file=sys.stderr)
                return 1
        report["status"] = "PASSED_OVERLAP_HUNKS_ONLY"
        persist()
        print(f"All {len(report['applied'])} selected patch operations passed "
              "on overlapping Chromium source files.")
        return 0
    except Exception as exc:
        report["status"] = "ERROR"
        report["failure"] = f"{type(exc).__name__}: {exc}"
        persist()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform-dir", type=Path,
                        default=Path("work/windows-platform"))
    parser.add_argument("--workspace", type=Path,
                        default=Path("work/chromium-overlap"))
    parser.add_argument("--report", type=Path,
                        default=Path("work/patch-overlap-results.json"))
    parser.add_argument("--scope", choices=("overlap", "windows"), default="overlap",
                        help="Overlap files (default) or every Windows patch target")
    args = parser.parse_args()
    return check_overlaps(
        args.platform_dir.resolve(),
        args.workspace.resolve(),
        args.report.resolve(),
        scope=args.scope,
    )


if __name__ == "__main__":
    raise SystemExit(main())
