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
    GN_ANCHOR, RESTORE_ANCHOR, BUILDER_IDENTIFIER, GN_PYTHON_ANCHOR,
    create_gn_only_builder,
)
from scripts.windows_version_compat import OLD_VERSION_BLOCK
from scripts.windows_sdk_compat import ORIGINAL_VCVARS_CALL
from scripts.chromium_sdk_pin import SDK_PIN_ANCHOR
from scripts.windows_release_integrations import (
    RELEASE_INTEGRATIONS_ANCHOR, RELEASE_INTEGRATIONS_STEP,
)


def upstream_fixture() -> str:
    return (
        '# Helium build script for Windows\n'
        'import os\n'
        'import sys\n'
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
        + RELEASE_INTEGRATIONS_ANCHOR +
        '            (source_tree / "branding.txt").write_text("branded", encoding="utf-8")\n'
        + OLD_VERSION_BLOCK +
        SDK_PIN_ANCHOR +
        '    # Run gn gen\n'
        '    if True:\n'
        '        (source_tree / "out" / "Default" / "build.ninja").write_text(\n'
        '            "rule test\\n", encoding="utf-8")\n'
        '        _run_build_process(\n'
        + GN_PYTHON_ANCHOR + '\n'
        + GN_ANCHOR + ' "/dummy")\n'
        '    raise AssertionError("Ninja must not execute")\n'
    )


class GNAdapterTests(unittest.TestCase):
    def test_release_preparation_applies_all_catalogs_before_branding_and_never_ninja(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'src'
            events = []
            code = create_gn_only_builder(upstream_fixture(), release_candidate=True)
            self.assertEqual(code.count(RELEASE_INTEGRATIONS_STEP), 1)
            self.assertLess(code.index(RELEASE_INTEGRATIONS_STEP),
                            code.index(RELEASE_INTEGRATIONS_ANCHOR))
            namespace = {
                '_ROOT_DIR':root,
                'helium_version':SimpleNamespace(
                    get_version_parts=lambda *args: {'HELIUM_MAJOR':'0'},
                    refresh_version=lambda *args: None),
            }
            exec(compile(code, 'candidate-gn.py', 'exec'), namespace)
            def check_entry(name, path, **kwargs):
                self.assertEqual(path, source)
                self.assertEqual(kwargs.get('apply'), True)
                self.assertFalse((source / 'branding.txt').exists())
                events.append(name)
            def run_gn(*args):
                self.assertTrue((source / 'branding.txt').is_file())
                events.append('gn')
            namespace['_run_build_process'] = run_gn
            with patch('scripts.restore_chromium_fixtures.restore_chromium_test_fixtures'), \
                 patch('scripts.restore_patch_webui_tests.restore_missing_webui_patch_targets'), \
                 patch('scripts.chromium_sdk_pin.pin_chromium_sdk_version'), \
                 patch('scripts.apply_windows_arc_workflow.integrate_bundle',
                       side_effect=lambda path, **kw: check_entry('bundle', path, **kw)), \
                 patch('scripts.apply_windows_arc_workflow.integrate',
                       side_effect=lambda path, **kw: check_entry('mac-buttons', path, **kw)), \
                 patch.dict(os.environ, {'ARCIUM_WINDOWS_SDK':'10.0.28000.0'}):
                namespace['main']()
            self.assertEqual(events, ['bundle', 'mac-buttons', 'gn'])
            self.assertEqual((root / 'ARCIUM_GN_GENERATED.marker').read_text(),
                             'PINNED_WINDOWS_GN_GENERATED\n')

    def test_release_preparation_rejects_a_failed_catalog_before_branding_or_gn(self):
        for failed_catalog in ('bundle', 'mac-buttons'):
            with self.subTest(failed_catalog=failed_catalog), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                namespace = {'_ROOT_DIR':root}
                exec(compile(create_gn_only_builder(upstream_fixture(), release_candidate=True),
                             'candidate-gn.py', 'exec'), namespace)
                gn = Mock()
                namespace['_run_build_process'] = gn
                failure = RuntimeError('catalog conflict')
                with patch('scripts.restore_chromium_fixtures.restore_chromium_test_fixtures'), \
                     patch('scripts.restore_patch_webui_tests.restore_missing_webui_patch_targets'), \
                     patch('scripts.apply_windows_arc_workflow.integrate_bundle',
                           side_effect=failure if failed_catalog == 'bundle' else None), \
                     patch('scripts.apply_windows_arc_workflow.integrate',
                           side_effect=failure if failed_catalog == 'mac-buttons' else None):
                    with self.assertRaisesRegex(RuntimeError, 'catalog conflict'):
                        namespace['main']()
                gn.assert_not_called()
                self.assertFalse((root / 'ARCIUM_GN_GENERATED.marker').exists())
                self.assertFalse((root / 'src/branding.txt').exists())

    def test_release_preparation_rejects_missing_or_duplicate_branding_entry(self):
        for fixture in (upstream_fixture().replace(RELEASE_INTEGRATIONS_ANCHOR, ''),
                        upstream_fixture() + RELEASE_INTEGRATIONS_ANCHOR):
            with self.assertRaisesRegex(ValueError, 'pre-branding integration'):
                create_gn_only_builder(fixture, release_candidate=True)

    def test_default_gn_mode_does_not_apply_optional_release_integrations(self):
        self.assertNotIn(RELEASE_INTEGRATIONS_STEP, create_gn_only_builder(upstream_fixture()))

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
            self.assertEqual(called[0][-1], '--script-executable=' + sys.executable)
            self.assertTrue((root / "ARCIUM_GN_GENERATED.marker").is_file())
            self.assertEqual(
                (root / "ARCIUM_GN_GENERATED.marker").read_text(encoding="utf-8"),
                "PINNED_WINDOWS_GN_GENERATED\n",
            )

    def test_python_path_with_spaces_is_a_single_explicit_gn_argument(self):
        code = create_gn_only_builder(upstream_fixture())
        self.assertIn("'--script-executable=' + sys.executable", code)
        self.assertNotIn(GN_PYTHON_ANCHOR, code)
        # Execute the inserted command fragment without running GN or a shell.
        calls = []
        from scripts.gn_smoke import GN_PYTHON_PINNED
        executable = r'C:\Program Files\Python314\python.exe'
        with patch.object(sys, 'executable', executable):
            exec('_run_build_process(\n' + GN_PYTHON_PINNED,
                 {'_run_build_process':lambda *args: calls.append(args), 'sys':sys})
        self.assertEqual(calls[0][-1], '--script-executable=' + executable)
        self.assertEqual(len(calls[0]), 5)

    def test_unknown_gn_python_command_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'GN Python invocation'):
            create_gn_only_builder(upstream_fixture().replace(
                "'--fail-on-unused-args'", "'--unknown-option'"))

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
