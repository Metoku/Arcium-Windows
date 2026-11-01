"""Offline tests for complete SDK selection and strict pinned vcvars rewrite."""

from pathlib import Path
import tempfile
import unittest

from scripts.windows_sdk_compat import (
    ORIGINAL_VCVARS_CALL, PINNED_VCVARS_CALL,
    adapt_windows_vcvars, installed_complete_sdks, select_windows_sdk
)


class WindowsSDKCompatibilityTests(unittest.TestCase):
    def make_sdk(self, root: Path, version: str, complete: bool):
        for suffix in [
            f"Include/{version}/um",
            f"Include/{version}/shared",
            f"Include/{version}/ucrt",
            f"Lib/{version}/um/x64",
            f"Lib/{version}/ucrt/x64",
        ]:
            if not complete and suffix.endswith("/um"):
                continue
            (root / suffix).mkdir(parents=True, exist_ok=True)

    def test_prefers_highest_complete_sdk_over_partial_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_sdk(root, "10.0.26100.0", complete=True)
            self.make_sdk(root, "10.0.28000.0", complete=False)
            self.assertEqual(
                installed_complete_sdks(root), ["10.0.26100.0"]
            )
            self.assertEqual(select_windows_sdk(root), "10.0.26100.0")

    def test_raises_if_no_complete_sdk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_sdk(root, "10.0.28000.0", complete=False)
            with self.assertRaisesRegex(EnvironmentError, "No complete"):
                select_windows_sdk(root)

    def test_rewrite_exact_two_call_sites(self):
        script = (
            "def first():\n" + ORIGINAL_VCVARS_CALL + "\n" +
            "def second():\n" + ORIGINAL_VCVARS_CALL + "\n"
        )
        updated = adapt_windows_vcvars(script)
        self.assertEqual(updated.count(PINNED_VCVARS_CALL), 2)
        self.assertEqual(updated.count(ORIGINAL_VCVARS_CALL), 0)
        self.assertIn("'vcvarsall.bat'", updated)
        self.assertIn("ARCIUM_WINDOWS_SDK", updated)

    def test_refuse_unexpected_sdk_call_sites(self):
        with self.assertRaisesRegex(ValueError, "vcvars invocation changed"):
            adapt_windows_vcvars(
                "def only_one():\n" + ORIGINAL_VCVARS_CALL + "\n"
            )


if __name__ == "__main__":
    unittest.main()
