"""Offline pinned Chromium fixture integrity and restoration checks."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from scripts import restore_chromium_fixtures as restore


class RestorePinnedFixturesTests(unittest.TestCase):
    def test_git_blob_hash_matches_git_object_format(self):
        data = b"hello"
        expected = hashlib.sha1(b"blob 5\0hello").hexdigest()
        self.assertEqual(restore.git_blob_sha1(data), expected)

    def test_restore_missing_fixture_without_overwriting_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "BUILD.gn").write_text("", encoding="utf-8")
            first = "chrome/test/data/webui/fixture_one.ts"
            second = "chrome/test/data/webui/fixture_two.ts"
            sample = {first: b"first\n", second: b"second\n"}
            fixture_hashes = {
                name: restore.git_blob_sha1(content)
                for name, content in sample.items()
            }
            already = source / second
            already.parent.mkdir(parents=True)
            already.write_bytes(sample[second])
            with patch.object(restore, "CHROMIUM_WEBUI_FIXTURES", fixture_hashes), \
                 patch.object(restore, "chromium_version",
                              return_value=restore.FIXTURE_CHROMIUM_VERSION), \
                 patch.object(
                    restore, "fetch_expected_fixture",
                    side_effect=lambda path, expected_blob: sample[path]
                 ) as downloader:
                actual = restore.restore_chromium_test_fixtures(source)
            self.assertEqual(actual, [first])
            downloader.assert_called_once_with(first, fixture_hashes[first])
            self.assertEqual((source / first).read_bytes(), sample[first])
            self.assertEqual(already.read_bytes(), sample[second])

    def test_reject_existing_fixture_with_wrong_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "BUILD.gn").write_text("", encoding="utf-8")
            name = "chrome/test/data/webui/fixture.ts"
            dest = source / name
            dest.parent.mkdir(parents=True)
            dest.write_bytes(b"wrong\n")
            with patch.object(restore, "CHROMIUM_WEBUI_FIXTURES",
                              {name: restore.git_blob_sha1(b"expected\n")}), \
                 patch.object(restore, "chromium_version",
                              return_value=restore.FIXTURE_CHROMIUM_VERSION):
                with self.assertRaisesRegex(ValueError, "differs"):
                    restore.restore_chromium_test_fixtures(source)

    def test_reject_changed_chromium_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(restore, "chromium_version",
                              return_value="156.0.8078.79"):
                with self.assertRaisesRegex(ValueError, "revalidate"):
                    restore.restore_chromium_test_fixtures(Path(tmp))

    def test_fetch_from_pinned_github_blob_hash(self):
        data = b"official test data\n"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = data
        with patch("scripts.restore_chromium_fixtures.urllib.request.urlopen",
                   return_value=response):
            actual = restore.fetch_expected_fixture(
                "chrome/test/data/webui/test_file.ts",
                restore.git_blob_sha1(data),
            )
        self.assertEqual(actual, data)

    def test_large_pinned_chromium_fixture_is_accepted(self):
        # chromium/new_tab_page/app_test.ts is ~223 KB in this release.
        data = b"// test\\n" * 30000
        response = MagicMock()
        response.__enter__.return_value.read.return_value = data
        with patch("scripts.restore_chromium_fixtures.urllib.request.urlopen",
                   return_value=response):
            value = restore.fetch_expected_fixture(
                "chrome/test/data/webui/new_tab_page/app_test.ts",
                restore.git_blob_sha1(data)
            )
        self.assertEqual(value, data)

    def test_reject_too_large_fixture(self):
        # Keep the source integrity and bounded-download protection.
        data = b"x" * (restore.MAX_FIXTURE_BYTES + 1)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = data
        with patch("scripts.restore_chromium_fixtures.urllib.request.urlopen",
                   return_value=response):
            with self.assertRaisesRegex(ValueError, "unexpectedly large"):
                restore.fetch_expected_fixture(
                    "chrome/test/data/webui/new_tab_page/app_test.ts",
                    restore.git_blob_sha1(data)
                )

    def test_refuse_unexpected_blob_hash(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"tampered"
        with patch("scripts.restore_chromium_fixtures.urllib.request.urlopen",
                   return_value=response):
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                restore.fetch_expected_fixture(
                    "chrome/test/data/webui/test_file.ts",
                    restore.git_blob_sha1(b"original"),
                )


if __name__ == "__main__":
    unittest.main()
