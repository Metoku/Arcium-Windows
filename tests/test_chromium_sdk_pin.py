"""Offline strict tests for pinning Chromium's internal Windows SDK version."""

from pathlib import Path
import tempfile
import unittest

from scripts.chromium_sdk_pin import (
    CHROMIUM_BASELINE_SDK, CHROMIUM_SDK_FILES, SDK_PIN_ANCHOR,
    inject_chromium_sdk_pin, pin_chromium_sdk_version
)


class ChromiumSDKPinTests(unittest.TestCase):
    def prepare(self, root, *, other_version=None):
        (root / "BUILD.gn").write_text("", encoding="utf-8")
        for relative in CHROMIUM_SDK_FILES:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            version = other_version or CHROMIUM_BASELINE_SDK
            target.write_bytes(
                ("# Original Chromium source\r\n"
                 "SDK_VERSION = '" + version + "'\r\n"
                 "def toolchain():\r\n    pass\r\n").encode("ascii")
            )

    def test_updates_both_chromium_constants_and_preserves_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root)
            result = pin_chromium_sdk_version(root, "10.0.26100.0")
            self.assertEqual(tuple(result), CHROMIUM_SDK_FILES)
            for relative in CHROMIUM_SDK_FILES:
                data = (root / relative).read_bytes()
                self.assertIn(b"SDK_VERSION = '10.0.26100.0'\r\n", data)
                self.assertNotIn(CHROMIUM_BASELINE_SDK.encode(), data)
                self.assertIn(b"def toolchain():\r\n", data)

    def test_fail_closed_if_one_original_constant_mismatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root)
            second = root / CHROMIUM_SDK_FILES[1]
            second.write_bytes(b"SDK_VERSION = '10.0.26100.0'\n")
            before = (root / CHROMIUM_SDK_FILES[0]).read_bytes()
            with self.assertRaisesRegex(ValueError, "Unknown pinned Chromium"):
                pin_chromium_sdk_version(root, "10.0.26100.0")
            self.assertEqual((root / CHROMIUM_SDK_FILES[0]).read_bytes(), before)

    def test_reject_invalid_target_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "Invalid Windows SDK"):
                pin_chromium_sdk_version(Path(tmp), "26100 & del /Q C:\\tmp")

    def test_strict_injection_before_source_entry(self):
        source = "def main():\n" + SDK_PIN_ANCHOR + "    os.chdir(source_tree)\n"
        result = inject_chromium_sdk_pin(source)
        self.assertIn("pin_chromium_sdk_version(source_tree", result)
        self.assertLess(result.index("pin_chromium_sdk_version(source_tree"),
                        result.index("os.chdir(source_tree)"))
        with self.assertRaisesRegex(ValueError, "pre-GN source entry"):
            inject_chromium_sdk_pin("def main():\n    pass\n")
        with self.assertRaisesRegex(ValueError, "pre-GN source entry"):
            inject_chromium_sdk_pin(source + SDK_PIN_ANCHOR)


if __name__ == "__main__":
    unittest.main()
