"""Atomic application of the Windows appearance + migration bundle."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.apply_windows_arc_workflow import integrate_bundle


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

    def test_no_mutually_exclusive_modes(self):
        with self.assertRaises(ValueError):
            integrate_bundle(self.source, apply=True, revert=True,
                             catalogs=self.catalogs)


if __name__ == "__main__":
    unittest.main()
