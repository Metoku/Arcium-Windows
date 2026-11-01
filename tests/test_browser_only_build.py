"""Browser-only compilation guardrails; these tests never compile Chromium."""

import unittest

from scripts.browser_only_build import (
    BROWSER_ONLY_TARGETS, ORIGINAL_RELEASE_TARGETS,
    make_browser_only_builder
)
from scripts.gn_smoke import RESTORE_ANCHOR, RESTORE_STEP
from scripts.windows_version_compat import OLD_VERSION_BLOCK
from scripts.windows_sdk_compat import ORIGINAL_VCVARS_CALL


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
        "    ninja_commandline = []\n"
        + ORIGINAL_RELEASE_TARGETS + "\n"
    )


class BrowserOnlyBuilderTests(unittest.TestCase):
    def test_version_restore_and_browser_only_target(self):
        code = make_browser_only_builder(pinned_fixture())
        self.assertIn("helium_version.refresh_version(", code)
        self.assertIn("ARCIUM_WINDOWS_SDK", code)
        self.assertIn("restore_missing_webui_patch_targets(", code)
        self.assertIn(BROWSER_ONLY_TARGETS, code)
        self.assertNotIn(ORIGINAL_RELEASE_TARGETS, code)
        self.assertNotIn("helium_version.check_existing_version(", code)
        self.assertNotIn("helium_version.append_version(", code)

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
