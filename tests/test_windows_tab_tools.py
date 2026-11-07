"""Cleanup lifecycle contracts and atomic patch application regressions."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts.apply_windows_arc_workflow import TAB_TOOLS_PATCH, integrate, main, patch_targets
from scripts.check_windows_tab_tools import REGION, compile_contract
from tests.test_windows_extension_services import hunk_preimages


def added_cpp():
    content = TAB_TOOLS_PATCH.read_text(encoding="utf-8")
    first = content.split("--- a/", 2)[1]
    return "\n".join(line[1:] for line in first.splitlines()
                     if line.startswith("+") and not line.startswith("+++"))


class SidebarTabToolsTests(unittest.TestCase):
    def fixture(self, root, style="LF"):
        for index, (name, data) in enumerate(hunk_preimages(
                TAB_TOOLS_PATCH.read_text(encoding="utf-8")).items()):
            if style == "CRLF" or (style == "mixed" and index % 2):
                data = data.replace(b"\n", b"\r\n")
            if style == "missing-final-newline":
                data = data.removesuffix(b"\n")
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (root / "BUILD.gn").write_bytes(b"# partial transaction fixture\n")
        for name in ("out/Default/retained.obj", "profile/Default/Preferences"):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"user data or existing compiled output")

    @staticmethod
    def snapshot(root):
        return {p.relative_to(root).as_posix():(p.read_bytes(), p.stat().st_mtime_ns)
                for p in root.rglob("*") if p.is_file()}

    def test_catalog_writes_only_five_existing_native_inputs(self):
        self.assertEqual(set(patch_targets(TAB_TOOLS_PATCH.read_text())), {
            REGION, REGION.removesuffix(".cc") + ".h", "chrome/browser/ui/helium/arcium_settings_prefs.h",
            "chrome/browser/ui/browser_ui_prefs.cc", "chrome/app/settings_strings.grdp"})

    def test_apply_check_reapply_revert_retains_objects_and_profiles(self):
        for style in ("LF", "CRLF", "mixed", "missing-final-newline"):
            with self.subTest(style=style), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.fixture(root, style)
                before = self.snapshot(root)
                self.assertEqual(integrate(root, patch=TAB_TOOLS_PATCH), "READY")
                self.assertEqual(before, self.snapshot(root))
                integrate(root, patch=TAB_TOOLS_PATCH, apply=True)
                applied = self.snapshot(root)
                self.assertEqual(integrate(root, patch=TAB_TOOLS_PATCH, apply=True), "APPLIED")
                self.assertEqual(applied, self.snapshot(root))
                integrate(root, patch=TAB_TOOLS_PATCH, revert=True)
                after = self.snapshot(root)
                self.assertEqual({n:v[0] for n,v in before.items()},
                                 {n:v[0] for n,v in after.items()})
                for name in ("out/Default/retained.obj", "profile/Default/Preferences"):
                    self.assertEqual(before[name], after[name])

    def test_conflict_rejects_the_whole_catalog_without_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            path = root / "chrome/browser/ui/helium/arcium_settings_prefs.h"
            path.write_bytes(path.read_bytes().replace(b"kSharedPalettePref", b"unknown_local_edit"))
            before = self.snapshot(root)
            with self.assertRaisesRegex(RuntimeError, "No changes made"):
                integrate(root, patch=TAB_TOOLS_PATCH, apply=True)
            self.assertEqual(before, self.snapshot(root))

    def test_cli_defaults_to_read_only_then_applies_the_approved_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            args = ["apply_windows_arc_workflow", "--source-dir", str(root),
                    "--feature", "tab-tools"]
            before = self.snapshot(root)
            with patch("sys.argv", args), patch("builtins.print"):
                self.assertEqual(main(), 0)
            self.assertEqual(before, self.snapshot(root))
            with patch("sys.argv", [*args, "--apply"]), patch("builtins.print"):
                self.assertEqual(main(), 0)
            self.assertIn(b"ArciumSidebarTabToolsView", (root / REGION).read_bytes())

    def test_release_xml_declaration_and_removed_comment_do_not_break_the_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            path = root / "chrome/app/settings_strings.grdp"
            body = path.read_bytes().split(b"<grit-part>", 1)[1]
            # The real pinned builder uses single quotes in its declaration
            # and removes XML comments. Full replay also runs that builder utility.
            path.write_bytes(b"<?xml version='1.0' encoding='utf-8'?>\n<grit-part>" + body)
            before = self.snapshot(root)
            self.assertEqual(integrate(root, patch=TAB_TOOLS_PATCH), "READY")
            integrate(root, patch=TAB_TOOLS_PATCH, apply=True)
            self.assertTrue(path.read_bytes().startswith(b"<?xml version='1.0'"))
            applied = self.snapshot(root)
            integrate(root, patch=TAB_TOOLS_PATCH, apply=True)
            self.assertEqual(applied, self.snapshot(root))
            integrate(root, patch=TAB_TOOLS_PATCH, revert=True)
            self.assertEqual({n:v[0] for n,v in before.items()},
                             {n:v[0] for n,v in self.snapshot(root).items()})

    @unittest.skipUnless(shutil.which("g++") or shutil.which("c++"), "C++ compiler required")
    def test_actual_cleanup_code_protects_tabs_and_handles_reentrant_mutations(self):
        report = compile_contract(added_cpp())
        self.assertEqual(report["protected_state_cases"], 36)
        self.assertEqual(report["reentrant_close_cases"], 7)


if __name__ == "__main__":
    unittest.main()
