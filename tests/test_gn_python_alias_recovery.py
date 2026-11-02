"""Regression checks for recovering a locally extracted, fully patched GN-only tree.

Never executes GN, source download, patch application, or Ninja in tests.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import recover_gn_python_alias as recovery


class GNRecoveryTests(unittest.TestCase):
    def fixture(self, work: Path):
        platform = work / "windows-platform"
        source = platform / "build" / "src"
        (source / "out" / "Default").mkdir(parents=True)
        (source / "buildtools" / "win").mkdir(parents=True)
        (source / "build" / "toolchain").mkdir(parents=True)
        (platform / "build.py").write_text("pinned source", encoding="utf-8")
        (platform / "arcium_gn_only.py").write_text("generated only", encoding="utf-8")
        for name in (
            "BUILD.gn", ".gn", "out/Default/args.gn",
            "buildtools/win/gn.exe", "build/toolchain/get_concurrent_links.py",
        ):
            (source / name).touch()
        report = {
            "status": "FAILED",
            "source_download_attempted": True,
            "chromium_version": "156.0.8078.47",
            "core_commit": "core",
            "platform_commit": "windows",
            "windows_sdk_version": recovery.REQUIRED_SDK,
            "expected_core_patches": 521,
            "expected_windows_patches": 30,
        }
        log = work / "gn-generation.log"
        log.write_text(
            r'D:\src\Arcium-Windows\build\src>"buildtools\win\gn.exe" '
            r'"gen" "out\Default" "--fail-on-unused-args"' + "\n"
            "Python was not found; run without arguments to install from the Microsoft Store\n",
            encoding="utf-8"
        )
        audit = {
            "chromium_version": "156.0.8078.47",
            "arcium_commit": "core",
            "platform_commit": "windows",
            "shared_patch_count": 521,
            "windows_patch_count": 30,
        }
        return platform, source, report, log, audit

    def test_accepts_only_verified_completed_preparation_to_gn(self):
        with tempfile.TemporaryDirectory() as d:
            platform, source, report, log, audit = self.fixture(Path(d))
            with patch.object(recovery, "audit_staged", return_value=audit), patch.object(
                recovery, "create_gn_only_builder", return_value="generated only"
            ):
                self.assertEqual(
                    recovery.verify_prepared_state(platform, report, log), source
                )

    def test_rejects_unfinished_or_changed_patch_setup(self):
        with tempfile.TemporaryDirectory() as d:
            platform, _, report, log, audit = self.fixture(Path(d))
            with patch.object(recovery, "audit_staged", return_value=audit), patch.object(
                recovery, "create_gn_only_builder", return_value="generated only"
            ):
                report["status"] = "RUNNING"
                with self.assertRaisesRegex(ValueError, "status"):
                    recovery.verify_prepared_state(platform, report, log)
                report["status"] = "FAILED"
                report["expected_core_patches"] = 500
                with self.assertRaisesRegex(ValueError, "expected_core_patches"):
                    recovery.verify_prepared_state(platform, report, log)

    def test_rejects_unrelated_error_and_existing_marker(self):
        with tempfile.TemporaryDirectory() as d:
            platform, _, report, log, audit = self.fixture(Path(d))
            with patch.object(recovery, "audit_staged", return_value=audit), patch.object(
                recovery, "create_gn_only_builder", return_value="generated only"
            ):
                log.write_text("GN failed for another reason", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "does not prove"):
                    recovery.verify_prepared_state(platform, report, log)
                log.write_text(
                    'buildtools\\win\\gn.exe gen out\\Default\n'
                    'Python was not found; install from the Microsoft Store\n',
                    encoding="utf-8",
                )
                (platform / "ARCIUM_GN_GENERATED.marker").write_text(
                    recovery.GN_MARKER, encoding="utf-8"
                )
                with self.assertRaises(FileExistsError):
                    recovery.verify_prepared_state(platform, report, log)

    def test_recovery_never_redownloads_patches_or_builds_installers(self):
        script = Path(recovery.__file__).read_text(encoding="utf-8")
        self.assertIn("--script-executable=", script)
        self.assertIn("gen out\\\\Default --fail-on-unused-args", script)
        self.assertIn("recovery_log", script)
        self.assertIn("marker.write_text(GN_MARKER", script)
        self.assertNotIn("downloads.unpack_downloads", script)
        self.assertNotIn("patches.apply_patches", script)
        self.assertNotIn("ninja_commandline", script)
        self.assertNotIn("mini_installer", script)


if __name__ == "__main__":
    unittest.main()
