"""Browser-only compilation guardrails; these tests never compile Chromium."""

import unittest
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from scripts.browser_only_build import (
    BROWSER_ONLY_TARGETS, ORIGINAL_RELEASE_TARGETS,
    first_compiler_failure, make_browser_only_builder, print_diagnostic,
    REQUIRED_NATIVE_CHROMIUM_SDK, require_native_chromium_sdk,
    latest_build_progress, require_compilation_cache, stop_build_tree
)
from scripts.gn_smoke import RESTORE_ANCHOR, RESTORE_STEP
from scripts.windows_version_compat import OLD_VERSION_BLOCK
from scripts.windows_sdk_compat import ORIGINAL_VCVARS_CALL
from scripts.chromium_sdk_pin import SDK_PIN_ANCHOR


def pinned_fixture() -> str:
    return (
        "# Helium build script for Windows\n"
        "def _run_build_process(*args):\n"
        + ORIGINAL_VCVARS_CALL + "\n"
        "def _run_build_process_timeout(*args, **kwargs):\n"
        + ORIGINAL_VCVARS_CALL + "\n"
        "def main():\n"
        "    if True:\n"
        + RESTORE_ANCHOR +
        "            pass\n"
        + OLD_VERSION_BLOCK +
        SDK_PIN_ANCHOR +
        "    ninja_commandline = []\n"
        + ORIGINAL_RELEASE_TARGETS + "\n"
    )


class BrowserOnlyBuilderTests(unittest.TestCase):
    def test_version_restore_and_browser_only_target(self):
        code = make_browser_only_builder(pinned_fixture())
        self.assertIn("helium_version.refresh_version(", code)
        self.assertIn("ARCIUM_WINDOWS_SDK", code)
        self.assertIn("pin_chromium_sdk_version(source_tree", code)
        self.assertIn("restore_missing_webui_patch_targets(", code)
        self.assertIn(BROWSER_ONLY_TARGETS, code)
        self.assertNotIn(ORIGINAL_RELEASE_TARGETS, code)
        self.assertNotIn("helium_version.check_existing_version(", code)
        self.assertNotIn("helium_version.append_version(", code)

    def test_native_compile_requires_reviewed_28000_sdk(self):
        self.assertEqual(REQUIRED_NATIVE_CHROMIUM_SDK, "10.0.28000.0")
        require_native_chromium_sdk("10.0.28000.0")
        with self.assertRaisesRegex(EnvironmentError, "Provision it"):
            require_native_chromium_sdk("10.0.26100.0")
        with self.assertRaisesRegex(EnvironmentError, "28000"):
            require_native_chromium_sdk("10.0.99999.0")

    def test_compilation_progress_uses_last_ninja_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "compiler.log"
            path.write_text(
                "GN generation started\n"
                "[82/93638] CXX first.obj\n"
                "SISO 4h34m status\n"
                "[22400/81338] CXX latest.obj\n",
                encoding="utf-8",
            )
            self.assertEqual(latest_build_progress(path), (22400, 81338))

    def test_compilation_progress_handles_empty_or_missing_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "compiler.log"
            self.assertIsNone(latest_build_progress(path))
            path.write_text("patches and GN are running\n", encoding="utf-8")
            self.assertIsNone(latest_build_progress(path))

    def test_compiler_cache_requirement_must_fail_closed(self):
        with patch("scripts.browser_only_build.shutil.which", return_value=None):
            with self.assertRaisesRegex(EnvironmentError, "Missing sccache"):
                require_compilation_cache()
        with patch("scripts.browser_only_build.shutil.which",
                   return_value="C:/tools/sccache.exe") as which:
            require_compilation_cache()
            which.assert_called_once_with("sccache")

    def test_windows_timeout_kills_child_compilers(self):
        process = Mock()
        process.pid = 1234
        process.poll.return_value = 1
        with patch("scripts.browser_only_build.os.name", "nt"), patch(
            "scripts.browser_only_build.subprocess.run"
        ) as run:
            stop_build_tree(process)
        self.assertEqual(run.call_args.args[0][:4],
                         ["taskkill", "/PID", "1234", "/T"])
        process.kill.assert_not_called()
        process.wait.assert_called_once_with(timeout=30)

    def test_non_windows_timeout_kills_parent(self):
        process = Mock()
        process.poll.return_value = None
        with patch("scripts.browser_only_build.os.name", "posix"):
            stop_build_tree(process)
        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=30)

    def test_windows_legacy_console_can_print_unicode_diagnostics(self):
        # Raw errors remain intact in the diagnostic log and JSON. The
        # console-facing copy must not contain cp1252-unencodable glyphs.
        with patch("builtins.print") as printer:
            print_diagnostic("build failure █ → ∆ 😀")
        argument = printer.call_args.args[0]
        argument.encode("cp1252", errors="strict")
        self.assertIn(r"\u2588", argument)
        self.assertIn(r"\U0001f600", argument)

    def test_extract_first_siso_failure_not_log_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "build.log"
            log.write_text(
                "[1/9] running\n"
                "FAILED: seed_material.obj CXX\n"
                "err: exit=1\n"
                "fileapi.h: error: unknown type name 'FILE_INFO_BY_HANDLE_CLASS'\n"
                "[2/9] another completed target\n"
                + "build status line\n" * 200,
                encoding="utf-8",
            )
            lines = first_compiler_failure(log, limit=3)
            self.assertEqual(len(lines), 3)
            self.assertIn("FAILED: seed_material.obj", lines[0])
            self.assertIn("FILE_INFO_BY_HANDLE_CLASS", lines[2])

    def test_compilation_failure_extractor_handles_no_siso_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "build.log"
            log.write_text("GN failed without Ninja\n", encoding="utf-8")
            self.assertEqual(first_compiler_failure(log), [])

    def test_refuse_unrecognized_release_target_list(self):
        with self.assertRaisesRegex(ValueError, "Ninja target list"):
            make_browser_only_builder(
                pinned_fixture().replace(ORIGINAL_RELEASE_TARGETS, "")
            )

    def test_refuse_patch_injection_absent(self):
        with self.assertRaisesRegex(ValueError, "patch-stage entry"):
            make_browser_only_builder(
                pinned_fixture().replace(RESTORE_ANCHOR, "")
            )

    def test_refuse_duplicate_release_target_command(self):
        with self.assertRaisesRegex(ValueError, "Ninja target list"):
            make_browser_only_builder(
                pinned_fixture() + ORIGINAL_RELEASE_TARGETS + "\n"
            )


if __name__ == "__main__":
    unittest.main()
