"""Tests for extracting and applying actual patch hunks, without network."""

import base64
import hashlib
from pathlib import Path
import shutil
import urllib.error
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from scripts.check_patch_overlaps import (
    chromium_source_url, discover_patch_paths, normalize_patch_path, select_patch_sections,
    download_original, chromium_dependency_revisions,
    winsparkle_platform_version,
    apply_sections
)


class PatchOverlapChecks(unittest.TestCase):
    def test_paths(self):
        self.assertEqual(
            normalize_patch_path("src.orig/chrome/browser/ui/browser.cc"),
            "chrome/browser/ui/browser.cc"
        )
        self.assertEqual(
            normalize_patch_path("a/chrome/browser/ui/browser.cc\t2026-10-10"),
            "chrome/browser/ui/browser.cc"
        )
        self.assertIsNone(normalize_patch_path("/dev/null"))
        self.assertIsNone(normalize_patch_path("a/../etc/passwd"))

    def test_unified_diff_selector_multi_format(self):
        diff = (
            "Index: src/chrome/browser/ui/browser.cc\n"
            "--- src.orig/chrome/browser/ui/browser.cc\n"
            "+++ src/chrome/browser/ui/browser.cc\n"
            "@@ -1 +1 @@\n"
            "-before\n"
            "+after\n"
            "Index: src/chrome/browser/ui/other.cc\n"
            "--- src.orig/chrome/browser/ui/other.cc\n"
            "+++ src/chrome/browser/ui/other.cc\n"
            "@@ -1 +1 @@\n"
            "-before\n"
            "+other\n"
            "diff --git a/chrome/browser/ui/browser.h b/chrome/browser/ui/browser.h\n"
            "--- a/chrome/browser/ui/browser.h\n"
            "+++ b/chrome/browser/ui/browser.h\n"
            "@@ -1 +1 @@\n"
            "-first\n"
            "+second\n"
        )
        got = select_patch_sections(diff, {
            "chrome/browser/ui/browser.cc", "chrome/browser/ui/browser.h"
        })
        self.assertIn("+after\n", got)
        self.assertIn("+second\n", got)
        self.assertNotIn("+other\n", got)
        self.assertNotIn("Index: ", got)

    def test_discover_created_and_modified_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_file = Path(tmp) / "test.patch"
            test_file.write_text(
                "--- /dev/null\n"
                "+++ b/chrome/browser/new_file.cc\n"
                "@@ -0,0 +1 @@\n"
                "+test\n"
                "--- a/chrome/browser/old_file.cc\n"
                "+++ b/chrome/browser/old_file.cc\n"
                "@@ -1 +1 @@\n"
                "-old\n"
                "+new\n",
                encoding="utf-8"
            )
            touched, created = discover_patch_paths([test_file])
            self.assertEqual(touched, {
                "chrome/browser/new_file.cc", "chrome/browser/old_file.cc"
            })
            self.assertEqual(created, {"chrome/browser/new_file.cc"})

    def test_source_url_validation(self):
        self.assertIn(
            "refs/tags/156.0.8078.47/chrome/browser/ui/browser.cc",
            chromium_source_url("156.0.8078.47", "chrome/browser/ui/browser.cc")
        )
        with self.assertRaises(ValueError):
            chromium_source_url("156.0.8078.47", "chrome/../../../etc/passwd")
        with self.assertRaises(ValueError):
            chromium_source_url("latest", "chrome/browser/ui/browser.cc")
        self.assertIn(
            "/media/cdm/win/media_foundation_cdm.cc",
            chromium_source_url("156.0.8078.47",
                                "media/cdm/win/media_foundation_cdm.cc")
        )

    def test_winsparkle_dependency_version_from_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "downloads.ini").write_text(
                "[winsparkle]\nversion = 0.9.3\n", encoding="utf-8"
            )
            self.assertEqual(winsparkle_platform_version(path), "0.9.3")
            (path / "downloads.ini").write_text(
                "[winsparkle]\nversion = ../../evil\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                winsparkle_platform_version(path)

    def test_external_dependency_revisions_follow_pinned_deps(self):
        deps = (
            "vars = {\n"
            "  'angle_revision': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',\n"
            "  'dawn_revision': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',\n"
            "}\n"
        ).encode("utf-8")
        response = MagicMock()
        response.__enter__.return_value.read.return_value = deps
        with patch(
            "scripts.check_patch_overlaps.urllib.request.urlopen",
            return_value=response
        ):
            revisions = chromium_dependency_revisions("156.0.8078.47")
        self.assertEqual(revisions["angle_revision"], "a" * 40)
        self.assertEqual(revisions["dawn_revision"], "b" * 40)

    def test_download_uses_other_official_mirror_on_http_429(self):
        data = b"verified original chromium source\\n"
        encoded = base64.b64encode(data)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = encoded
        failed_request = urllib.error.HTTPError(
            "https://example.com/rate-limited", 429, "Too Many Requests",
            None, None
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "chrome/browser/ui/browser.cc"
            with patch(
                "scripts.check_patch_overlaps.urllib.request.urlopen",
                side_effect=[failed_request, response]
            ):
                result = download_original(
                    "156.0.8078.47", "chrome/browser/ui/browser.cc",
                    target, mirror_first=True
                )
            self.assertEqual(target.read_bytes(), data)
            self.assertEqual(result, hashlib.sha256(data).hexdigest())

    @unittest.skipUnless(shutil.which("patch"), "GNU patch not available")
    def test_apply_extracted_patch_real_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "chrome/browser/ui/browser.cc"
            source.parent.mkdir(parents=True)
            source.write_text("before\n", encoding="utf-8")
            patch_text = (
                "--- src.orig/chrome/browser/ui/browser.cc\n"
                "+++ src/chrome/browser/ui/browser.cc\n"
                "@@ -1 +1 @@\n"
                "-before\n"
                "+after\n"
            )
            result = apply_sections(root, "Arcium", "fixture.patch", patch_text)
            self.assertTrue(result["passed"], result)
            self.assertEqual(source.read_text(encoding="utf-8"), "after\n")

    @unittest.skipUnless(shutil.which("patch"), "GNU patch not available")
    def test_patch_conflict_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "chrome/browser/ui/browser.cc"
            source.parent.mkdir(parents=True)
            source.write_text("different\n", encoding="utf-8")
            patch_text = (
                "--- a/chrome/browser/ui/browser.cc\n"
                "+++ b/chrome/browser/ui/browser.cc\n"
                "@@ -1 +1 @@\n"
                "-before\n"
                "+after\n"
            )
            result = apply_sections(root, "Windows", "failure.patch", patch_text)
            self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
