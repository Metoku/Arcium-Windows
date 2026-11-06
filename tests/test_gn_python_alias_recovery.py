"""Regression checks for recovering a locally extracted, fully patched GN-only tree.

Never executes GN, source download, patch application, or Ninja in tests.
"""
from pathlib import Path
import json
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts import recover_gn_python_alias as recovery
from scripts.gn_smoke import create_gn_only_builder
from tests.test_gn_smoke import upstream_fixture


class GNRecoveryTests(unittest.TestCase):
    def test_real_default_and_release_builders_match_only_the_recorded_mode(self):
        for release in (False, True):
            for pin_python in (False, True):
                with self.subTest(release=release, pin_python=pin_python), tempfile.TemporaryDirectory() as d:
                    work = Path(d)
                    platform, source, report, log, audit = self.fixture(work)
                    builder = upstream_fixture()
                    (platform / 'build.py').write_text(builder, encoding='utf-8')
                    generated = platform / 'arcium_gn_only.py'
                    generated.write_text(create_gn_only_builder(
                        builder, release_candidate=release, pin_python=pin_python),
                        encoding='utf-8')
                    report['release_candidate_integrations'] = release
                    retained = source / 'out/Default/retained.obj'
                    retained.write_bytes(b'completed output')
                    before = {p:(p.read_bytes(), p.stat().st_mtime_ns)
                              for p in work.rglob('*') if p.is_file()}
                    with patch.object(recovery, 'audit_staged', return_value=audit):
                        self.assertEqual(recovery.verify_prepared_state(platform, report, log), source)
                        self.assertEqual(before, {p:(p.read_bytes(), p.stat().st_mtime_ns)
                                                 for p in work.rglob('*') if p.is_file()})
                        report['release_candidate_integrations'] = not release
                        with self.assertRaisesRegex(ValueError, 'differs from reviewed'):
                            recovery.verify_prepared_state(platform, report, log)
                        report['release_candidate_integrations'] = release
                        generated.write_text(generated.read_text() + '\n# unknown local edit\n')
                        with self.assertRaisesRegex(ValueError, 'differs from reviewed'):
                            recovery.verify_prepared_state(platform, report, log)

    def test_non_boolean_release_mode_is_rejected_without_changing_source(self):
        with tempfile.TemporaryDirectory() as d:
            platform, source, report, log, audit = self.fixture(Path(d))
            report['release_candidate_integrations'] = 'false'
            with patch.object(recovery, 'audit_staged', return_value=audit):
                with self.assertRaisesRegex(ValueError, 'not a boolean'):
                    recovery.verify_prepared_state(platform, report, log)

    def test_legacy_release_recovery_runs_only_gn_with_real_python_and_marks_success_only_on_success(self):
        for exit_code in (0, 1):
            with self.subTest(exit_code=exit_code), tempfile.TemporaryDirectory(prefix='gn recovery ') as d:
                root = Path(d)
                work = root / 'work'
                work.mkdir()
                platform, source, report, log, audit = self.fixture(work)
                builder = upstream_fixture()
                (platform / 'build.py').write_text(builder, encoding='utf-8')
                (platform / 'arcium_gn_only.py').write_text(create_gn_only_builder(
                    builder, release_candidate=True, pin_python=False), encoding='utf-8')
                report['release_candidate_integrations'] = True
                report_path = log.with_suffix('.json')
                report_path.write_text(json.dumps(report), encoding='utf-8')
                original_report = report_path.read_bytes()
                retained = source / 'out/Default/retained.obj'
                retained.write_bytes(b'completed output')
                profile = root / 'existing-profile/Default/Preferences'
                profile.parent.mkdir(parents=True)
                profile.write_bytes(b'{"existing":"profile"}')
                protected = {p:(p.read_bytes(), p.stat().st_mtime_ns)
                             for p in (retained, profile, source/'BUILD.gn', log)}
                python = root / 'Program Files/Python314/python.exe'
                python.parent.mkdir(parents=True)
                python.touch()
                vcvars = root / 'Visual Studio/vcvarsall.bat'
                vcvars.parent.mkdir()
                vcvars.touch()
                commands = []
                def run_only_gn(args, **kwargs):
                    self.assertEqual(args[-3:-1], ['/d', '/c'])
                    commands.append(Path(args[-1]).read_text())
                    self.assertIn('--script-executable="' + str(python.resolve()) + '"', commands[-1])
                    self.assertNotIn('apply_patches', commands[-1])
                    self.assertNotIn('autoninja', commands[-1])
                    self.assertEqual(kwargs['timeout'], 1800)
                    (source/'out/Default/build.ninja').write_text('generated graph')
                    return SimpleNamespace(returncode=exit_code)
                with patch.object(recovery, 'ROOT', root), \
                     patch.object(recovery, 'audit_staged', return_value=audit), \
                     patch.object(recovery, 'find_vcvarsall', return_value=vcvars), \
                     patch.object(recovery, 'select_windows_sdk', return_value=recovery.REQUIRED_SDK), \
                     patch.object(recovery.sys, 'executable', str(python)), \
                     patch.object(recovery.sys, 'platform', 'win32'), \
                     patch.object(recovery.subprocess, 'run', side_effect=run_only_gn):
                    self.assertEqual(recovery.recover(platform, report_path, execute=True), exit_code)
                self.assertEqual(len(commands), 1)
                self.assertFalse((work/'arcium-recover-gn.cmd').exists())
                self.assertEqual(protected, {p:(p.read_bytes(), p.stat().st_mtime_ns)
                                            for p in protected})
                if exit_code == 0:
                    self.assertEqual((platform/'ARCIUM_GN_GENERATED.marker').read_text(),
                                     recovery.GN_MARKER)
                    self.assertEqual(json.loads(report_path.read_text())['status'], 'GN_GENERATED')
                else:
                    self.assertFalse((platform/'ARCIUM_GN_GENERATED.marker').exists())
                    self.assertEqual(report_path.read_bytes(), original_report)

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
        self.assertIn("gen out", script)
        self.assertIn("--fail-on-unused-args", script)
        self.assertIn("recovery_log", script)
        self.assertIn("marker.write_text(GN_MARKER", script)
        self.assertNotIn("downloads.unpack_downloads", script)
        self.assertNotIn("patches.apply_patches", script)
        self.assertNotIn("ninja_commandline", script)
        self.assertNotIn("mini_installer", script)


if __name__ == "__main__":
    unittest.main()
