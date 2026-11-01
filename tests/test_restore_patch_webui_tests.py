"""Offline tests for safe dynamic restoration of pinned Chromium WebUI tests."""

import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from scripts import restore_patch_webui_tests as webui
from scripts.restore_chromium_fixtures import git_blob_sha1


TEST_FILE = "chrome/test/data/webui/extensions/sidebar_test.ts"


class DynamicWebUiRestoreTests(unittest.TestCase):
    def make_patches(self, root: Path):
        patch_dir = root / "patches"
        patch_dir.mkdir()
        (patch_dir / "series").write_text("test.patch\n", encoding="utf-8")
        (patch_dir / "test.patch").write_text(
            "--- a/chrome/test/data/webui/extensions/sidebar_test.ts\n"
            "+++ b/chrome/test/data/webui/extensions/sidebar_test.ts\n"
            "@@ -1 +1 @@\n-old\n+new\n"
            "--- /dev/null\n"
            "+++ b/chrome/test/data/webui/extensions/new_test.ts\n"
            "@@ -0,0 +1 @@\n+fresh\n"
            "--- a/chrome/browser/ui/browser.cc\n"
            "+++ b/chrome/browser/ui/browser.cc\n"
            "@@ -1 +1 @@\n-old\n+new\n",
            encoding="utf-8",
        )
        return patch_dir

    def test_discover_targets_ignores_created_and_non_webui_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch_dir = self.make_patches(root)
            self.assertEqual(
                webui.discover_webui_test_targets(patch_dir), [TEST_FILE]
            )

    def test_invalid_paths_rejected(self):
        self.assertTrue(webui.allowed_target(TEST_FILE))
        self.assertFalse(webui.allowed_target("chrome/test/data/webui/../../etc"))
        self.assertFalse(webui.allowed_target("chrome/test/data/webui/sub/../x.ts"))
        self.assertFalse(webui.allowed_target("chrome/browser/other.ts"))

    def test_restore_only_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch_dir = self.make_patches(root)
            source = root / "chromium"
            source.mkdir()
            (source / "BUILD.gn").write_text("", encoding="utf-8")
            with patch.object(webui, "chromium_version",
                              return_value=webui.FIXTURE_CHROMIUM_VERSION), \
                 patch.object(webui, "download_from_pinned_git",
                              return_value=b"original chromium source\n") as fetch:
                restored = webui.restore_missing_webui_patch_targets(
                    source, patch_dir
                )
                self.assertEqual(restored, [TEST_FILE])
                fetch.assert_called_once()
                restored_again = webui.restore_missing_webui_patch_targets(
                    source, patch_dir
                )
                self.assertEqual(restored_again, [])
                fetch.assert_called_once()
            self.assertEqual(
                (source / TEST_FILE).read_bytes(), b"original chromium source\n"
            )

    def test_pinned_api_verifies_git_blob(self):
        payload = b"// original chromium test\n"
        reply = {
            "type": "file",
            "path": TEST_FILE,
            "sha": git_blob_sha1(payload),
            "size": len(payload),
            "encoding": "base64",
            "content": base64.b64encode(payload).decode("ascii"),
        }
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            reply
        ).encode("utf-8")
        with patch.object(webui.urllib.request, "urlopen",
                          return_value=response):
            value = webui.download_from_pinned_git(
                webui.FIXTURE_CHROMIUM_VERSION, TEST_FILE
            )
        self.assertEqual(value, payload)

    def test_reject_mismatched_sha(self):
        payload = b"not the expected source\n"
        reply = {
            "type": "file",
            "path": TEST_FILE,
            "sha": git_blob_sha1(b"other content\n"),
            "size": len(payload),
            "encoding": "base64",
            "content": base64.b64encode(payload).decode("ascii"),
        }
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            reply
        ).encode("utf-8")
        with patch.object(webui.urllib.request, "urlopen",
                          return_value=response):
            with self.assertRaisesRegex(ValueError, "integrity"):
                webui.download_from_pinned_git(
                    webui.FIXTURE_CHROMIUM_VERSION, TEST_FILE
                )

    def test_404_is_not_silently_restored(self):
        not_found = urllib.error.HTTPError(
            "https://example.com", 404, "Not Found", None, None
        )
        with patch.object(webui.urllib.request, "urlopen",
                          side_effect=not_found):
            self.assertIsNone(webui.download_from_pinned_git(
                webui.FIXTURE_CHROMIUM_VERSION, TEST_FILE
            ))


if __name__ == "__main__":
    unittest.main()
