"""Offline tests of the pinned Windows build script GN-only exit adapter."""

import os
from pathlib import Path
import tempfile
import unittest

from scripts.gn_smoke import (
    GN_ANCHOR, BUILDER_IDENTIFIER, create_gn_only_builder
)


def upstream_fixture() -> str:
    return (
        '# Helium build script for Windows\n'
        'import os\n'
        'from pathlib import Path\n'
        'def main():\n'
        '    source_tree = _ROOT_DIR / "src"\n'
        '    (source_tree / "out" / "Default").mkdir(parents=True, exist_ok=True)\n'
        '    # patches.generate_patches_from_series (unit fixture)\n'
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
            namespace = {
                "_ROOT_DIR": root,
                "_run_build_process": lambda *args: called.append(args),
            }
            exec(compile(code, "generated_builder.py", "exec"), namespace)
            namespace["main"]()
            self.assertEqual(len(called), 1)
            self.assertTrue((root / "ARCIUM_GN_GENERATED.marker").is_file())
            self.assertEqual(
                (root / "ARCIUM_GN_GENERATED.marker").read_text(encoding="utf-8"),
                "PINNED_WINDOWS_GN_GENERATED\n",
            )

    def test_reject_missing_gn_anchor(self):
        with self.assertRaisesRegex(ValueError, "Expected one"):
            create_gn_only_builder(upstream_fixture().replace(GN_ANCHOR, ""))

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
