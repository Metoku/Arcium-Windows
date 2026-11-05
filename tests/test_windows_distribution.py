"""Real PowerShell contracts and isolated Windows setup lifecycle tests."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / 'installer/windows/Distribution.ps1'
SHELLS = list(dict.fromkeys(filter(None, (
    os.environ.get('ARCIUM_POWERSHELL'), shutil.which('pwsh'), shutil.which('powershell'),
))))


def psquote(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_ps(shell, code, directory, timeout=120):
    script = directory / 'driver.ps1'
    script.write_text(
        "$ErrorActionPreference='Stop'\nSet-StrictMode -Version Latest\n"
        + '. ' + psquote(COMMON) + '\n' + code, encoding='utf-8')
    return subprocess.run(
        [shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)


def release(version, *, preview=None, draft=False, installer=True):
    name = f'Arcium-Windows-{version}-Setup.exe'
    assets = [{
        'name': n, 'state': 'uploaded', 'size': 100,
        'browser_download_url': f'https://github.com/Metoku/Arcium-Windows/releases/download/v{version}/{n}',
        'digest': 'sha256:' + 'a' * 64,
    } for n in (name, name + '.sha256')] if installer else []
    return {'tag_name': 'v' + version, 'prerelease': ('-' in version) if preview is None else preview,
            'draft': draft, 'assets': assets}


def make_zip(parent, entries=None, browser=b'fake'):
    version = '0.1.0-alpha.1'
    archive = parent / f'Arcium-Windows-{version}.zip'
    files = entries if entries is not None else {
        'chrome.exe': browser, 'chrome.dll': b'dll', 'chrome_elf.dll': b'dll',
        'resources.pak': b'pak', 'chrome_100_percent.pak': b'pak',
        'locales/en-US.pak': b'locale', 'v8_context_snapshot.bin': b'v8',
        'LICENSE.Arcium.txt': (ROOT / 'LICENSE').read_bytes(),
    }
    with zipfile.ZipFile(archive, 'w') as z:
        for name, value in files.items():
            z.writestr(f'Arcium-Windows-{version}/{name}', value)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    Path(str(archive) + '.sha256').write_text(digest + '  ' + archive.name + '\n')
    return archive


@unittest.skipUnless(SHELLS, 'PowerShell is required')
class DistributionContracts(unittest.TestCase):
    def each(self, code):
        for shell in SHELLS:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                result = run_ps(shell, code, Path(folder))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_semver_order_including_numeric_prereleases(self):
        values = ['0.1.0-alpha.1', '0.1.0-alpha.2', '0.1.0-alpha.10',
                  '0.1.0-beta', '0.1.0-rc.1', '0.1.0', '0.1.1', '0.2.0', '1.0.0']
        self.each(
            '$versions=ConvertFrom-Json ' + psquote(json.dumps(values)) + '\n'
            'for($i=0;$i -lt $versions.Count;$i++) {'
            'for($j=0;$j -lt $versions.Count;$j++) {'
            'if((Compare-ArciumVersion $versions[$i] $versions[$j]) -ne [Math]::Sign($i-$j)) {'
            'throw "Wrong ordering: $i $j" } } }')

    def test_unsupported_versions_are_rejected(self):
        self.each(
            '$bad=ConvertFrom-Json ' + psquote(json.dumps([
                '../1.0.0', '1.0', '01.0.0', '1.0.0-alpha.01', '1.0.0+meta',
                '65536.0.0', '1.0.0-', 'v1.0.0', '1.0.0-alpha/1',
            ])) + '\n'
            'foreach($v in $bad) { $failed=$false; try { $null=ConvertTo-ArciumVersion $v }'
            'catch { $failed=$true }; if(-not $failed) { throw "Accepted $v" } }')

    def test_update_channels_skip_drafts_incomplete_assets_and_downgrades(self):
        releases = [release('0.1.0-alpha.2'), release('0.1.0-alpha.10'),
                    release('0.1.0'), release('0.2.0-beta.1'),
                    release('9.0.0', draft=True), release('8.0.0', installer=False)]
        self.each(
            '$releases=ConvertFrom-Json ' + psquote(json.dumps(releases)) + '\n'
            "$p=Find-ArciumInstallerUpdate $releases '0.1.0-alpha.1' preview\n"
            "if($p.Version -ne '0.2.0-beta.1') { throw 'Wrong preview' }\n"
            "$s=Find-ArciumInstallerUpdate $releases '0.1.0-alpha.1' stable\n"
            "if($s.Version -ne '0.1.0') { throw 'Wrong stable' }\n"
            "if($null -ne (Find-ArciumInstallerUpdate $releases '1.0.0' preview)) { throw 'Downgrade offered' }\n"
            "if($null -ne (Find-ArciumInstallerUpdate $releases '0.1.0' stable)) { throw 'Reinstall offered' }")

    def test_update_urls_cannot_point_to_helium_or_another_repository(self):
        for url in [
            'https://github.com/imputnet/helium/releases/download/v1.0.0/Arcium-Windows-1.0.0-Setup.exe',
            'https://github.com.evil.invalid/Metoku/Arcium-Windows/releases/download/v1.0.0/x.exe',
            'http://github.com/Metoku/Arcium-Windows/releases/download/v1.0.0/Arcium-Windows-1.0.0-Setup.exe',
        ]:
            item = release('1.0.0')
            item['assets'][0]['browser_download_url'] = url
            self.each(
                '$releases=ConvertFrom-Json ' + psquote(json.dumps([item])) + '\n'
                "$failed=$false; try { $null=Find-ArciumInstallerUpdate $releases '0.1.0' stable }"
                "catch { $failed=$true }; if(-not $failed) { throw 'Foreign download accepted' }")

    def test_checksum_checks_filename_payload_and_api_digest(self):
        for shell in SHELLS:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                payload = root / 'Arcium-Windows-1.0.0-Setup.exe'
                payload.write_bytes(b'test installer')
                digest = hashlib.sha256(payload.read_bytes()).hexdigest()
                checksum = root / 'checksum'
                checksum.write_text(digest + '  ' + payload.name + '\n')
                code = '$file=' + psquote(payload) + '\n$checksum=' + psquote(checksum) + '\n'
                code += (
                    '$null=Assert-ArciumChecksum $file $checksum ' + psquote(payload.name)
                    + ' ' + psquote('sha256:' + digest) + '\n'
                    "$failed=$false; try { $null=Assert-ArciumChecksum $file $checksum 'another.exe' }"
                    "catch { $failed=$true }; if(-not $failed) { throw 'Wrong name accepted' }\n"
                    "$failed=$false; try { $null=Assert-ArciumChecksum $file $checksum "
                    + psquote(payload.name) + " ('sha256:'+('0'*64)) }"
                    "catch { $failed=$true }; if(-not $failed) { throw 'Wrong API digest accepted' }\n"
                    "[IO.File]::WriteAllText($file,'tampered')\n"
                    "$failed=$false; try { $null=Assert-ArciumChecksum $file $checksum "
                    + psquote(payload.name) + " } catch { $failed=$true };"
                    "if(-not $failed) { throw 'Tampering accepted' }")
                result = run_ps(shell, code, root)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_archive_is_extracted_with_original_structure_and_hashes(self):
        for shell in SHELLS:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); archive = make_zip(root); before = archive.read_bytes()
                result = run_ps(shell, '$v=Expand-ArciumRuntime ' + psquote(archive) + ' '
                                + psquote(root/'payload') + "\nif($v -ne '0.1.0-alpha.1'){throw 'Wrong version'}", root)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((root/'payload/locales/en-US.pak').read_bytes(), b'locale')
                self.assertEqual(archive.read_bytes(), before)

    def test_archive_traversal_links_profiles_and_duplicate_paths_are_rejected(self):
        cases = [
            {'../escape.exe': b'bad'}, {'locales/../../escape.exe': b'bad'},
            {'Default/Preferences': b'private'}, {'passwords.csv': b'private'},
            {'locales/NUL.txt': b'bad'}, {'locales/trailing.': b'bad'},
            {'chrome.exe': b'one', 'CHROME.EXE': b'two'},
        ]
        for shell in SHELLS:
            for files in cases:
                with self.subTest(shell=shell, files=list(files)), tempfile.TemporaryDirectory() as folder:
                    root = Path(folder); archive = make_zip(root, files)
                    result = run_ps(shell, 'Expand-ArciumRuntime ' + psquote(archive) + ' ' + psquote(root/'payload'), root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((root/'escape.exe').exists())
                    self.assertFalse((root/'payload').exists())
            with self.subTest(shell=shell, link=True), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); archive = make_zip(root)
                with zipfile.ZipFile(archive, 'a') as z:
                    entry = zipfile.ZipInfo('Arcium-Windows-0.1.0-alpha.1/locales/escape')
                    entry.create_system = 3; entry.external_attr = (0o120777 << 16)
                    z.writestr(entry, '../../private')
                result = run_ps(shell, 'Expand-ArciumRuntime ' + psquote(archive) + ' ' + psquote(root/'payload'), root)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root/'payload').exists())

    def test_pe_architecture_validation(self):
        for shell in SHELLS:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); binary = bytearray(256)
                binary[:2] = b'MZ'; binary[0x3C:0x40] = (128).to_bytes(4, 'little')
                binary[128:134] = b'PE\0\0\x64\x86'
                path = root/'browser.exe'; path.write_bytes(binary)
                result = run_ps(shell, 'Assert-ArciumX64Executable ' + psquote(path), root)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                binary[132:134] = b'\x4c\x01'; path.write_bytes(binary)
                result = run_ps(shell, 'Assert-ArciumX64Executable ' + psquote(path), root)
                self.assertNotEqual(result.returncode, 0)

    def test_install_metadata_has_fixed_repository_and_channel(self):
        for shell in SHELLS:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); ini = root/'arcium-install.ini'
                ini.write_text('[Install]\nSchema=1\nRepository=Metoku/Arcium-Windows\nVersion=0.1.0-alpha.2\nChannel=preview\n')
                result = run_ps(shell, '$s=Read-ArciumInstall ' + psquote(root)
                                + "\nif($s.Version -ne '0.1.0-alpha.2'){throw 'Wrong state'}", root)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                ini.write_text(ini.read_text().replace('Metoku/Arcium-Windows', 'imputnet/helium'))
                result = run_ps(shell, 'Read-ArciumInstall ' + psquote(root), root)
                self.assertNotEqual(result.returncode, 0)

    def test_all_distribution_scripts_parse(self):
        paths = [*ROOT.glob('installer/windows/*.ps1'),
                 ROOT/'scripts/package_windows_installer.ps1', ROOT/'scripts/fetch_windows_portable.ps1']
        self.each(
            '$paths=ConvertFrom-Json ' + psquote(json.dumps([str(p) for p in paths])) + '\n'
            'foreach($p in $paths) { $tokens=$null; $errors=$null;'
            '$null=[Management.Automation.Language.Parser]::ParseFile($p,[ref]$tokens,[ref]$errors);'
            'if($errors.Count) { throw ($errors | Out-String) } }')


    def test_network_client_initializes_on_legacy_and_modern_powershell(self):
        self.each(
            "$client=New-ArciumWebClient\n"
            "try { if($client.Headers['User-Agent'] -ne 'Arcium-Windows-Distribution') {"
            "throw 'Missing client identity' } } finally { $client.Dispose() }")


@unittest.skipUnless(os.name == 'nt' and os.environ.get('ARCIUM_RUN_INSTALLER_TESTS') == '1',
                     'Windows setup lifecycle runs only in its isolated CI job')
class WindowsInstallerLifecycle(unittest.TestCase):
    def test_install_launch_upgrade_reject_downgrade_and_uninstall_keeps_profiles(self):
        shell = shutil.which('pwsh')
        self.assertTrue(shell)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); output = root/'output'; installed = root/'installed'
            fake = root/'fake.cs'
            fake.write_text(
                'using System; using System.IO; class Fake { static int Main(string[] args) {'
                'File.WriteAllLines(Environment.GetEnvironmentVariable("ARCIUM_FAKE_ARGS"),args);'
                'File.WriteAllText(Environment.GetEnvironmentVariable("ARCIUM_FAKE_PATH"),'
                'System.Reflection.Assembly.GetExecutingAssembly().Location);return 0;} }')
            browser = root/'chrome.exe'
            csc = Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
            subprocess.run([str(csc), '/nologo', '/target:winexe', '/platform:x64',
                            '/out:'+str(browser), str(fake)], check=True, capture_output=True)
            archive = make_zip(root, browser=browser.read_bytes())
            installers = []
            for version in ('0.1.0-alpha.2', '0.1.0-alpha.10'):
                result = subprocess.run([
                    shell, '-NoProfile', '-File', str(ROOT/'scripts/package_windows_installer.ps1'),
                    '-PortableZip', str(archive), '-Version', version, '-OutputDirectory', str(output),
                ], capture_output=True, text=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                installers.append(output/f'Arcium-Windows-{version}-Setup.exe')
            # Only this CI-owned sentinel is removed. Real browser data is never
            # read or deleted by installation or these tests.
            profile = Path(os.environ['LOCALAPPDATA'])/'Arcium/User Data'
            profile.mkdir(parents=True, exist_ok=True)
            sentinel = profile/('installer-test-'+root.name)
            sentinel.write_text('keep profile')
            try:
                for setup, version in zip(installers, ('0.1.0-alpha.2', '0.1.0-alpha.10')):
                    result = subprocess.run([str(setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                                             '/TASKS=previewupdates', '/DIR='+str(installed)], timeout=120)
                    self.assertEqual(result.returncode, 0)
                    args = ['', 'https://example.invalid/a?q="quoted"&x=1', 'space value', 'trailing\\', '"']
                    env = os.environ.copy()
                    env['ARCIUM_FAKE_ARGS'] = str(root/'args.txt'); env['ARCIUM_FAKE_PATH'] = str(root/'path.txt')
                    result = subprocess.run([str(installed/'Arcium.exe'), *args], env=env, timeout=30)
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual((root/'args.txt').read_text().splitlines(), args)
                    self.assertIn(version, (root/'path.txt').read_text())
                    self.assertEqual(sentinel.read_text(), 'keep profile')
                self.assertTrue((installed/'versions/0.1.0-alpha.2/chrome.exe').exists())
                rejected = subprocess.run([str(installers[0]), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                                           '/NORESTART', '/DIR='+str(installed)], timeout=60)
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn('Version=0.1.0-alpha.10', (installed/'arcium-install.ini').read_text())
            finally:
                uninstaller = installed/'unins000.exe'
                if uninstaller.exists():
                    result = subprocess.run([str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'], timeout=120)
                    self.assertEqual(result.returncode, 0)
                self.assertEqual(sentinel.read_text(), 'keep profile')
                self.assertFalse((installed/'versions').exists())
                sentinel.unlink()


if __name__ == '__main__':
    unittest.main()
