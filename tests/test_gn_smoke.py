"""Offline tests of the pinned Windows build script GN-only exit adapter."""

import os
import sys
import types
from unittest.mock import Mock, patch
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest

from scripts.gn_smoke import (
    GN_ANCHOR, RESTORE_ANCHOR, BUILDER_IDENTIFIER, create_gn_only_builder
)
from scripts.windows_version_compat import OLD_VERSION_BLOCK
from scripts.windows_sdk_compat import ORIGINAL_VCVARS_CALL
from scripts.chromium_sdk_pin import SDK_PIN_ANCHOR


def upstream_fixture() -> str:
    return (
        '# Helium build script for Windows\n'
        'import os\n'
        'from pathlib import Path\n'
        'from types import SimpleNamespace\n'
        'def _run_build_process(*args):\n'
        + ORIGINAL_VCVARS_CALL + '\n'
        'def _run_build_process_timeout(*args, **kwargs):\n'
        + ORIGINAL_VCVARS_CALL + '\n'
        'def main():\n'
        '    source_tree = _ROOT_DIR / "src"\n'
        '    args = SimpleNamespace(dev=False)\n'
        '    (source_tree / "out" / "Default").mkdir(parents=True, exist_ok=True)\n'
        '    (source_tree / "chrome").mkdir(parents=True, exist_ok=True)\n'
        '    (source_tree / "chrome" / "VERSION").write_text("MAJOR=156\\n", encoding="utf-8")\n'
        '    if True:\n'
        + RESTORE_ANCHOR +
        '            # patches.generate_patches_from_series (unit fixture)\n'
        '            pass\n'
        + OLD_VERSION_BLOCK +
        SDK_PIN_ANCHOR +
        '    # Run gn gen\n'
        '    if True:\n'
        '        (source_tree / "out" / "Default" / "build.ninja").write_text(\n'
        '            "rule test\\n", encoding="utf-8")\n'
        '        _run_build_process("buildtools\\\\win\\\\gn.exe", "gen", "out\\\\Default")\n'
        + GN_ANCHOR + ' "/dummy")\n'
        '    raise AssertionError("Ninja must not execute")\n'
    )


class GNAdapterTests(unittest.TestCase):
    def test_exit_after_gn_before_ninja(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            called = []
            code = create_gn_only_builder(upstream_fixture())
            versions = []
            namespace = {
                "_ROOT_DIR": root,
                "_run_build_process": lambda *args: called.append(args),
                "helium_version": SimpleNamespace(
                    get_version_parts=lambda *args: {"HELIUM_MAJOR": "0"},
                    refresh_version=lambda path, parts: (
                        versions.append((path, parts)),
                        path.write_text(
                            path.read_text(encoding="utf-8") +
                            "HELIUM_MAJOR=0\\n", encoding="utf-8"
                        )
                    )
                ),
            }
            exec(compile(code, "generated_builder.py", "exec"), namespace)
            # The fixture declares both pinned vcvars functions for static
            # rewriting; intercept the later GN call in this offline test.
            namespace["_run_build_process"] = lambda *args: called.append(args)
            module = types.ModuleType("scripts.restore_chromium_fixtures")
            restore_mock = Mock()
            module.restore_chromium_test_fixtures = restore_mock
            additional = types.ModuleType("scripts.restore_patch_webui_tests")
            additional_mock = Mock()
            additional.restore_missing_webui_patch_targets = additional_mock
            sdk_module = types.ModuleType("scripts.chromium_sdk_pin")
            sdk_mock = Mock()
            sdk_module.pin_chromium_sdk_version = sdk_mock
            with patch.dict(sys.modules, {
                "scripts.restore_chromium_fixtures": module,
                "scripts.restore_patch_webui_tests": additional,
                "scripts.chromium_sdk_pin": sdk_module,
            }), patch.dict(os.environ, {"ARCIUM_WINDOWS_SDK": "10.0.26100.0"}):
                namespace["main"]()
            sdk_mock.assert_called_once_with(root / "src", "10.0.26100.0")
            restore_mock.assert_called_once_with(root / "src")
            additional_mock.assert_called_once_with(
                root / "src", root / "helium-chromium" / "patches"
            )
            self.assertEqual(versions[0][1], {"HELIUM_MAJOR": "0"})
            self.assertEqual(len(versions), 1)
            self.assertEqual(len(called), 1)
            self.assertTrue((root / "ARCIUM_GN_GENERATED.marker").is_file())
            self.assertEqual(
                (root / "ARCIUM_GN_GENERATED.marker").read_text(encoding="utf-8"),
                "PINNED_WINDOWS_GN_GENERATED\n",
            )

    def test_reject_missing_source_sdk_injection_anchor(self):
        with self.assertRaisesRegex(ValueError, "pre-GN source entry"):
            create_gn_only_builder(
                upstream_fixture().replace(SDK_PIN_ANCHOR, "")
            )

    def test_reject_missing_gn_anchor(self):
        with self.assertRaisesRegex(ValueError, "Expected one"):
            create_gn_only_builder(upstream_fixture().replace(GN_ANCHOR, ""))

    def test_reject_missing_fixture_injection_point(self):
        with self.assertRaisesRegex(ValueError, "Chromium patch-stage entry"):
            create_gn_only_builder(
                upstream_fixture().replace(RESTORE_ANCHOR, "")
            )

    def test_reject_unknown_builder(self):
        with self.assertRaisesRegex(ValueError, "Unexpected Windows builder"):
            create_gn_only_builder(
                upstream_fixture().replace(BUILDER_IDENTIFIER, "Unknown builder")
            )

    def test_reject_missing_patch_stage(self):
        with self.assertRaisesRegex(ValueError, "patch stage missing"):
            create_gn_only_builder(
                upstream_fixture().replace("patches.generate_patches_from_series", "")
            )

    def test_reject_duplicate_gn_gate(self):
        with self.assertRaisesRegex(ValueError, "Expected one"):
            create_gn_only_builder(upstream_fixture() + GN_ANCHOR)


if __name__ == "__main__":
    unittest.main()
