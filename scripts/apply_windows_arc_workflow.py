#!/usr/bin/env python3
"""Apply the Windows Arc workflow patch to an already prepared Chromium tree.

The default is a read-only check. This never downloads source, changes GN flags,
cleans build output, launches a browser, or edits a browser profile.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "windows" / "arc-workflow-settings.patch"


def patch_targets(text: str) -> list[str]:
    """Only allow this integration patch to edit existing Chromium UI files."""
    old_paths = re.findall(r"^--- a/(\S+)$", text, re.MULTILINE)
    new_paths = re.findall(r"^\+\+\+ b/(\S+)$", text, re.MULTILINE)
    if (not old_paths or old_paths != new_paths
            or len(set(old_paths)) != len(old_paths)
            or len(re.findall(r"^--- ", text, re.MULTILINE)) != len(old_paths)
            or len(re.findall(r"^\+\+\+ ", text, re.MULTILINE)) != len(new_paths)
            or "GIT binary patch" in text):
        raise ValueError("Expected one in-place edit per patch target")
    for path in new_paths:
        parts = PurePosixPath(path).parts
        if (
            not path.startswith("chrome/")
            or ".." in parts
            or "\\" in path
            or ":" in path
            or PurePosixPath(path).is_absolute()
        ):
            raise ValueError(f"Unsafe patch target: {path}")
    return new_paths


def git_apply(source: Path, patch: Path, *, reverse: bool, check: bool) -> subprocess.CompletedProcess[str]:
    # Do not inherit an outer repository's working-directory prefix (work/src
    # is normally inside Arcium-Windows), which can silently skip every hunk.
    # Absolute targets are permitted only after validating the fixed catalog.
    command = ["git", "apply", "--unsafe-paths", "--whitespace=nowarn",
               f"--directory={source.as_posix()}"]
    if reverse:
        command.append("--reverse")
    if check:
        command.append("--check")
    command.append(str(patch))
    env = os.environ.copy()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="arcium-patch-") as temporary:
        return subprocess.run(command, cwd=temporary, env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def integrate(source: Path, *, apply: bool = False, revert: bool = False,
              patch: Path = PATCH) -> str:
    source = source.resolve(strict=True)
    patch = patch.resolve(strict=True)
    targets = patch_targets(patch.read_text(encoding="utf-8"))
    if not (source / "BUILD.gn").is_file():
        raise ValueError("Expected a prepared Chromium source root containing BUILD.gn")
    # Reject symlink escapes before allowing git to write absolute paths.
    for target in targets:
        resolved = (source / target).resolve(strict=True)
        if not resolved.is_relative_to(source) or not resolved.is_file():
            raise ValueError(f"Patch target escapes the source root: {target}")
    forward = git_apply(source, patch, reverse=False, check=True)
    backward = git_apply(source, patch, reverse=True, check=True)
    if forward.returncode == 0 and backward.returncode != 0:
        status = "READY"
    elif backward.returncode == 0 and forward.returncode != 0:
        status = "APPLIED"
    else:
        raise RuntimeError(
            "The workflow patch does not match this source tree. No changes made.\n"
            + forward.stderr + backward.stderr)
    if not apply and not revert:
        return status
    if apply and revert:
        raise ValueError("Choose apply or revert")
    desired = "READY" if revert else "APPLIED"
    if status == desired:
        return status
    result = git_apply(source, patch, reverse=revert, check=False)
    if result.returncode:
        raise RuntimeError("Patch application failed:\n" + result.stderr)
    verified = git_apply(source, patch, reverse=not revert, check=True)
    if verified.returncode:
        raise RuntimeError("Patch verification failed:\n" + verified.stderr)
    return desired


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path,
                        default=ROOT / "work/windows-platform/build/src")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Read-only applicability check (default)")
    mode.add_argument("--apply", action="store_true", help="Apply only the Windows workflow patch")
    mode.add_argument("--revert", action="store_true", help="Undo only the Windows workflow patch")
    args = parser.parse_args()
    try:
        status = integrate(args.source_dir, apply=args.apply, revert=args.revert)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    print(f"ARCIUM_WINDOWS_ARC_WORKFLOW_{status}")
    if args.apply or args.revert:
        print("Resume the existing build to compile the changed UI. Build outputs were retained.")
    else:
        print("Read-only check. No source, build output, or profile was changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
