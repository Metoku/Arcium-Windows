import difflib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import apply_windows_arc_workflow as workflow
from scripts.apply_windows_arc_workflow import PATCH, integrate, patch_targets


@unittest.skipUnless(shutil.which("git"), "Git is required for patch integration")
class WorkflowPatchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="arc workflow ")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        # Reproduce the user's source tree inside an outer Git repository.
        subprocess.run(["git", "init", "-q", str(self.parent)], check=True)
        self.source = self.parent / "work" / "windows-platform" / "build" / "src"
        self.source.mkdir(parents=True)
        (self.source / "BUILD.gn").write_text("# Chromium\n")
        self.first = self.source / "chrome" / "first.cc"
        self.second = self.source / "chrome" / "second.cc"
        self.first.parent.mkdir()
        self.first.write_text("first original\n")
        self.second.write_text("second original\n")
        self.output = self.source / "out" / "Default" / "completed.obj"
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"existing compiled object")
        self.profile = self.parent / "work" / "arcium-test-profile" / "Preferences"
        self.profile.parent.mkdir()
        self.profile.write_text('{"unrelated":"user settings"}')
        self.patch = self.parent / "workflow.patch"
        patch = ""
        for name in ("first", "second"):
            patch += "".join(difflib.unified_diff(
                [f"{name} original\n"], [f"{name} changed\n"],
                fromfile=f"a/chrome/{name}.cc", tofile=f"b/chrome/{name}.cc"))
        self.patch.write_text(patch)

    def assert_user_data_unchanged(self):
        self.assertEqual(self.output.read_bytes(), b"existing compiled object")
        self.assertEqual(self.profile.read_text(), '{"unrelated":"user settings"}')

    def test_default_check_is_read_only(self):
        before = self.first.stat().st_mtime_ns
        self.assertEqual(integrate(self.source, patch=self.patch), "READY")
        self.assertEqual(self.first.read_text(), "first original\n")
        self.assertEqual(self.first.stat().st_mtime_ns, before)
        self.assert_user_data_unchanged()

    def test_apply_reapply_and_revert_inside_outer_git_repo(self):
        self.assertEqual(integrate(self.source, apply=True, patch=self.patch), "APPLIED")
        self.assertEqual(self.first.read_text(), "first changed\n")
        self.assertEqual(self.second.read_text(), "second changed\n")
        before = self.first.stat().st_mtime_ns
        self.assertEqual(integrate(self.source, apply=True, patch=self.patch), "APPLIED")
        self.assertEqual(self.first.stat().st_mtime_ns, before)
        self.assertEqual(integrate(self.source, revert=True, patch=self.patch), "READY")
        self.assertEqual(self.first.read_text(), "first original\n")
        self.assertEqual(self.second.read_text(), "second original\n")
        self.assert_user_data_unchanged()

    def test_conflicting_file_leaves_all_other_files_untouched(self):
        self.second.write_text("a local user edit\n")
        with self.assertRaisesRegex(RuntimeError, "No changes made"):
            integrate(self.source, apply=True, patch=self.patch)
        self.assertEqual(self.first.read_text(), "first original\n")
        self.assertEqual(self.second.read_text(), "a local user edit\n")
        self.assert_user_data_unchanged()

    def test_all_patch_and_source_lf_crlf_combinations(self):
        patch_lf = self.patch.read_bytes().replace(b"\r\n", b"\n")
        for source_eol in (b"\n", b"\r\n"):
            for patch_eol in (b"\n", b"\r\n"):
                with self.subTest(source_eol=source_eol, patch_eol=patch_eol):
                    self.first.write_bytes(b"first original" + source_eol)
                    self.second.write_bytes(b"second original" + source_eol)
                    self.patch.write_bytes(patch_lf.replace(b"\n", patch_eol))
                    self.assertEqual(integrate(self.source, patch=self.patch), "READY")
                    self.assertEqual(integrate(self.source, apply=True, patch=self.patch), "APPLIED")
                    self.assertEqual(self.first.read_bytes(), b"first changed" + source_eol)
                    self.assertEqual(self.second.read_bytes(), b"second changed" + source_eol)
                    before = self.first.stat().st_mtime_ns
                    self.assertEqual(integrate(self.source, apply=True, patch=self.patch), "APPLIED")
                    self.assertEqual(self.first.stat().st_mtime_ns, before)
                    self.assertEqual(integrate(self.source, revert=True, patch=self.patch), "READY")
                    self.assertEqual(self.first.read_bytes(), b"first original" + source_eol)
                    self.assertEqual(self.second.read_bytes(), b"second original" + source_eol)
                    self.assert_user_data_unchanged()

    def test_mixed_target_endings_are_read_only_during_check_and_preserved_on_apply(self):
        self.first.write_bytes(b"first original\r\n")
        self.second.write_bytes(b"second original\n")
        self.patch.write_bytes(self.patch.read_bytes().replace(b"\r\n", b"\n")
                               .replace(b"\n", b"\r\n"))
        before = [self.first.stat().st_mtime_ns, self.second.stat().st_mtime_ns]
        self.assertEqual(integrate(self.source, patch=self.patch), "READY")
        self.assertEqual(self.first.read_bytes(), b"first original\r\n")
        self.assertEqual(self.second.read_bytes(), b"second original\n")
        self.assertEqual([self.first.stat().st_mtime_ns, self.second.stat().st_mtime_ns], before)
        integrate(self.source, apply=True, patch=self.patch)
        self.assertEqual(self.first.read_bytes(), b"first changed\r\n")
        self.assertEqual(self.second.read_bytes(), b"second changed\n")
        integrate(self.source, revert=True, patch=self.patch)
        self.assertEqual(self.first.read_bytes(), b"first original\r\n")
        self.assertEqual(self.second.read_bytes(), b"second original\n")
        self.assert_user_data_unchanged()

    def test_io_failure_restores_already_written_source(self):
        originals = [self.first.read_bytes(), self.second.read_bytes()]
        original_write = workflow.atomic_write

        def failing_write(path, data):
            if path == self.second:
                raise OSError("injected write failure")
            return original_write(path, data)

        with mock.patch.object(workflow, "atomic_write", side_effect=failing_write):
            with self.assertRaisesRegex(RuntimeError, "previously written files were restored"):
                integrate(self.source, apply=True, patch=self.patch)
        self.assertEqual([self.first.read_bytes(), self.second.read_bytes()], originals)
        self.assert_user_data_unchanged()

    def test_edit_during_staging_prevents_source_commit(self):
        original_git_apply = workflow.git_apply

        def concurrent_edit(*args, **kwargs):
            result = original_git_apply(*args, **kwargs)
            if not kwargs["check"]:
                self.second.write_bytes(b"a concurrent source edit\n")
            return result

        with mock.patch.object(workflow, "git_apply", side_effect=concurrent_edit):
            with self.assertRaisesRegex(RuntimeError, "Source changed during patch validation"):
                integrate(self.source, apply=True, patch=self.patch)
        self.assertEqual(self.first.read_text(), "first original\n")
        self.assertEqual(self.second.read_bytes(), b"a concurrent source edit\n")
        self.assert_user_data_unchanged()

    def test_inherited_git_work_tree_does_not_redirect_edits(self):
        original = os.environ.get("GIT_WORK_TREE")
        os.environ["GIT_WORK_TREE"] = str(self.parent)
        try:
            self.assertEqual(integrate(self.source, apply=True, patch=self.patch), "APPLIED")
        finally:
            if original is None:
                os.environ.pop("GIT_WORK_TREE", None)
            else:
                os.environ["GIT_WORK_TREE"] = original
        self.assertEqual(self.first.read_text(), "first changed\n")

    @unittest.skipIf(os.name == "nt", "Symlink creation may require Windows privileges")
    def test_rejects_symlink_escape(self):
        outside = self.parent / "outside.cc"
        outside.write_text("first original\n")
        self.first.unlink()
        self.first.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "escapes"):
            integrate(self.source, apply=True, patch=self.patch)
        self.assertEqual(outside.read_text(), "first original\n")


class WorkflowCatalogTests(unittest.TestCase):
    def test_mixed_line_file_retains_unchanged_bytes(self):
        original = b"header LF\nline CRLF\r\nold value\r\nfooter LF\n"
        changed = b"header LF\nline CRLF\nnew value\nfooter LF\n"
        result = workflow.preserve_line_endings(original, changed)
        self.assertTrue(result.startswith(b"header LF\nline CRLF\r\n"))
        self.assertTrue(result.endswith(b"footer LF\n"))
        self.assertEqual(result.replace(b"\r\n", b"\n"), changed)
        self.assertEqual(workflow.preserve_line_endings(original,
                         original.replace(b"\r\n", b"\n")), original)

    def test_catalog_edits_only_existing_chromium_ui_files(self):
        targets = patch_targets(PATCH.read_text())
        self.assertGreater(len(targets), 4)
        self.assertTrue(all(path.startswith("chrome/") for path in targets))

    def test_rejects_traversal_and_new_file_sections(self):
        for target in ("../escape", "chrome/../../escape", "D:/escape", "out/Default/args.gn"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                patch_targets(f"--- a/{target}\n+++ b/{target}\n")
        with self.assertRaises(ValueError):
            patch_targets("--- a/chrome/a\n+++ b/chrome/a\n"
                          "--- /dev/null\n+++ b/chrome/new\n")

    def test_windows_preset_has_no_meta_keys_or_internal_key_collisions(self):
        text = PATCH.read_text()
        table = text.split("+constexpr ArcWindowsShortcut kArcWindowsShortcuts[] = {", 1)[1].split("+};", 1)[0]
        entries = re.findall(r'\{(IDC_\w+), "([^"]+)"\}', table)
        commands, keys = zip(*entries)
        self.assertEqual(len(commands), len(set(commands)))
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all("Meta" not in key for key in keys))
        mappings = dict(entries)
        self.assertEqual(mappings["IDC_ARCIUM_TOGGLE_SPACE_PIN"], "Control+KeyD")
        self.assertEqual(mappings["IDC_TOGGLE_VERTICAL_TABS_COLLAPSE"], "Control+KeyS")
        self.assertEqual(mappings["IDC_ARCIUM_SELECT_SPACE_1"], "Alt+Digit1")
        self.assertNotIn("IDC_CLOSE_WINDOW", mappings)


if __name__ == "__main__":
    unittest.main()
