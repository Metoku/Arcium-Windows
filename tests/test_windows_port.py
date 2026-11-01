"""Offline regression tests for the Windows platform source-preparation logic."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import windows_port


CORE_SHA = "a" * 40
PLATFORM_SHA = "b" * 40


class SourceAuditTests(unittest.TestCase):
    def test_patch_target_parsing(self):
        sample = "\n".join([
            "Index: src/chrome/browser/ui/views/frame/browser_view.cc",
            "--- src.orig/chrome/browser/ui/views/frame/browser_view.cc",
            "--- a/chrome/browser/ui/browser.h",
            "diff --git a/chrome/browser/ui/tabs.cc b/chrome/browser/ui/tabs.cc",
            "+++ b/chrome/browser/ui/browser.h",
        ])
        self.assertEqual(windows_port.patch_targets(sample), {
            "chrome/browser/ui/views/frame/browser_view.cc",
            "chrome/browser/ui/browser.h",
            "chrome/browser/ui/tabs.cc"
        })

    def test_series_skips_comments_and_fails_on_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            series = root / "series"
            (root / "a.patch").write_text("--- a/a.cc\n", encoding="utf-8")
            series.write_text("# a comment\n\na.patch\n", encoding="utf-8")
            self.assertEqual(windows_port.read_series(series), [root / "a.patch"])
            series.write_text("missing.patch\n", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                windows_port.read_series(series)

    def test_series_rejects_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            series = root / "series"
            series.write_text("file.patch -p1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                windows_port.read_series(series)

    def create_staging(self, root: Path):
        core = root / "helium-chromium"
        for parent in [root / "patches", core / "patches", core / "utils"]:
            parent.mkdir(parents=True, exist_ok=True)

        for name in ["build.py", "flags.windows.gn", "downloads.x64.ini"]:
            (root / name).write_text("", encoding="utf-8")
        for name in ["patches.py", "downloads.py"]:
            (core / "utils" / name).write_text("", encoding="utf-8")
        (core / "flags.gn").write_text("", encoding="utf-8")
        (core / "chromium_version.txt").write_text(
            "156.0.8078.47\n", encoding="utf-8"
        )
        (root / "patches" / "series").write_text("win.patch\n", encoding="utf-8")
        (root / "patches" / "win.patch").write_text(
            "--- a/chrome/browser/ui/browser.cc\n", encoding="utf-8"
        )
        (core / "patches" / "series").write_text(
            "arcium.patch\n", encoding="utf-8"
        )
        (core / "patches" / "arcium.patch").write_text(
            "Index: src/chrome/browser/ui/browser.cc\n"
            "#if BUILDFLAG(IS_MAC)\n", encoding="utf-8"
        )

    def test_audit_detects_overlapping_paths_without_claiming_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_staging(root)
            with patch.object(windows_port, "git", side_effect=[
                PLATFORM_SHA, CORE_SHA
            ]), patch.object(
                windows_port, "read_pin",
                side_effect=lambda name: PLATFORM_SHA
                if name == "helium-windows.sha" else CORE_SHA
            ), patch.object(
                windows_port, "chromium_version",
                return_value="156.0.8078.47"
            ):
                result = windows_port.audit_staged(root)
            self.assertEqual(result["overlapping_target_count"], 1)
            self.assertEqual(result["shared_patch_count"], 1)
            self.assertEqual(result["windows_patch_count"], 1)
            self.assertEqual(result["mac_code_hints_count"], 1)
            self.assertFalse(result["build_executed"])
            self.assertFalse(result["windows_patch_application_verified"])

    def test_audit_fails_closed_on_version_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_staging(root)
            (root / "helium-chromium" / "chromium_version.txt").write_text(
                "156.0.8078.79\n", encoding="utf-8"
            )
            with patch.object(windows_port, "git", side_effect=[
                PLATFORM_SHA, CORE_SHA
            ]), patch.object(
                windows_port, "read_pin",
                side_effect=lambda name: PLATFORM_SHA
                if name == "helium-windows.sha" else CORE_SHA
            ), patch.object(
                windows_port, "chromium_version",
                return_value="156.0.8078.47"
            ):
                with self.assertRaisesRegex(ValueError, "Chromium mismatch"):
                    windows_port.audit_staged(root)


if __name__ == "__main__":
    unittest.main()
