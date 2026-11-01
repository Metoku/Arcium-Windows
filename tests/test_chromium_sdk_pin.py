"""Offline strict tests for pinning Chromium's internal Windows SDK version."""

from pathlib import Path
import tempfile
import unittest

from scripts.chromium_sdk_pin import (
    CHROMIUM_BASELINE_SDK, CHROMIUM_SDK_FILES, CHROMIUM_WINVER_FILE,
    SDK_PIN_ANCHOR, inject_chromium_sdk_pin, pin_chromium_sdk_version
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
        target = root / CHROMIUM_WINVER_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            b'# Copyright Chromium\r\n'
            b'config("winver") {\r\n'
            b'  defines = [\r\n'
            b'    "NTDDI_VERSION=NTDDI_WIN11_BR",\r\n'
            b'    "_WIN32_WINNT=0x0A00",\r\n'
            b'  ]\r\n}\r\n'
        )

    def test_updates_both_chromium_constants_and_preserves_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root)
            result = pin_chromium_sdk_version(root, "10.0.26100.0")
            self.assertEqual(
                tuple(result), CHROMIUM_SDK_FILES + (CHROMIUM_WINVER_FILE,)
            )
            winver = (root / CHROMIUM_WINVER_FILE).read_bytes()
            self.assertIn(b'"NTDDI_VERSION=NTDDI_WIN11_GE",\r\n', winver)
            self.assertNotIn(b'NTDDI_WIN11_BR', winver)
            self.assertIn(b'"_WIN32_WINNT=0x0A00",\r\n', winver)
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

    def test_unknown_chromium_winver_leaves_all_files_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root)
            winver = root / CHROMIUM_WINVER_FILE
            winver.write_bytes(
                winver.read_bytes().replace(
                    b'NTDDI_WIN11_BR', b'NTDDI_WIN11_GE'
                )
            )
            before = {
                path: (root / path).read_bytes()
                for path in CHROMIUM_SDK_FILES + (CHROMIUM_WINVER_FILE,)
            }
            with self.assertRaisesRegex(ValueError, "Chromium Windows NTDDI"):
                pin_chromium_sdk_version(root, "10.0.26100.0")
            for path, data in before.items():
                self.assertEqual((root / path).read_bytes(), data)

    def test_28000_keeps_br_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root)
            pin_chromium_sdk_version(root, "10.0.28000.0")
            self.assertIn(
                b'"NTDDI_VERSION=NTDDI_WIN11_BR"',
                (root / CHROMIUM_WINVER_FILE).read_bytes(),
            )

    def test_unreviewed_sdk_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.prepare(root)
            with self.assertRaisesRegex(ValueError, "Unsupported Windows SDK"):
                pin_chromium_sdk_version(root, "10.0.22621.0")

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
