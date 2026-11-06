"""Reproduce the missing-origin compile error using the real Chromium 156 types.

The fixtures are the complete pinned header, logger and metrics file. Only the
logger's build_config/NOTREACHED transitive support is stubbed by the contract.
"""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts.apply_windows_arc_workflow import (
    ROOT, PROFILE_KEEP_ALIVE_PATCH, PROFILE_KEEP_ALIVE_METRICS,
    integrate, patch_targets,
    main,
)
from scripts.check_windows_profile_keep_alive import (
    HEADER, LOGGER, compile_contract, verify_profile_keep_alive,
)


class ProfileKeepAliveTests(unittest.TestCase):
    def fixture(self, source, endings="LF"):
        source.mkdir(exist_ok=True)
        (source / "BUILD.gn").write_bytes(b"# partial source fixture\n")
        for index, (target, name) in enumerate((
                (HEADER, "profile_keep_alive_types.h"),
                (LOGGER, "profile_keep_alive_types.cc"),
                (PROFILE_KEEP_ALIVE_METRICS, "profile_enums.xml"))):
            data = (ROOT / "tests/fixtures" / name).read_bytes().replace(b"\r\n", b"\n")
            if endings == "CRLF" or (endings == "mixed" and index % 2):
                data = data.replace(b"\n", b"\r\n")
            if endings == "missing-final-newline":
                data = data.removesuffix(b"\n")
            path = source / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for target in ("out/Default/retained.obj", "existing-profile/Default/Preferences"):
            path = source / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"retained compiled output or profile")

    @staticmethod
    def snapshot(source):
        return {p.relative_to(source).as_posix():(p.read_bytes(), p.stat().st_mtime_ns)
                for p in source.rglob("*") if p.is_file()}

    def test_scope_contains_the_complete_enum_logger_and_metric_port(self):
        targets = set(patch_targets(PROFILE_KEEP_ALIVE_PATCH.read_text()))
        self.assertEqual(targets, {HEADER, LOGGER, PROFILE_KEEP_ALIVE_METRICS})
        with self.assertRaises(ValueError):
            patch_targets("--- a/tools/metrics/unrelated.xml\n+++ b/tools/metrics/unrelated.xml\n")

    def test_resume_cli_checks_then_applies_only_the_required_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            self.fixture(source)
            arguments = ["apply_windows_arc_workflow", "--source-dir", str(source),
                         "--feature", "profile-keep-alive"]
            before = self.snapshot(source)
            with patch("sys.argv", arguments), patch("builtins.print"):
                self.assertEqual(main(), 0)
            self.assertEqual(before, self.snapshot(source))
            with patch("sys.argv", [*arguments, "--apply"]), patch("builtins.print"):
                self.assertEqual(main(), 0)
            self.assertEqual(verify_profile_keep_alive(source)["origin"], 47)

    def test_read_only_apply_idempotence_revert_and_saved_output_in_all_line_endings(self):
        for endings in ("LF", "CRLF", "mixed", "missing-final-newline"):
            with self.subTest(endings=endings), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp)
                self.fixture(source, endings)
                original = self.snapshot(source)
                with self.assertRaisesRegex(RuntimeError, "kArciumSettingsWindow"):
                    verify_profile_keep_alive(source)
                self.assertEqual(integrate(source, patch=PROFILE_KEEP_ALIVE_PATCH), "READY")
                self.assertEqual(self.snapshot(source), original)
                integrate(source, patch=PROFILE_KEEP_ALIVE_PATCH, apply=True)
                result = self.snapshot(source)
                proof = verify_profile_keep_alive(source)
                self.assertEqual(proof["origin"], 47)
                integrate(source, patch=PROFILE_KEEP_ALIVE_PATCH, apply=True)
                self.assertEqual(self.snapshot(source), result)
                integrate(source, patch=PROFILE_KEEP_ALIVE_PATCH, revert=True)
                final = self.snapshot(source)
                self.assertEqual({k:v[0] for k,v in final.items()},
                                 {k:v[0] for k,v in original.items()})
                for name in ("out/Default/retained.obj", "existing-profile/Default/Preferences"):
                    self.assertEqual(final[name], original[name])

    def test_partial_or_conflicting_ports_do_not_change_any_source(self):
        for conflict in ("partial", "changed-enum"):
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp)
                self.fixture(source)
                integrate(source, patch=PROFILE_KEEP_ALIVE_PATCH, apply=True)
                if conflict == "partial":
                    path = source / PROFILE_KEEP_ALIVE_METRICS
                    path.write_bytes(path.read_bytes().replace(
                        b'  <int value="47" label="kArciumSettingsWindow"/>\n', b"", 1))
                else:
                    path = source / HEADER
                    path.write_bytes(path.read_bytes().replace(
                        b"kArciumSettingsWindow = 47", b"kArciumSettingsWindow = 48", 1))
                changed = self.snapshot(source)
                with self.assertRaisesRegex(RuntimeError, "No changes made"):
                    integrate(source, patch=PROFILE_KEEP_ALIVE_PATCH, apply=True)
                self.assertEqual(self.snapshot(source), changed)

    def test_consumer_reference_is_checked_against_the_actual_enum(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            self.fixture(source)
            integrate(source, patch=PROFILE_KEEP_ALIVE_PATCH, apply=True)
            consumer = source / "consumer.cc"
            consumer.write_text("auto origin = ProfileKeepAliveOrigin::kArciumSettingsWindow;")
            self.assertEqual(verify_profile_keep_alive(
                source, consumers=("consumer.cc",))["consumer_count"], 1)
            consumer.write_text("auto origin = ProfileKeepAliveOrigin::kUnknownProfileOrigin;")
            with self.assertRaisesRegex(RuntimeError, "unresolved reference"):
                verify_profile_keep_alive(source, consumers=("consumer.cc",))

    @unittest.skipUnless(shutil.which("g++") or shutil.which("c++"), "C++ compiler required")
    def test_original_error_is_reproduced_and_corrected_types_compile_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            self.fixture(source)
            before = self.snapshot(source)
            with self.assertRaisesRegex(RuntimeError, "kArciumSettingsWindow"):
                compile_contract(source)
            self.assertEqual(before, self.snapshot(source))
            integrate(source, patch=PROFILE_KEEP_ALIVE_PATCH, apply=True)
            proof = verify_profile_keep_alive(source, compile_cpp=True)
            self.assertEqual(proof["cpp_contract"]["status"], "PROFILE_ORIGIN_CPP_CONTRACT_PASSED")


if __name__ == "__main__":
    unittest.main()
