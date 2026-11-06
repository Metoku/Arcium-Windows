"""Executable contracts for candidate evidence, stale runtimes and packaging drift."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.verify_windows_release_candidate import verify

ROOT = Path(__file__).resolve().parents[1]


class ReleaseCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo, self.build, self.dist = (root / name for name in ('repo', 'build', 'dist'))
        for path in (self.repo / 'upstream', self.build, self.dist):
            path.mkdir(parents=True)
        self.version, self.commit = '0.1.0-alpha.4', 'c' * 40
        self.expected = {'arcium_commit':'a' * 40, 'windows_platform_commit':'b' * 40,
                         'chromium_version':'156.0.8078.47', 'integration_commit':self.commit}
        for name, value in (('arcium-core.sha', self.expected['arcium_commit']),
                            ('helium-windows.sha', self.expected['windows_platform_commit']),
                            ('chromium-version.txt', self.expected['chromium_version'])):
            (self.repo / 'upstream' / name).write_text(value + '\n')
        (self.repo / 'LICENSE').write_bytes(b'Project license')
        self.files = {'chrome.exe':b'Executable', 'chrome.dll':b'Native code',
                      'chrome_elf.dll':b'ELF', 'resources.pak':b'UI resources',
                      'chrome_100_percent.pak':b'Icons', 'locales/en-US.pak':b'English',
                      'v8_context_snapshot.bin':b'V8'}
        for name, data in self.files.items():
            path = self.build / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.proof = self.dist / 'build.json'
        self.raw, self.packaged = self.dist / 'raw.json', self.dist / 'packaged.json'
        self.write(self.proof, {**self.expected, 'browser_compiled':True,
            'release_candidate_integrations':True, 'browser_binary_bytes':len(self.files['chrome.exe']),
            'status':'BROWSER_BINARY_CREATED_NOT_LAUNCHED'})
        smoke = {'status':'HEADLESS_LAUNCH_PASSED', 'browser_launched':True,
                 'isolated_profile_deleted':True, 'browser_sha256':self.hash(self.build / 'chrome.exe')}
        for path in (self.raw, self.packaged):
            self.write(path, smoke)
        self.archive = self.dist / f'Arcium-Windows-{self.version}.zip'
        self.setup = self.dist / f'Arcium-Windows-{self.version}-Setup.exe'
        self.setup.write_bytes(b'Installer')
        self.make_archive()

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def hash(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def make_archive(self, extras=()):
        with zipfile.ZipFile(self.archive, 'w') as package:
            root = f'Arcium-Windows-{self.version}/'
            for name, data in self.files.items():
                package.writestr(root + name, data)
            package.writestr(root + 'LICENSE.Arcium.txt', (self.repo / 'LICENSE').read_bytes())
            for name, data in extras:
                package.writestr(name, data)
        for artifact in (self.archive, self.setup):
            Path(str(artifact) + '.sha256').write_text(self.hash(artifact) + '  ' + artifact.name + '\n')
        self.write(Path(str(self.setup) + '.json'), {'PackageVersion':self.version,
            'RuntimeVersion':self.version, 'PortableFile':self.archive.name,
            'PortableSha256':self.hash(self.archive), 'InstallerSha256':self.hash(self.setup),
            'DistributionCommit':self.commit, 'Repository':'Metoku/Arcium-Windows'})

    def check(self):
        return verify(self.repo, self.build, self.dist, self.version, self.commit,
                      self.proof, self.raw, self.packaged)

    def test_matching_native_and_packaged_bytes_produce_candidate_evidence_only(self):
        receipt = self.check()
        self.assertEqual(receipt['status'], 'WINDOWS_RELEASE_CANDIDATE_VERIFIED')
        self.assertEqual(receipt['runtime_sha256']['chrome.dll'], self.hash(self.build / 'chrome.dll'))
        self.assertFalse(receipt['published'])
        self.assertFalse(receipt['signed'])
        self.assertFalse(receipt['interactive_acceptance'])

    def test_old_checkout_pins_or_missing_integrations_cannot_be_released_as_current(self):
        proof = json.loads(self.proof.read_text())
        for field, wrong in [('integration_commit','d' * 40), ('arcium_commit','d' * 40),
                             ('windows_platform_commit','d' * 40), ('chromium_version','155.0.1.2'),
                             ('browser_compiled',False), ('release_candidate_integrations',False)]:
            with self.subTest(field=field):
                self.write(self.proof, {**proof, field:wrong})
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    self.check()
        self.write(self.proof, proof)

    def test_launch_evidence_must_match_this_executable_and_delete_its_profile(self):
        smoke = json.loads(self.packaged.read_text())
        for field, wrong in [('browser_sha256','0' * 64), ('browser_launched',False),
                             ('isolated_profile_deleted',False), ('status','ERROR')]:
            self.write(self.packaged, {**smoke, field:wrong})
            with self.assertRaisesRegex(ValueError, 'launch evidence'):
                self.check()

    def test_dll_and_resource_drift_is_detected_even_when_executable_matches(self):
        for name in ('chrome.dll', 'resources.pak'):
            original = (self.build / name).read_bytes()
            (self.build / name).write_bytes(b'Changed after native compilation')
            with self.assertRaisesRegex(ValueError, 'Packaged bytes differ'):
                self.check()
            (self.build / name).write_bytes(original)

    def test_sidecars_and_installer_provenance_cannot_relabel_an_older_zip(self):
        provenance = Path(str(self.setup) + '.json')
        original = json.loads(provenance.read_text())
        for field, wrong in [('RuntimeVersion','0.1.0-alpha.3'), ('PortableSha256','0' * 64),
                             ('DistributionCommit','d' * 40), ('Repository','imputnet/helium')]:
            self.write(provenance, {**original, field:wrong})
            with self.assertRaisesRegex(ValueError, 'provenance'):
                self.check()
        self.write(provenance, original)
        Path(str(self.archive) + '.sha256').write_text('0' * 64 + '  ' + self.archive.name)
        with self.assertRaisesRegex(ValueError, 'sidecar'):
            self.check()

    def test_unsafe_private_or_duplicate_entries_fail_before_candidate_receipt(self):
        prefix = f'Arcium-Windows-{self.version}/'
        for entry in (prefix + '../escape', prefix + '../escape/', prefix + 'Default/',
                      prefix + 'Default/Preferences',
                      prefix + 'passwords.csv', prefix + 'CHROME.EXE', '/absolute',
                      prefix + 'locales\\en-US.pak'):
            with self.subTest(entry=entry):
                self.make_archive([(entry, b'Unexpected')])
                with self.assertRaises(ValueError):
                    self.check()
        self.make_archive([(prefix, b''), (prefix + 'locales/', b'')])
        self.assertEqual(self.check()['status'], 'WINDOWS_RELEASE_CANDIDATE_VERIFIED')

    def test_heavy_workflow_is_manual_and_candidate_upload_requires_success(self):
        workflow = (ROOT / '.github/workflows/windows-release-candidate.yml').read_text()
        self.assertIn('  workflow_dispatch:', workflow)
        for trigger in ('  pull_request:', '  push:', '  schedule:'):
            self.assertNotIn(trigger, workflow)
        self.assertIn('contents: read', workflow)
        self.assertNotIn('contents: write', workflow)
        self.assertIn('--execute --release-candidate --require-cache', workflow)
        self.assertLess(workflow.index('verify_windows_release_candidate.py'),
                        workflow.index('name: Upload complete candidate'))
        self.assertNotIn('if: always()', workflow.split('name: Upload complete candidate')[1]
                         .split('name: Upload diagnostics')[0])


if __name__ == '__main__':
    unittest.main()
