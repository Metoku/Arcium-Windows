#!/usr/bin/env python3
"""Restore narrowly scoped Chromium WebUI test fixtures omitted by base archives.

Pinned Arcium test-support patches target WebUI TypeScript tests absent from
some prepared Windows source archives. Restore only an explicit allowlist of
exact Chromium 156.0.8078.47 source blobs, verified
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
    "chrome/test/data/webui/extensions/sidebar_test.ts":
        "d62d26b4192539125b213720d1777d08bf37a35d",
    "chrome/test/data/webui/history/history_routing_test.ts":
        "5461ec4695023c2d1ac64655f8f1913ade5fe89f",
    "chrome/test/data/webui/new_tab_page/app_test.ts":
        "0ceac229900a53346d43cc5fdf86996f8f6aff3d",
    "chrome/test/data/webui/new_tab_page/new_tab_page_browsertest.cc":
        "9907372be673bd4909b0921d466db5f25411e0f0",
    "chrome/test/data/webui/settings/about_page_test.ts":
        "72633b9e55541dd7868d033efdf20dbf5143f939",
    "chrome/test/data/webui/settings/import_data_dialog_test.ts":
        "b0d52e62e2945e8229c3f22b201b6d3323cff678",
    "chrome/test/data/webui/settings/people_page_manage_profile_test.ts":
        "799ecf2ea8067c01c811bf3b4e6beae8fc346620",
    "chrome/test/data/webui/settings/people_page_sync_controls_test.ts":
        "795d7f214599866e0baaf79058cd73a97d61e520",
    "chrome/test/data/webui/settings/people_page_sync_page_interactive_test.ts":
        "12944709e5c67baf2d6ac27d01dea7d43dc4ba7f",
    "chrome/test/data/webui/settings/people_page_sync_page_test.ts":
        "1a61b1aafd9e376839cb4b074756860d2f31ff93",
    "chrome/test/data/webui/settings/system_page_test.ts":
        "9b9991a31ff7daa9f398fec8119161b4eefdc31b",
    "chrome/test/data/webui/settings/test_search_engines_browser_proxy.ts":
        "613b3dd37b9de7f0d6fed622bd4c6617505cb8ff",
    "chrome/test/data/webui/settings/appearance_page_test.ts":
        "68332a3cf5a524632a0753d283338e76584ced9b",
    "chrome/test/data/webui/settings/clear_browsing_data_dialog_test.ts":
        "4951ee32bf5ef39a35cae9da0de48d5a50945e1f",
    "chrome/test/data/webui/settings/do_not_track_toggle_test.ts":
        "d669dc92c17c4077d6bd95bad240e0f2555838f7",
    "chrome/test/data/webui/settings/payments_page_test.ts":
        "b4ed60422125e49c2b758338471cd1af3c458359",
    "chrome/test/data/webui/settings/personalization_options_test.ts":
        "fe07b258893f8fdccd1eb46a9cd9137131979183",
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
    """Verify existing fixtures; download only allowlisted missing files."""
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
