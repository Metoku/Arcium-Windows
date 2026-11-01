#!/usr/bin/env python3
"""Restore Chromium WebUI test files omitted by the lean Windows source archive.

Only original test files explicitly referenced by the exact pinned Arcium
patch series are candidates. Missing files are fetched from Chromium's exact
release tag using GitHub's Contents API. Their bytes must match the API's
Git blob SHA before being placed in the disposable build tree.

No patch may be skipped; no existing file is overwritten.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path, PurePosixPath
import re
import urllib.error
import urllib.parse
import urllib.request

from scripts.restore_chromium_fixtures import (
    FIXTURE_CHROMIUM_VERSION, git_blob_sha1
)
from scripts.windows_port import chromium_version, read_series


ALLOWED_PREFIX = "chrome/test/data/webui/"
ALLOWED_SUFFIXES = (".ts", ".js", ".cc", ".html")
MAX_FILES = 160
MAX_MISSING = 120
MAX_BYTES = 2 * 1024 * 1024


def allowed_target(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        isinstance(value, str)
        and value.startswith(ALLOWED_PREFIX)
        and len(path.parts) >= 5
        and path == PurePosixPath(value)
        and not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in value
        and value.endswith(ALLOWED_SUFFIXES)
    )


def discover_webui_test_targets(patches_root: Path) -> list[str]:
    """Enumerate existing original files modified by a pinned patch series."""
    originals: set[str] = set()
    for patch_file in read_series(patches_root / "series"):
        lines = patch_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for i in range(len(lines) - 1):
            if not lines[i].startswith("--- a/"):
                continue
            if not lines[i + 1].startswith("+++ b/"):
                continue
            old = lines[i][6:].split("\t")[0].split(" ")[0]
            new = lines[i + 1][6:].split("\t")[0].split(" ")[0]
            if old != new:
                continue
            if allowed_target(old):
                originals.add(old)
    if len(originals) > MAX_FILES:
        raise ValueError("Too many WebUI test targets in Arcium patch manifest")
    return sorted(originals)


def download_from_pinned_git(tag: str, path: str) -> bytes | None:
    """Get exact file bytes and verify against Chromium's pinned Git blob SHA.

    A 404 means the file is absent in the original release; the real patch
    stage remains responsible for reporting whether the file is required.
    Any other HTTP/network or integrity error fails closed.
    """
    if tag != FIXTURE_CHROMIUM_VERSION or not allowed_target(path):
        raise ValueError("Unapproved Chromium tag or WebUI fixture path")
    url = (
        "https://api.github.com/repos/chromium/chromium/contents/" +
        urllib.parse.quote(path, safe="/") +
        "?ref=" + urllib.parse.quote(tag, safe="")
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Arcium-Windows-source-restoration",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            response_bytes = response.read(4 * MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if len(response_bytes) > 4 * MAX_BYTES:
        raise ValueError("Chromium GitHub metadata response exceeded size limit")
    obj = json.loads(response_bytes)
    if (
        not isinstance(obj, dict)
        or obj.get("type") != "file"
        or obj.get("path") != path
        or obj.get("encoding") != "base64"
    ):
        raise ValueError("Unexpected Chromium Contents API response")
    expected_sha = obj.get("sha")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("Unexpected Chromium Git blob SHA")
    data = base64.b64decode(obj["content"], validate=False)
    if len(data) > MAX_BYTES:
        raise ValueError("Pinned Chromium WebUI test source exceeds size limit")
    if obj.get("size") != len(data) or git_blob_sha1(data) != expected_sha:
        raise ValueError("Pinned Chromium Git object failed integrity validation")
    return data


def restore_missing_webui_patch_targets(
    source_tree: Path, patches_root: Path
) -> list[str]:
    """Restore only missing *original* files named by the exact patch series."""
    if chromium_version() != FIXTURE_CHROMIUM_VERSION:
        raise ValueError("Chromium version changed; dynamic restoration is disabled")
    if not (source_tree / "BUILD.gn").is_file():
        raise FileNotFoundError("Chromium source root missing BUILD.gn")
    targets = discover_webui_test_targets(patches_root)
    missing = [path for path in targets if not (source_tree / path).is_file()]
    if len(missing) > MAX_MISSING:
        raise ValueError("Unexpected number of missing Chromium WebUI files")
    print(
        f"Arcium WebUI test targets: {len(targets)}; "
        f"missing from prepared source: {len(missing)}",
        flush=True,
    )
    restored: list[str] = []
    absent_in_upstream: list[str] = []
    for path in missing:
        payload = download_from_pinned_git(FIXTURE_CHROMIUM_VERSION, path)
        if payload is None:
            absent_in_upstream.append(path)
            continue
        destination = source_tree / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        # 'xb' prevents clobbering any file that another process created.
        with destination.open("xb") as handle:
            handle.write(payload)
        restored.append(path)
    print(
        f"Restored {len(restored)} pinned WebUI files; "
        f"{len(absent_in_upstream)} not present in Chromium tag.",
        flush=True,
    )
    if absent_in_upstream:
        print(
            "No original Chromium blob for: " + ", ".join(absent_in_upstream),
            flush=True,
        )
    return restored
