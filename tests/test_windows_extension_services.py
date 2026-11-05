"""Offline transaction tests for the optional services-review catalog.

Only hunk preimages are reconstructed here. The pinned source replay separately
checks complete upstream files and runs the actual frontend interaction tests.
"""
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from scripts.apply_windows_arc_workflow import SERVICES_PATCH, integrate, main, patch_targets


def hunk_preimages(text):
    files = {}
    current = None
    for line in text.splitlines(keepends=True):
        if line.startswith('--- a/'):
            current = line[6:].strip()
            files[current] = []
        elif line.startswith('@@ '):
            start = int(re.match(r'@@ -(\d+)', line)[1])
            while len(files[current]) < start - 1:
                files[current].append('// omitted upstream line\n')
        elif current and line.startswith((' ', '-')):
            files[current].append(line[1:])
    return {name: (''.join(lines) + ('// omitted trailing upstream lines\n'
                                   if lines[-1] == '\n' else '')).encode()
            for name, lines in files.items()}


class ExtensionServicesTests(unittest.TestCase):
    def test_services_cli_selects_only_the_recovery_catalog(self):
        with patch('sys.argv', ['apply_windows_arc_workflow.py', '--feature', 'services', '--apply']), \
                patch('scripts.apply_windows_arc_workflow.integrate', return_value='APPLIED') as apply, \
                patch('builtins.print'):
            self.assertEqual(main(), 0)
            self.assertEqual(apply.call_args.kwargs,
                             {'apply': True, 'revert': False, 'patch': SERVICES_PATCH})

    def test_only_existing_webui_and_build_inputs_are_in_scope(self):
        targets = set(patch_targets(SERVICES_PATCH.read_text(encoding='utf-8')))
        self.assertEqual(targets, {
            'chrome/app/settings_strings.grdp',
            'chrome/browser/resources/settings/privacy_page/services_page.ts',
            'components/helium_onboarding/BUILD.gn',
            'components/helium_onboarding/src/lib/onboarding-flow.ts',
            'components/helium_onboarding/src/components/PageNavigation.svelte',
            'components/helium_onboarding/src/pages/HeliumServices.svelte',
            'components/helium_onboarding/tests/import-navigation.test.mjs',
        })
        with self.assertRaises(ValueError):
            patch_targets('--- a/components/helium_onboarding/src/unrelated.ts\n'
                          '+++ b/components/helium_onboarding/src/unrelated.ts\n'
                          '@@ -1 +1 @@\n-before\n+after\n')

    def test_check_apply_reapply_revert_and_conflict_preserve_output_and_profile(self):
        originals = hunk_preimages(SERVICES_PATCH.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source'
            source.mkdir()
            (source / 'BUILD.gn').write_bytes(b'# partial fixture\n')
            sentinels = {'out/Default/retained.obj': b'existing output',
                         'profile/Default/Preferences': b'{"extensions":{"settings":{}}}'}
            for endings in ('LF', 'CRLF', 'mixed', 'missing-final-newline'):
                with self.subTest(endings=endings):
                    for index, (name, data) in enumerate(originals.items()):
                        if endings == 'CRLF' or (endings == 'mixed' and index % 2):
                            data = data.replace(b'\n', b'\r\n')
                        if endings == 'missing-final-newline':
                            data = data.removesuffix(b'\n')
                        path = source / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                    for name, data in sentinels.items():
                        path = source / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                    snapshot = lambda: {p.relative_to(source).as_posix():
                                        (p.read_bytes(), p.stat().st_mtime_ns)
                                        for p in source.rglob('*') if p.is_file()}
                    before = snapshot()
                    self.assertEqual(integrate(source, patch=SERVICES_PATCH), 'READY')
                    self.assertEqual(snapshot(), before)
                    self.assertEqual(integrate(source, patch=SERVICES_PATCH, apply=True), 'APPLIED')
                    applied = snapshot()
                    self.assertEqual(integrate(source, patch=SERVICES_PATCH, apply=True), 'APPLIED')
                    self.assertEqual(snapshot(), applied)
                    self.assertEqual(integrate(source, patch=SERVICES_PATCH, revert=True), 'READY')
                    self.assertEqual({p: value[0] for p, value in snapshot().items()},
                                     {p: value[0] for p, value in before.items()})
                    for name in sentinels:
                        self.assertEqual(snapshot()[name], before[name])
                    conflict = source / 'components/helium_onboarding/src/lib/onboarding-flow.ts'
                    conflict.write_bytes(b'unknown local edit\n')
                    edited = snapshot()
                    with self.assertRaisesRegex(RuntimeError, 'No changes made'):
                        integrate(source, patch=SERVICES_PATCH, apply=True)
                    self.assertEqual(snapshot(), edited)


if __name__ == '__main__':
    unittest.main()
