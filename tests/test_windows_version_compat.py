"""Regression tests for pinned Helium-Windows vs Arcium version writer API."""

from pathlib import Path
import tempfile
import unittest

from scripts.windows_version_compat import (
    OLD_VERSION_BLOCK, NEW_VERSION_BLOCK,
    adapt_builder_version_api, assert_arcium_version_api
)


class WindowsVersionCompatibilityTests(unittest.TestCase):
    def test_replaces_obsolete_append_api(self):
        original = (
            '# Helium build script for Windows\n'
            'def run():\n'
            + OLD_VERSION_BLOCK +
            '        print("done")\n'
        )
        adapted = adapt_builder_version_api(original)
        self.assertIn(NEW_VERSION_BLOCK, adapted)
        self.assertNotIn("helium_version.append_version(", adapted)
        self.assertNotIn("helium_version.check_existing_version(", adapted)
        self.assertIn('print("done")', adapted)

    def test_unknown_platform_version_block_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            adapt_builder_version_api('def run():\n    print("different")\n')

    def test_duplicate_version_step_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            adapt_builder_version_api(OLD_VERSION_BLOCK + OLD_VERSION_BLOCK)

    def test_idempotent_second_attempt_rejected(self):
        adapted = adapt_builder_version_api("def run():\n" + OLD_VERSION_BLOCK)
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            adapt_builder_version_api(adapted)

    def test_core_has_refresh_version_api(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "helium_version.py"
            path.write_text(
                "def get_version_parts(tree, platform): pass\n"
                "def refresh_version(path, parts): pass\n",
                encoding="utf-8",
            )
            assert_arcium_version_api(path)
            path.write_text(
                "def get_version_parts(tree, platform): pass\n"
                "def check_existing_version(path): pass\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "API changed"):
                assert_arcium_version_api(path)


if __name__ == "__main__":
    unittest.main()
