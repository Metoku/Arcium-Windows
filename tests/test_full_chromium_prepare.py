"""Non-network tests of the full-source Chromium patch preparation adapter."""

from pathlib import Path
import tempfile
import unittest

from scripts.prepare_full_chromium import (
    ANCHOR, generate_prepare_only_script, VERSION_MARKER
)


def sample_upstream_builder() -> str:
    # Preserve reviewed upstream's conditional shape and exact exit anchor.
    return (
        "# Helium build script for Windows\n"
        "from pathlib import Path\n"
        "class FakePatches:\n"
        "    def __init__(self): self.calls = []\n"
        "    def generate_patches_from_series(self, path, resolve=True):\n"
        "        return [path]\n"
        "    def apply_patches(self, patches, source, patch_bin_path=None):\n"
        "        self.calls.append(patches)\n"
        "patches = FakePatches()\n"
        "def main():\n"
        "    if True:\n"
        "        if True:\n"
        "            patches.apply_patches(\n"
        "                patches.generate_patches_from_series('arcium', resolve=True),\n"
        "                None, patch_bin_path=None\n"
        "            )\n"
        "            patches.apply_patches(\n"
        "                patches.generate_patches_from_series('windows', resolve=True),\n"
        "                None, patch_bin_path=None\n"
        "            )\n"
        + ANCHOR +
        "    raise AssertionError('Must not proceed to GN compilation')\n"
    )


class FullPrepareSourceTests(unittest.TestCase):
    def test_adapter_proves_both_patch_calls_before_hard_exit(self):
        generated = generate_prepare_only_script(sample_upstream_builder())
        with tempfile.TemporaryDirectory() as tmp:
            namespace = {"_ROOT_DIR": Path(tmp)}
            exec(compile(generated, "test_preparation.py", "exec"), namespace)
            namespace["main"]()
            self.assertEqual(
                namespace["patches"].calls, [["arcium"], ["windows"]]
            )
            marker = Path(tmp) / "ARCIUM_PATCHES_APPLIED.marker"
            self.assertEqual(
                marker.read_text(encoding="utf-8"),
                "ALL_PINNED_PATCHES_APPLIED\n"
            )

    def test_reject_script_missing_exit_anchor(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            generate_prepare_only_script(
                sample_upstream_builder().replace(ANCHOR, "")
            )

    def test_reject_unexpected_script(self):
        with self.assertRaisesRegex(ValueError, "Unexpected upstream"):
            generate_prepare_only_script(
                sample_upstream_builder().replace(VERSION_MARKER, "Other script")
            )

    def test_reject_duplicate_anchor(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            generate_prepare_only_script(
                sample_upstream_builder() + ANCHOR
            )


if __name__ == "__main__":
    unittest.main()
