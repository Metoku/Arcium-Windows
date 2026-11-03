"""Atomic application of the Windows appearance + migration bundle."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.apply_windows_arc_workflow import (
    APPEARANCE_CSS_SOURCE, LEGACY_APPEARANCE_CSS, ROOT,
    appearance_css_addition, integrate, integrate_bundle,
)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / "src"
        (self.source / "chrome").mkdir(parents=True)
        (self.source / "BUILD.gn").write_text("# fixture\n")
        self.catalogs = []
        for index in range(4):
            path = self.source / f"chrome/source{index}.cc"
            path.write_bytes(f"before {index}\r\n".encode())
            patch = root / f"feature{index}.patch"
            patch.write_text(f"--- a/chrome/source{index}.cc\n"
                             f"+++ b/chrome/source{index}.cc\n"
                             f"@@ -1 +1 @@\n-before {index}\n+after {index}\n")
            self.catalogs.append(patch)
        self.catalogs = tuple(self.catalogs)
        self.output = self.source / "out/Default/retained.obj"
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"existing compiled object")
        self.originals = self.snapshot()

    def snapshot(self):
        return {p.relative_to(self.source).as_posix():
                (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.source.rglob("*") if p.is_file()}

    def test_check_rehearses_entire_bundle_without_touching_source(self):
        self.assertEqual(integrate_bundle(self.source, catalogs=self.catalogs), "READY")
        self.assertEqual(self.snapshot(), self.originals)

    def test_failure_in_last_catalog_is_atomic(self):
        (self.source / "chrome/source3.cc").write_bytes(b"local user edit\r\n")
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "No changes made"):
            integrate_bundle(self.source, apply=True, catalogs=self.catalogs)
        self.assertEqual(before, self.snapshot())

    def test_apply_repeat_and_revert_preserve_eol_and_build_output(self):
        self.assertEqual(integrate_bundle(self.source, apply=True,
                                         catalogs=self.catalogs), "APPLIED")
        for i in range(4):
            self.assertEqual((self.source / f"chrome/source{i}.cc").read_bytes(),
                             f"after {i}\r\n".encode())
        after = self.snapshot()
        self.assertEqual(integrate_bundle(self.source, apply=True,
                                         catalogs=self.catalogs), "APPLIED")
        self.assertEqual(after, self.snapshot())
        self.assertEqual(integrate_bundle(self.source, revert=True,
                                         catalogs=self.catalogs), "READY")
        for name, (content, _) in self.originals.items():
            self.assertEqual((self.source / name).read_bytes(), content)
        self.assertEqual(self.snapshot()['out/Default/retained.obj'],
                         self.originals['out/Default/retained.obj'])

    def test_partly_applied_bundle_can_be_completed(self):
        from scripts.apply_windows_arc_workflow import integrate
        integrate(self.source, apply=True, patch=self.catalogs[1])
        self.assertEqual(integrate_bundle(self.source, catalogs=self.catalogs), "READY")
        self.assertEqual(integrate_bundle(self.source, apply=True,
                                         catalogs=self.catalogs), "APPLIED")

    def test_overlapping_catalogs_are_validated_in_the_staged_order(self):
        patch = self.catalogs[1]
        patch.write_text("--- a/chrome/source0.cc\n+++ b/chrome/source0.cc\n"
                         "@@ -1 +1 @@\n-after 0\n+combined\n")
        self.assertEqual(integrate_bundle(self.source, apply=True,
                                         catalogs=self.catalogs), "APPLIED")
        self.assertEqual((self.source / 'chrome/source0.cc').read_bytes(), b'combined\r\n')
        self.assertEqual(integrate_bundle(self.source, revert=True,
                                         catalogs=self.catalogs), "READY")
        self.assertEqual((self.source / 'chrome/source0.cc').read_bytes(), b'before 0\r\n')

    def test_eof_context_insertion_preserves_missing_final_newline(self):
        import difflib
        # Reproduce the real GRIT-footer hunk: insert immediately before the
        # closing root, while the user's existing file has no final newline.
        before = b'<grit-part>\n  <message name="OLD">old</message>\n</grit-part>\n'
        after = before.replace(b"</grit-part>", b'  <message name="NEW">new</message>\n</grit-part>')
        target = self.source / "chrome/source3.cc"
        self.catalogs[3].write_text("".join(difflib.unified_diff(
            before.decode().splitlines(True), after.decode().splitlines(True),
            fromfile="a/chrome/source3.cc", tofile="b/chrome/source3.cc")))
        for style in ("LF", "CRLF", "mixed"):
            with self.subTest(style=style):
                raw = before.removesuffix(b"\n")
                if style == "CRLF": raw = raw.replace(b"\n", b"\r\n")
                if style == "mixed": raw = raw.replace(b"<grit-part>\n", b"<grit-part>\r\n")
                target.write_bytes(raw)
                untouched = self.snapshot()
                self.assertEqual(integrate_bundle(self.source, catalogs=self.catalogs), "READY")
                self.assertEqual(self.snapshot(), untouched)
                self.assertEqual(integrate_bundle(self.source, apply=True, catalogs=self.catalogs), "APPLIED")
                self.assertFalse(target.read_bytes().endswith(b"\n"))
                self.assertIn(b'name="NEW"', target.read_bytes())
                applied = self.snapshot()
                self.assertEqual(integrate_bundle(self.source, apply=True, catalogs=self.catalogs), "APPLIED")
                self.assertEqual(self.snapshot(), applied)
                self.assertEqual(integrate_bundle(self.source, revert=True, catalogs=self.catalogs), "READY")
                self.assertEqual(target.read_bytes(), raw)
                self.assertEqual(self.snapshot()['out/Default/retained.obj'],
                                 self.originals['out/Default/retained.obj'])

    def test_already_applied_files_without_final_newline_are_not_rewritten(self):
        integrate_bundle(self.source, apply=True, catalogs=self.catalogs)
        for i in range(4):
            path = self.source / f"chrome/source{i}.cc"
            path.write_bytes(path.read_bytes().rstrip(b"\r\n"))
        before = self.snapshot()
        self.assertEqual(integrate_bundle(self.source, catalogs=self.catalogs), "APPLIED")
        self.assertEqual(integrate_bundle(self.source, apply=True, catalogs=self.catalogs), "APPLIED")
        self.assertEqual(self.snapshot(), before)
        integrate_bundle(self.source, revert=True, catalogs=self.catalogs)
        for i in range(4):
            self.assertEqual((self.source / f"chrome/source{i}.cc").read_bytes(),
                             f"before {i}".encode())

    def test_error_identifies_catalog_without_dumping_reverse_check(self):
        (self.source / "chrome/source3.cc").write_bytes(b"unrelated user change")
        before = self.snapshot()
        with self.assertRaises(RuntimeError) as caught:
            integrate_bundle(self.source, apply=True, catalogs=self.catalogs)
        message = str(caught.exception)
        self.assertIn("feature3.patch", message)
        self.assertIn(str(self.source.resolve()), message)
        self.assertIn("Forward check:", message)
        self.assertNotIn("arcium-workflow-stage-", message)
        self.assertEqual(before, self.snapshot())

    def test_no_mutually_exclusive_modes(self):
        with self.assertRaises(ValueError):
            integrate_bundle(self.source, apply=True, revert=True,
                             catalogs=self.catalogs)


class AppearanceCSSUpgradeTests(unittest.TestCase):
    def setUp(self):
        import difflib
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "src"
        self.source.mkdir()
        (self.source / "BUILD.gn").write_text("# fixture\n")
        self.css = self.source / APPEARANCE_CSS_SOURCE
        self.css.parent.mkdir(parents=True)
        self.css.write_bytes(b"/* existing CSS */\n")
        self.native = self.source / "chrome/native.cc"
        self.native.write_bytes(b"native before\n")
        self.output = self.source / "out/Default/retained.obj"
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"existing compiled object")
        catalog = ROOT / "patches/windows/arc-appearance-windows.patch"
        self.fixed = appearance_css_addition(catalog.read_bytes())
        self.patch = self.root / "arc-appearance-windows.patch"
        sections = []
        for name, before, after in (
                (APPEARANCE_CSS_SOURCE, b"/* existing CSS */\n",
                 b"/* existing CSS */\n" + self.fixed),
                ("chrome/native.cc", b"native before\n", b"native after\n")):
            sections.extend(difflib.unified_diff(before.decode().splitlines(True),
                after.decode().splitlines(True), fromfile="a/" + name, tofile="b/" + name))
        self.patch.write_text("".join(sections))
        integrate(self.source, patch=self.patch, apply=True)
        self.css.write_bytes(self.css.read_bytes().replace(self.fixed, LEGACY_APPEARANCE_CSS, 1))

    def snapshot(self):
        return {p: (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.source.rglob("*") if p.is_file()}

    def test_known_old_css_upgrades_only_css_and_is_idempotent(self):
        before = self.snapshot()
        self.assertEqual(integrate(self.source, patch=self.patch), "UPDATE_AVAILABLE")
        self.assertEqual(before, self.snapshot())
        self.assertEqual(integrate(self.source, patch=self.patch, apply=True), "APPLIED")
        self.assertIn(self.fixed, self.css.read_bytes())
        for path in before:
            if path != self.css:
                self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before[path])
        after = self.snapshot()
        self.assertEqual(integrate(self.source, patch=self.patch, apply=True), "APPLIED")
        self.assertEqual(after, self.snapshot())

    def test_upgrade_preserves_crlf_mixed_and_absent_eof_format(self):
        for style in ("CRLF", "mixed", "no-eof"):
            with self.subTest(style=style):
                old = b"/* existing CSS */\n" + LEGACY_APPEARANCE_CSS
                if style == "CRLF": old = old.replace(b"\n", b"\r\n")
                if style == "mixed": old = old.replace(b"/* existing CSS */\n", b"/* existing CSS */\r\n")
                if style == "no-eof": old = old.removesuffix(b"\n")
                self.css.write_bytes(old)
                self.assertEqual(integrate(self.source, patch=self.patch, apply=True), "APPLIED")
                result = self.css.read_bytes()
                self.assertEqual(result.endswith(b"\n"), style != "no-eof")
                if style == "CRLF": self.assertNotIn(b"\n", result.replace(b"\r\n", b""))
                if style == "mixed": self.assertTrue(result.startswith(b"/* existing CSS */\r\n"))

    def test_unknown_css_edit_is_rejected_without_writing_source(self):
        self.css.write_bytes(self.css.read_bytes().replace(b"padding: 0 20px", b"padding: 0 21px"))
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "No changes made"):
            integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_incomplete_native_catalog_is_rejected_even_with_known_css(self):
        self.native.write_bytes(b"native before\n")
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "complete appearance catalog"):
            integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_legacy_version_can_be_reverted_after_full_verification(self):
        self.assertEqual(integrate(self.source, patch=self.patch, revert=True), "READY")
        self.assertEqual(self.css.read_bytes(), b"/* existing CSS */\n")
        self.assertEqual(self.native.read_bytes(), b"native before\n")
        self.assertEqual(self.output.read_bytes(), b"existing compiled object")


if __name__ == "__main__":
    unittest.main()
