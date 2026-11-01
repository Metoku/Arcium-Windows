#!/usr/bin/env python3
"""Restore narrowly scoped Chromium WebUI test fixtures omitted by base archives.

The pinned Arcium patch heliom-profile-avatar-test-support.patch targets three
Chromium TypeScript tests absent from the prepared Windows source tarball.
Restore only those exact official Chromium 156.0.8078.47 source blobs, verified
against their Git blob hashes. Never modify an existing divergent source file.

This is not a general-purpose Chromium downloader or browser build.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path, PurePosixPath
import urllib.error
import urllib.request

from scripts.windows_port import chromium_version

# Exact blob SHA-1 IDs at Chromium 156.0.8078.47.
# These are Git *blob object* hashes, not raw file-content SHA-1 hashes.
CHROMIUM_WEBUI_FIXTURES = {
    "chrome/test/data/webui/cr_elements/cr_profile_avatar_selector_test.ts":
        "2135e5dd1ee803a36fac9a1b36c5b2650948dc60",
    "chrome/test/data/webui/signin/test_manage_profiles_browser_proxy.ts":
        "a096a050c82d5ae2da34dd85d6f985f3909719ea",
    "chrome/test/data/webui/signin/test_profile_customization_browser_proxy.ts":
        "46075b0f7d303984c98111b016cbfb0545773f2e",
}
FIXTURE_CHROMIUM_VERSION = "156.0.8078.47"
MAX_FIXTURE_BYTES = 128 * 1024


def git_blob_sha1(content: bytes) -> str:
    data = f"blob {len(content)}\0".encode("ascii") + content
    return hashlib.sha1(data).hexdigest()


def fetch_expected_fixture(path: str, expected_blob: str,
                           version: str = FIXTURE_CHROMIUM_VERSION) -> bytes:
    """Fetch immutable-tag fixture from two Chromium mirrors with size limits."""
    path_obj = PurePosixPath(path)
    if (path_obj.is_absolute() or ".." in path_obj.parts or
            not path.startswith("chrome/test/data/webui/") or
            path != path_obj.as_posix()):
        raise ValueError("Disallowed Chromium fixture path")
    sources = [
        ("github",
         f"https://raw.githubusercontent.com/chromium/chromium/{version}/{path}", False),
        ("gitiles",
         f"https://chromium.googlesource.com/chromium/src/+/refs/tags/{version}/{path}?format=TEXT",
         True),
    ]
    failures = []
    for label, url, is_base64 in sources:
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "Arcium-Windows-pinned-fixtures"}
            )
            with urllib.request.urlopen(request, timeout=40) as response:
                payload = response.read(MAX_FIXTURE_BYTES * 2 + 1)
            if len(payload) > MAX_FIXTURE_BYTES * 2:
                raise ValueError("Fixture response unexpectedly large")
            data = base64.b64decode(payload, validate=True) if is_base64 else payload
            if len(data) > MAX_FIXTURE_BYTES:
                raise ValueError("Decoded fixture unexpectedly large")
            actual = git_blob_sha1(data)
            if actual != expected_blob:
                raise ValueError(
                    f"Git blob SHA mismatch for {path}: {actual} != {expected_blob}"
                )
            return data
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            failures.append(f"{label}: {exc}")
    raise RuntimeError(f"Unable to restore pinned Chromium fixture {path}: {failures}")


def restore_chromium_test_fixtures(source_tree: Path) -> list[str]:
    """Verify existing fixtures; download only the three missing source files."""
    if chromium_version() != FIXTURE_CHROMIUM_VERSION:
        raise ValueError(
            "Pinned Chromium version changed; revalidate fixture blob hashes first"
        )
    if not (source_tree / "BUILD.gn").is_file():
        raise FileNotFoundError("Chromium source root does not contain BUILD.gn")
    restored: list[str] = []
    for path, expected_blob in CHROMIUM_WEBUI_FIXTURES.items():
        dest = source_tree / path
        if dest.is_file():
            actual = git_blob_sha1(dest.read_bytes())
            if actual != expected_blob:
                raise ValueError(
                    f"Existing WebUI fixture differs from Chromium tag: {path}"
                )
            print(f"Verified existing Chromium fixture: {path}", flush=True)
            continue
        print(f"Restoring required WebUI test fixture: {path}", flush=True)
        data = fetch_expected_fixture(path, expected_blob)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        restored.append(path)
    print(
        f"WebUI test fixtures verified: {len(CHROMIUM_WEBUI_FIXTURES)}; "
        f"restored: {len(restored)}",
        flush=True
    )
    return restored
