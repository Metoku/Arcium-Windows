"""Atomic application of the Windows appearance + migration bundle."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.apply_windows_arc_workflow import (
    APPEARANCE_CSS_SOURCE, APPEARANCE_LAYOUT_TEMPLATE, LEGACY_APPEARANCE_CSS, ROOT,
    LEGACY_SURFACE_LABEL, SURFACE_LABEL,
    APPEARANCE_SNAPSHOT_SOURCES, LEGACY_SNAPSHOT_SIGNATURE, SNAPSHOT_SIGNATURE,
    APPEARANCE_FRAME_SOURCE, LEGACY_FRAME_GRADIENT, FRAME_GRADIENT,
    APPEARANCE_CUSTOMIZE_UI_SOURCE, LEGACY_SETTINGS_STRINGS_INCLUDE,
    GENERATED_RESOURCES_INCLUDE, LEGACY_CLOSE_WORKSPACE_STRING, CLOSE_WORKSPACE_STRING,
    APPEARANCE_CAPTURE_SOURCE, LEGACY_WINDOW_TYPE_CHECK, WINDOW_TYPE_CHECK,
    APPEARANCE_COLOR_PICKER_SOURCE, LEGACY_DARK_COLOR_CHECK, DARK_COLOR_CHECK,
    appearance_css_addition, git_apply, integrate, integrate_bundle,
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


class AppearanceHandlerUpgradeTests(unittest.TestCase):
    def setUp(self):
        import difflib
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "src"
        self.source.mkdir()
        (self.source / "BUILD.gn").write_text("# fixture\n")
        self.patch = self.source.parent / "arc-appearance-windows.patch"
        catalog = ROOT / "patches/windows/arc-appearance-windows.patch"
        css = b"/* existing */\n" + appearance_css_addition(catalog.read_bytes())
        self.corrected = {
            APPEARANCE_CSS_SOURCE: css,
            "chrome/browser/resources/side_panel/customize_chrome/app.ts":
                b"class App {\n  onWorkspaceAppearanceClick_() {}\n  onCloseWorkspacePanelClick_() {}\n}\n",
            "chrome/browser/resources/side_panel/customize_chrome/app.html.ts":
                b'html`<button @click="${this.onWorkspaceAppearanceClick_}"></button>\n'
                b'<button @click="${this.onCloseWorkspacePanelClick_}"></button>`;\n',
            "chrome/native.cc": b"native after\n",
            APPEARANCE_LAYOUT_TEMPLATE: b"// template\nhtml`" + SURFACE_LABEL + b"`;\n// footer\n",
        }
        self.baseline = {name:b"original\n" for name in self.corrected}
        self.baseline[APPEARANCE_CSS_SOURCE] = b"/* existing */\n"
        sections = []
        for name, data in self.corrected.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            sections.extend(difflib.unified_diff(self.baseline[name].decode().splitlines(True),
                data.decode().splitlines(True), fromfile="a/" + name, tofile="b/" + name))
        self.patch.write_text("".join(sections))
        self.output = self.source / "out/Default/retained.obj"
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"retained object")
        for name in self.corrected:
            path = self.source / name
            path.write_bytes(path.read_bytes().replace(b"onWorkspaceAppearanceClick_", b"onWorkspaceAppearance_")
                             .replace(b"onCloseWorkspacePanelClick_", b"onCloseWorkspacePanel_")
                             .replace(SURFACE_LABEL, LEGACY_SURFACE_LABEL))

    def snapshot(self):
        return {path:(path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.source.rglob("*") if path.is_file()}

    def test_installed_handlers_upgrade_together_and_preserve_native_output(self):
        before = self.snapshot()
        self.assertEqual(integrate(self.source, patch=self.patch), "UPDATE_AVAILABLE")
        self.assertEqual(before, self.snapshot())
        integrate(self.source, patch=self.patch, apply=True)
        for name, data in self.corrected.items():
            path = self.source / name
            self.assertEqual(path.read_bytes(), data)
            if not name.endswith(".ts"):
                self.assertEqual((data, path.stat().st_mtime_ns), before[path])
        after = self.snapshot()
        integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(after, self.snapshot())
        self.assertEqual(before[self.output], after[self.output])

    def test_unknown_source_edit_is_rejected_atomically(self):
        path = self.source / "chrome/native.cc"
        path.write_bytes(b"user edited native source\n")
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "complete appearance catalog"):
            integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_combined_old_css_and_handler_upgrade(self):
        path = self.source / APPEARANCE_CSS_SOURCE
        path.write_bytes(b"/* existing */\n" + LEGACY_APPEARANCE_CSS)
        self.assertEqual(integrate(self.source, patch=self.patch, apply=True), "APPLIED")
        for name, data in self.corrected.items():
            self.assertEqual((self.source / name).read_bytes(), data)

    def test_installed_old_handlers_can_be_reverted(self):
        self.assertEqual(integrate(self.source, patch=self.patch, revert=True), "READY")
        for name, data in self.baseline.items():
            self.assertEqual((self.source / name).read_bytes(), data)
        self.assertEqual(self.output.read_bytes(), b"retained object")

    def test_latest_installed_template_only_upgrade_preserves_other_sources(self):
        for style in ("LF", "CRLF", "mixed", "no-eof"):
            with self.subTest(style=style):
                for name, data in self.corrected.items():
                    (self.source / name).write_bytes(data)
                path = self.source / APPEARANCE_LAYOUT_TEMPLATE
                old = self.corrected[APPEARANCE_LAYOUT_TEMPLATE].replace(SURFACE_LABEL, LEGACY_SURFACE_LABEL)
                if style in ("CRLF", "mixed"):
                    old = old.replace(b"\n", b"\r\n")
                if style == "mixed": old = old.replace(b"// template\r\n", b"// template\n")
                if style == "no-eof": old = old.removesuffix(b"\n")
                path.write_bytes(old)
                before = self.snapshot()
                self.assertEqual(integrate(self.source, patch=self.patch), "UPDATE_AVAILABLE")
                self.assertEqual(before, self.snapshot())
                self.assertEqual(integrate(self.source, patch=self.patch, apply=True), "APPLIED")
                self.assertEqual(path.read_bytes(), old.replace(LEGACY_SURFACE_LABEL, SURFACE_LABEL))
                after = self.snapshot()
                for file in before:
                    if file != path: self.assertEqual(before[file], after[file])
                integrate(self.source, patch=self.patch, apply=True)
                self.assertEqual(after, self.snapshot())

    def test_unknown_template_edit_prevents_all_source_writes(self):
        path = self.source / APPEARANCE_LAYOUT_TEMPLATE
        path.write_bytes(path.read_bytes().replace(b"toUpperCase", b"toLowerCase"))
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "complete appearance catalog"):
            integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(before, self.snapshot())


class AppearanceSnapshotUpgradeTests(unittest.TestCase):
    def setUp(self):
        import difflib
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "src"
        self.source.mkdir()
        (self.source / "BUILD.gn").write_text("# fixture\n")
        header, cpp = APPEARANCE_SNAPSHOT_SOURCES
        fixed_css = appearance_css_addition(
            (ROOT / "patches/windows/arc-appearance-windows.patch").read_bytes())
        self.corrected = {
            APPEARANCE_CSS_SOURCE:b"/* existing */\n" + fixed_css,
            header:b"// header\n  base::DictValue " + SNAPSHOT_SIGNATURE + b";\n// footer\n",
            cpp:b"// implementation\nbase::DictValue AppearanceHandler::" +
                SNAPSHOT_SIGNATURE + b" {\n  return {};\n}\n// footer\n",
            "chrome/unrelated.cc":b"unrelated feature applied\n",
        }
        self.originals = {name:b"original\n" for name in self.corrected}
        self.originals[APPEARANCE_CSS_SOURCE] = b"/* existing */\n"
        sections = []
        for name, data in self.corrected.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            sections.extend(difflib.unified_diff(self.originals[name].decode().splitlines(True),
                data.decode().splitlines(True), fromfile="a/" + name, tofile="b/" + name))
        self.patch = self.source.parent / "arc-appearance-windows.patch"
        self.patch.write_text("".join(sections))
        self.output = self.source / "out/Default/retained.obj"
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"retained compiled output")
        self.install_previous()

    def install_previous(self, style="LF"):
        for name in APPEARANCE_SNAPSHOT_SOURCES:
            data = self.corrected[name].replace(SNAPSHOT_SIGNATURE, LEGACY_SNAPSHOT_SIGNATURE)
            if style in ("CRLF", "mixed"):
                data = data.replace(b"\n", b"\r\n")
            if style == "mixed":
                data = data.replace(b"// header\r\n", b"// header\n").replace(
                    b"// implementation\r\n", b"// implementation\n")
            if style == "no-eof": data = data.removesuffix(b"\n")
            (self.source / name).write_bytes(data)

    def snapshot(self):
        return {path:(path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.source.rglob("*") if path.is_file()}

    def test_previous_snapshot_pair_upgrades_without_touching_other_outputs(self):
        for style in ("LF", "CRLF", "mixed", "no-eof"):
            with self.subTest(style=style):
                self.install_previous(style)
                before = self.snapshot()
                self.assertEqual(integrate(self.source, patch=self.patch), "UPDATE_AVAILABLE")
                self.assertEqual(before, self.snapshot())
                self.assertEqual(integrate(self.source, patch=self.patch, apply=True), "APPLIED")
                for path, (data, stamp) in before.items():
                    name = path.relative_to(self.source).as_posix()
                    if name in APPEARANCE_SNAPSHOT_SOURCES:
                        self.assertEqual(path.read_bytes(), data.replace(
                            LEGACY_SNAPSHOT_SIGNATURE, SNAPSHOT_SIGNATURE))
                    else:
                        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), (data, stamp))
                after = self.snapshot()
                integrate(self.source, patch=self.patch, apply=True)
                self.assertEqual(after, self.snapshot())

    def test_unknown_native_edit_rejects_both_signature_updates_atomically(self):
        path = self.source / APPEARANCE_SNAPSHOT_SOURCES[1]
        path.write_bytes(path.read_bytes().replace(b"return {};", b"return local_value;"))
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "complete appearance catalog"):
            integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_previous_snapshot_version_can_be_reverted(self):
        self.assertEqual(integrate(self.source, patch=self.patch, revert=True), "READY")
        for name, data in self.originals.items():
            self.assertEqual((self.source / name).read_bytes(), data)
        self.assertEqual(self.output.read_bytes(), b"retained compiled output")


class AppearanceFrameUpgradeTests(unittest.TestCase):
    def setUp(self):
        import difflib
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "src"
        self.source.mkdir()
        (self.source / "BUILD.gn").write_text("# fixture\n")
        fixed_css = appearance_css_addition(
            (ROOT / "patches/windows/arc-appearance-windows.patch").read_bytes())
        self.corrected = {
            APPEARANCE_CSS_SOURCE:b"/* existing */\n" + fixed_css,
            APPEARANCE_FRAME_SOURCE:b"// frame\n" + FRAME_GRADIENT + b"// footer\n",
            "chrome/unrelated.cc":b"unrelated feature applied\n",
        }
        self.originals = {name:b"original\n" for name in self.corrected}
        self.originals[APPEARANCE_CSS_SOURCE] = b"/* existing */\n"
        sections = []
        for name, data in self.corrected.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            sections.extend(difflib.unified_diff(self.originals[name].decode().splitlines(True),
                data.decode().splitlines(True), fromfile="a/" + name, tofile="b/" + name))
        self.patch = self.source.parent / "arc-appearance-windows.patch"
        self.patch.write_text("".join(sections))
        self.frame = self.source / APPEARANCE_FRAME_SOURCE
        self.frame.write_bytes(self.corrected[APPEARANCE_FRAME_SOURCE].replace(
            FRAME_GRADIENT, LEGACY_FRAME_GRADIENT))
        self.output = self.source / "out/Default/retained.obj"
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"retained object")

    def snapshot(self):
        return {path:(path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.source.rglob("*") if path.is_file()}

    def test_frame_only_upgrade_preserves_unrelated_files_and_source_endings(self):
        for style in ("LF", "CRLF", "mixed", "no-eof"):
            with self.subTest(style=style):
                expected = self.corrected[APPEARANCE_FRAME_SOURCE]
                old = expected.replace(FRAME_GRADIENT, LEGACY_FRAME_GRADIENT)
                if style in ("CRLF", "mixed"):
                    old = old.replace(b"\n", b"\r\n")
                    expected = expected.replace(b"\n", b"\r\n")
                if style == "mixed":
                    old = old.replace(b"// frame\r\n", b"// frame\n")
                    expected = expected.replace(b"// frame\r\n", b"// frame\n")
                if style == "no-eof":
                    old = old.removesuffix(b"\n")
                    expected = expected.removesuffix(b"\n")
                self.frame.write_bytes(old)
                before = self.snapshot()
                self.assertEqual(integrate(self.source, patch=self.patch), "UPDATE_AVAILABLE")
                self.assertEqual(before, self.snapshot())
                self.assertEqual(integrate(self.source, patch=self.patch, apply=True), "APPLIED")
                self.assertEqual(self.frame.read_bytes(), expected)
                after = self.snapshot()
                for path in before:
                    if path != self.frame: self.assertEqual(before[path], after[path])
                integrate(self.source, patch=self.patch, apply=True)
                self.assertEqual(after, self.snapshot())

    def test_unknown_frame_edit_rejects_upgrade_atomically(self):
        self.frame.write_bytes(self.frame.read_bytes().replace(b"// footer", b"// user changed"))
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "complete appearance catalog"):
            integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_old_frame_version_can_be_reverted(self):
        self.assertEqual(integrate(self.source, patch=self.patch, revert=True), "READY")
        for name, data in self.originals.items():
            self.assertEqual((self.source / name).read_bytes(), data)
        self.assertEqual(self.output.read_bytes(), b"retained object")


class AppearanceResourceUpgradeTests(unittest.TestCase):
    def setUp(self):
        import difflib
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "src"
        self.source.mkdir()
        (self.source / "BUILD.gn").write_text("# fixture\n")
        css = appearance_css_addition(
            (ROOT / "patches/windows/arc-appearance-windows.patch").read_bytes())
        # Keep the include outside the changed string hunk, as in the real file.
        original_panel = GENERATED_RESOURCES_INCLUDE + b"// existing component\n" * 12
        self.originals = {
            APPEARANCE_CSS_SOURCE:b"/* existing */\n",
            APPEARANCE_CUSTOMIZE_UI_SOURCE:original_panel,
            "chrome/unrelated.cc":b"native before\n",
        }
        self.corrected = {
            APPEARANCE_CSS_SOURCE:self.originals[APPEARANCE_CSS_SOURCE] + css,
            APPEARANCE_CUSTOMIZE_UI_SOURCE:original_panel + CLOSE_WORKSPACE_STRING + b",\n",
            "chrome/unrelated.cc":b"native after\n",
        }
        sections = []
        for name, data in self.corrected.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            sections.extend(difflib.unified_diff(self.originals[name].decode().splitlines(True),
                data.decode().splitlines(True), fromfile="a/" + name, tofile="b/" + name))
        self.patch = self.source.parent / "arc-appearance-windows.patch"
        # This fixture also goes directly to git_apply(), which expects LF.
        self.patch.write_text("".join(sections), encoding="utf-8", newline="\n")
        self.panel = self.source / APPEARANCE_CUSTOMIZE_UI_SOURCE
        self.output = self.source / "out/Default/retained.obj"
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"retained object")
        self.install_previous()

    def install_previous(self, style="LF", old_label=True):
        old = self.corrected[APPEARANCE_CUSTOMIZE_UI_SOURCE].replace(
            GENERATED_RESOURCES_INCLUDE, GENERATED_RESOURCES_INCLUDE + LEGACY_SETTINGS_STRINGS_INCLUDE)
        if old_label: old = old.replace(CLOSE_WORKSPACE_STRING, LEGACY_CLOSE_WORKSPACE_STRING)
        expected = self.corrected[APPEARANCE_CUSTOMIZE_UI_SOURCE]
        if style in ("CRLF", "mixed"):
            old = old.replace(b"\n", b"\r\n")
            expected = expected.replace(b"\n", b"\r\n")
        if style == "mixed":
            old = old.replace(b"// existing component\r\n", b"// existing component\n", 1)
            expected = expected.replace(b"// existing component\r\n", b"// existing component\n", 1)
        if style == "no-eof":
            old = old.removesuffix(b"\n")
            expected = expected.removesuffix(b"\n")
        self.panel.write_bytes(old)
        return expected

    def snapshot(self):
        return {path:(path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.source.rglob("*") if path.is_file()}

    def test_previous_panel_resources_upgrade_without_touching_other_outputs(self):
        for style in ("LF", "CRLF", "mixed", "no-eof"):
            with self.subTest(style=style):
                expected = self.install_previous(style)
                before = self.snapshot()
                self.assertEqual(integrate(self.source, patch=self.patch), "UPDATE_AVAILABLE")
                self.assertEqual(before, self.snapshot())
                self.assertEqual(integrate(self.source, patch=self.patch, apply=True), "APPLIED")
                self.assertEqual(self.panel.read_bytes(), expected)
                after = self.snapshot()
                for path in before:
                    if path != self.panel: self.assertEqual(before[path], after[path])
                integrate(self.source, patch=self.patch, apply=True)
                self.assertEqual(after, self.snapshot())

    def test_invalid_include_is_removed_even_outside_current_patch_hunks(self):
        self.install_previous(old_label=False)
        check = git_apply(self.source, self.patch, reverse=True, check=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertEqual(integrate(self.source, patch=self.patch), "UPDATE_AVAILABLE")
        integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(self.panel.read_bytes(), self.corrected[APPEARANCE_CUSTOMIZE_UI_SOURCE])

    def test_duplicate_legacy_includes_are_rejected_without_writes(self):
        self.panel.write_bytes(LEGACY_SETTINGS_STRINGS_INCLUDE + self.panel.read_bytes())
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "Ambiguous legacy"):
            integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_unknown_source_edit_rejects_resource_cleanup_atomically(self):
        (self.source / "chrome/unrelated.cc").write_bytes(b"local native changes\n")
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "complete appearance catalog"):
            integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_previous_resource_version_can_be_reverted(self):
        self.assertEqual(integrate(self.source, patch=self.patch, revert=True), "READY")
        for name, data in self.originals.items():
            self.assertEqual((self.source / name).read_bytes(), data)
        self.assertEqual(self.output.read_bytes(), b"retained object")


class AppearanceWindowTypeUpgradeTests(unittest.TestCase):
    def setUp(self):
        import difflib
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "src"
        self.source.mkdir()
        (self.source / "BUILD.gn").write_text("# fixture\n")
        css = appearance_css_addition(
            (ROOT / "patches/windows/arc-appearance-windows.patch").read_bytes())
        self.originals = {APPEARANCE_CSS_SOURCE:b"/* existing */\n",
                          APPEARANCE_CAPTURE_SOURCE:b"// original model\n"}
        self.corrected = {APPEARANCE_CSS_SOURCE:self.originals[APPEARANCE_CSS_SOURCE] + css,
                          APPEARANCE_CAPTURE_SOURCE:b"// model\n" + WINDOW_TYPE_CHECK + b"\n// footer\n"}
        sections = []
        for name, data in self.corrected.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            sections.extend(difflib.unified_diff(self.originals[name].decode().splitlines(True),
                data.decode().splitlines(True), fromfile="a/" + name, tofile="b/" + name))
        self.patch = self.source.parent / "arc-appearance-windows.patch"
        self.patch.write_text("".join(sections), encoding="utf-8", newline="\n")
        self.capture = self.source / APPEARANCE_CAPTURE_SOURCE
        self.capture.write_bytes(self.corrected[APPEARANCE_CAPTURE_SOURCE].replace(
            WINDOW_TYPE_CHECK, LEGACY_WINDOW_TYPE_CHECK))
        self.output = self.source / "out/Default/retained.obj"
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"retained object")

    def snapshot(self):
        return {path:(path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.source.rglob("*") if path.is_file()}

    def test_old_capture_query_upgrades_only_model_and_preserves_source_format(self):
        for style in ("LF", "CRLF", "mixed", "no-eof"):
            with self.subTest(style=style):
                expected = self.corrected[APPEARANCE_CAPTURE_SOURCE]
                old = expected.replace(WINDOW_TYPE_CHECK, LEGACY_WINDOW_TYPE_CHECK)
                if style in ("CRLF", "mixed"):
                    old = old.replace(b"\n", b"\r\n")
                    expected = expected.replace(b"\n", b"\r\n")
                if style == "mixed":
                    old = old.replace(b"// model\r\n", b"// model\n")
                    expected = expected.replace(b"// model\r\n", b"// model\n")
                if style == "no-eof":
                    old = old.removesuffix(b"\n")
                    expected = expected.removesuffix(b"\n")
                self.capture.write_bytes(old)
                before = self.snapshot()
                self.assertEqual(integrate(self.source, patch=self.patch), "UPDATE_AVAILABLE")
                self.assertEqual(before, self.snapshot())
                self.assertEqual(integrate(self.source, patch=self.patch, apply=True), "APPLIED")
                self.assertEqual(self.capture.read_bytes(), expected)
                after = self.snapshot()
                for path in before:
                    if path != self.capture: self.assertEqual(before[path], after[path])
                integrate(self.source, patch=self.patch, apply=True)
                self.assertEqual(after, self.snapshot())

    def test_unknown_model_edit_is_rejected_without_writing_other_source(self):
        self.capture.write_bytes(self.capture.read_bytes().replace(b"// footer", b"// local changes"))
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "complete appearance catalog"):
            integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_old_model_query_can_be_reverted(self):
        self.assertEqual(integrate(self.source, patch=self.patch, revert=True), "READY")
        for name, data in self.originals.items():
            self.assertEqual((self.source / name).read_bytes(), data)
        self.assertEqual(self.output.read_bytes(), b"retained object")


class AppearanceNativeThemeUpgradeTests(unittest.TestCase):
    def setUp(self):
        import difflib
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "src"
        self.source.mkdir()
        (self.source / "BUILD.gn").write_text("# fixture\n")
        css = appearance_css_addition(
            (ROOT / "patches/windows/arc-appearance-windows.patch").read_bytes())
        self.originals = {APPEARANCE_CSS_SOURCE:b"/* existing */\n",
                          APPEARANCE_COLOR_PICKER_SOURCE:b"// original picker\n"}
        self.corrected = {
            APPEARANCE_CSS_SOURCE:self.originals[APPEARANCE_CSS_SOURCE] + css,
            APPEARANCE_COLOR_PICKER_SOURCE:b"// picker\n" + DARK_COLOR_CHECK +
                b"\n// other palette logic\n" + DARK_COLOR_CHECK + b"\n// footer\n"}
        sections = []
        for name, data in self.corrected.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            sections.extend(difflib.unified_diff(self.originals[name].decode().splitlines(True),
                data.decode().splitlines(True), fromfile="a/" + name, tofile="b/" + name))
        self.patch = self.source.parent / "arc-appearance-windows.patch"
        self.patch.write_text("".join(sections), encoding="utf-8", newline="\n")
        self.picker = self.source / APPEARANCE_COLOR_PICKER_SOURCE
        self.picker.write_bytes(self.corrected[APPEARANCE_COLOR_PICKER_SOURCE].replace(
            DARK_COLOR_CHECK, LEGACY_DARK_COLOR_CHECK))
        self.output = self.source / "out/Default/retained.obj"
        self.output.parent.mkdir(parents=True)
        self.output.write_bytes(b"retained object")

    def snapshot(self):
        return {path:(path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.source.rglob("*") if path.is_file()}

    def test_both_native_theme_queries_upgrade_without_touching_other_files(self):
        for style in ("LF", "CRLF", "mixed", "no-eof"):
            with self.subTest(style=style):
                expected = self.corrected[APPEARANCE_COLOR_PICKER_SOURCE]
                old = expected.replace(DARK_COLOR_CHECK, LEGACY_DARK_COLOR_CHECK)
                if style in ("CRLF", "mixed"):
                    old = old.replace(b"\n", b"\r\n")
                    expected = expected.replace(b"\n", b"\r\n")
                if style == "mixed":
                    old = old.replace(b"// picker\r\n", b"// picker\n")
                    expected = expected.replace(b"// picker\r\n", b"// picker\n")
                if style == "no-eof":
                    old = old.removesuffix(b"\n")
                    expected = expected.removesuffix(b"\n")
                self.picker.write_bytes(old)
                before = self.snapshot()
                self.assertEqual(integrate(self.source, patch=self.patch), "UPDATE_AVAILABLE")
                self.assertEqual(before, self.snapshot())
                self.assertEqual(integrate(self.source, patch=self.patch, apply=True), "APPLIED")
                self.assertEqual(self.picker.read_bytes(), expected)
                after = self.snapshot()
                for path in before:
                    if path != self.picker: self.assertEqual(before[path], after[path])
                integrate(self.source, patch=self.patch, apply=True)
                self.assertEqual(after, self.snapshot())

    def test_unknown_picker_edit_is_rejected_atomically(self):
        self.picker.write_bytes(self.picker.read_bytes().replace(b"// footer", b"// local changes"))
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "complete appearance catalog"):
            integrate(self.source, patch=self.patch, apply=True)
        self.assertEqual(before, self.snapshot())

    def test_old_color_picker_queries_can_be_reverted(self):
        self.assertEqual(integrate(self.source, patch=self.patch, revert=True), "READY")
        for name, data in self.originals.items():
            self.assertEqual((self.source / name).read_bytes(), data)
        self.assertEqual(self.output.read_bytes(), b"retained object")


if __name__ == "__main__":
    unittest.main()
