"""Transactional regressions for the upstream legal-page onboarding change.

Hunk fixtures reproduce patch matching only. Full upstream replay separately
checks the complete files, native contracts and real onboarding frontend.
"""
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.apply_windows_arc_workflow import (
    EXTERNAL_EXTENSION_REGISTRY, EXTERNAL_EXTENSION_SOURCE,
    LEGACY_EXTERNAL_EXTENSION_REGISTRY, ONBOARDING_BUILD_SOURCE,
    ONBOARDING_PATCH, git_apply, integrate,
)
from tests.test_windows_extension_services import hunk_preimages


@unittest.skipUnless(shutil.which('git'), 'Git is required for patch integration')
class OnboardingUpstreamInputsTests(unittest.TestCase):
    def fixture(self, root, *, legal):
        originals = hunk_preimages(ONBOARDING_PATCH.read_text(encoding='utf-8'))
        if legal:
            build = originals[ONBOARDING_BUILD_SOURCE]
            originals[ONBOARDING_BUILD_SOURCE] = build.replace(
                b'    "public",\n',
                b'    "public",\n    "public/privacy.html",\n'
                b'    "public/terms.html",\n    "src/pages/Welcome.svelte",\n', 1)
        for name, data in originals.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (root / 'BUILD.gn').write_bytes(b'# partial source fixture\n')
        for name in ('out/Default/retained.obj', 'profile/Default/Preferences'):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'existing user data or compiled output')
        return originals

    @staticmethod
    def snapshot(root):
        return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in root.rglob('*') if p.is_file()}

    def test_old_and_legal_inputs_apply_once_and_revert_without_losing_upstream(self):
        for legal in (False, True):
            for endings in ('LF', 'CRLF', 'mixed', 'missing-final-newline'):
                with self.subTest(legal=legal, endings=endings), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    originals = self.fixture(root, legal=legal)
                    for index, name in enumerate(originals):
                        path = root / name
                        data = path.read_bytes()
                        if endings == 'CRLF' or (endings == 'mixed' and index % 2):
                            data = data.replace(b'\n', b'\r\n')
                        if endings == 'missing-final-newline':
                            data = data.removesuffix(b'\n')
                        path.write_bytes(data)
                    before = self.snapshot(root)
                    if legal and endings == 'LF':
                        # Reproduce the exact CI failure with the old catalog.
                        failed = git_apply(root, ONBOARDING_PATCH, reverse=False, check=True)
                        self.assertNotEqual(failed.returncode, 0)
                        self.assertIn(ONBOARDING_BUILD_SOURCE, failed.stderr)
                        self.assertEqual(failed.stderr.count('patch failed:'), 1)
                    self.assertEqual(integrate(root, patch=ONBOARDING_PATCH), 'READY')
                    self.assertEqual(self.snapshot(root), before)
                    self.assertEqual(integrate(root, patch=ONBOARDING_PATCH, apply=True), 'APPLIED')
                    after = self.snapshot(root)
                    build = (root / ONBOARDING_BUILD_SOURCE).read_bytes()
                    for name in (b'helium_onboarding_strings.grdp', b'src/pages/Welcome.svelte',
                                 b'src/pages/DataImport.svelte'):
                        self.assertEqual(build.count(b'"' + name + b'"'), 1)
                    if legal:
                        self.assertIn(b'"public/privacy.html"', build)
                        self.assertIn(b'"public/terms.html"', build)
                    self.assertEqual(integrate(root, patch=ONBOARDING_PATCH, apply=True), 'APPLIED')
                    self.assertEqual(self.snapshot(root), after)
                    self.assertEqual(integrate(root, patch=ONBOARDING_PATCH, revert=True), 'READY')
                    reverted = self.snapshot(root)
                    self.assertEqual({n: v[0] for n, v in reverted.items()},
                                     {n: v[0] for n, v in before.items()})
                    for name in ('out/Default/retained.obj', 'profile/Default/Preferences'):
                        self.assertEqual(reverted[name], before[name])

    def test_legal_variant_keeps_the_existing_registry_upgrade_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, legal=True)
            integrate(root, patch=ONBOARDING_PATCH, apply=True)
            registry = root / EXTERNAL_EXTENSION_SOURCE
            registry.write_bytes(registry.read_bytes().replace(
                EXTERNAL_EXTENSION_REGISTRY, LEGACY_EXTERNAL_EXTENSION_REGISTRY, 1))
            before = self.snapshot(root)
            self.assertEqual(integrate(root, patch=ONBOARDING_PATCH), 'UPDATE_AVAILABLE')
            self.assertEqual(self.snapshot(root), before)
            integrate(root, patch=ONBOARDING_PATCH, apply=True)
            after = self.snapshot(root)
            self.assertIn(EXTERNAL_EXTENSION_REGISTRY, registry.read_bytes())
            self.assertEqual({n: v for n, v in after.items() if n != EXTERNAL_EXTENSION_SOURCE},
                             {n: v for n, v in before.items() if n != EXTERNAL_EXTENSION_SOURCE})

    def test_unknown_inputs_or_conflicting_other_hunks_reject_the_whole_catalog(self):
        for conflict in ('inputs', 'registry'):
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.fixture(root, legal=True)
                path = root / (ONBOARDING_BUILD_SOURCE if conflict == 'inputs'
                               else EXTERNAL_EXTENSION_SOURCE)
                old, new = ((b'"public/terms.html"', b'"public/unknown.html"')
                            if conflict == 'inputs' else
                            (LEGACY_EXTERNAL_EXTENSION_REGISTRY, b'unknown registry'))
                self.assertIn(old, path.read_bytes())
                path.write_bytes(path.read_bytes().replace(old, new, 1))
                before = self.snapshot(root)
                with self.assertRaisesRegex(RuntimeError, 'No changes made'):
                    integrate(root, patch=ONBOARDING_PATCH, apply=True)
                self.assertEqual(self.snapshot(root), before)


if __name__ == '__main__':
    unittest.main()
