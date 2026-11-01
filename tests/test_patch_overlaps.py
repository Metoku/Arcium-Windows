"""Tests for extracting and applying actual patch hunks, without network."""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts.check_patch_overlaps import (
    chromium_source_url, normalize_patch_path, select_patch_sections,
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

    def test_source_url_validation(self):
        self.assertIn(
            "refs/tags/156.0.8078.47/chrome/browser/ui/browser.cc",
            chromium_source_url("156.0.8078.47", "chrome/browser/ui/browser.cc")
        )
        with self.assertRaises(ValueError):
            chromium_source_url("156.0.8078.47", "chrome/../../../etc/passwd")
        with self.assertRaises(ValueError):
            chromium_source_url("latest", "chrome/browser/ui/browser.cc")

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
