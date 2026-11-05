"""Execute the packager with synthetic files; no browser binaries are launched."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/package_windows_portable.ps1'
SHELLS = list(dict.fromkeys(filter(None, (
    os.environ.get('ARCIUM_POWERSHELL'),
    shutil.which('pwsh'),
    shutil.which('powershell'),
))))


@unittest.skipUnless(SHELLS, 'PowerShell is required for packaging execution tests')
class PortablePackageTests(unittest.TestCase):
    def fixture(self, parent):
        source = parent / 'build output'
        contents = {
            'chrome.exe':b'executable', 'chrome.dll':b'library',
            'chrome_elf.dll':b'library', 'resources.pak':b'resources',
            'chrome_100_percent.pak':b'icons', 'chrome_200_percent.pak':b'hidpi',
            'v8_context_snapshot.bin':b'snapshot', 'icudtl.dat':b'icu',
            'extra_gpu.dll':b'gpu', 'chrome_proxy.exe':b'helper',
            'notification_helper.exe':b'helper',
            'locales/en-US.pak':b'english', 'locales/fil.pak':b'filipino',
            'WidevineCdm/manifest.json':b'{}',
            'WidevineCdm/_platform_specific/win_x64/widevinecdm.dll':b'cdm',
            'Extensions/bundled/manifest.json':b'{}',
            'LICENSES.chromium.html':b'notices',
            'obj/private.obj':b'build object', 'obj/trap.dll':b'not a runtime DLL',
            'gen/generated.js':b'build generation',
            'Default/Preferences':b'personal profile', 'User Data/Local State':b'personal state',
            'passwords.csv':b'private export', 'debug.log':b'private log',
            'chrome.dll.pdb':b'debug symbols', 'locales/private.csv':b'private export',
            'setup.exe':b'installer', 'mini_installer.exe':b'installer',
            'helium_update_helper.exe':b'updater',
        }
        for name, data in contents.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return source

    def invoke(self, shell, source, output, *options):
        return subprocess.run([
            shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', str(SCRIPT), '-BuildDirectory', str(source),
            '-OutputDirectory', str(output), *options,
        ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)

    def inventory(self, root):
        return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob('*') if p.is_file()}

    def test_package_selection_checksum_and_unchanged_build(self):
        for shell in SHELLS:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                parent=Path(folder); source=self.fixture(parent); output=parent/'release output'
                before=self.inventory(source)
                result=self.invoke(shell, source, output)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertIn('ARCIUM_PORTABLE_ZIP_CREATED', result.stdout)
                name='Arcium-Windows-0.1.0-alpha.1'
                archive=output/(name+'.zip')
                with zipfile.ZipFile(archive) as package:
                    members={p for p in package.namelist() if not p.endswith('/')}
                    expected={
                        name+'/'+p for p in before
                        if p.split('/')[0] in ('locales','Extensions','WidevineCdm')
                        and not p.endswith('.csv')
                    }
                    expected |= {name+'/'+p for p in (
                        'chrome.exe','chrome.dll','chrome_elf.dll','resources.pak',
                        'chrome_100_percent.pak','chrome_200_percent.pak',
                        'v8_context_snapshot.bin','icudtl.dat','extra_gpu.dll',
                        'chrome_proxy.exe','notification_helper.exe','LICENSES.chromium.html',
                        'LICENSE.Arcium.txt')}
                    self.assertEqual(members,expected)
                    self.assertEqual(package.read(name+'/chrome.exe'), b'executable')
                    self.assertEqual(package.read(name+'/LICENSE.Arcium.txt'), (ROOT/'LICENSE').read_bytes())
                expected_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
                self.assertEqual(Path(str(archive)+'.sha256').read_text().strip(),
                                 expected_hash+'  '+archive.name)
                self.assertEqual(before,self.inventory(source))

    def test_list_only_creates_no_output(self):
        for shell in SHELLS:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                parent=Path(folder);source=self.fixture(parent);output=parent/'release'
                result=self.invoke(shell,source,output,'-ListOnly')
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('chrome.exe',result.stdout)
                self.assertNotIn('passwords.csv',result.stdout)
                self.assertFalse(output.exists())

    def test_incomplete_build_fails_before_output_creation(self):
        for shell in SHELLS:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                parent=Path(folder);source=self.fixture(parent);output=parent/'release'
                (source/'chrome.dll').unlink()
                before=self.inventory(source)
                result=self.invoke(shell,source,output)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('Missing required runtime file',result.stderr)
                self.assertFalse(output.exists())
                self.assertEqual(before,self.inventory(source))

    def test_existing_outputs_are_not_overwritten(self):
        for shell in SHELLS:
            for kind in ('folder','zip','checksum'):
                with self.subTest(shell=shell,kind=kind), tempfile.TemporaryDirectory() as folder:
                    parent=Path(folder);source=self.fixture(parent);output=parent/'release'
                    output.mkdir()
                    name='Arcium-Windows-0.1.0-alpha.1'
                    if kind=='folder':
                        path=output/name;path.mkdir();(path/'keep.txt').write_bytes(b'keep')
                    else:
                        path=output/(name+('.zip' if kind=='zip' else '.zip.sha256'))
                        path.write_bytes(b'keep')
                    before=self.inventory(output)
                    result=self.invoke(shell,source,output)
                    self.assertNotEqual(result.returncode,0)
                    self.assertIn('Output already exists',result.stderr)
                    self.assertEqual(before,self.inventory(output))

    def test_output_inside_build_is_rejected(self):
        for shell in SHELLS:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                source=self.fixture(Path(folder));before=self.inventory(source)
                result=self.invoke(shell,source,source/'release')
                self.assertNotEqual(result.returncode,0)
                self.assertIn('outside the build directory',result.stderr)
                self.assertEqual(before,self.inventory(source))

    @unittest.skipIf(os.name=='nt','Creating symlinks can require Windows privileges')
    def test_linked_runtime_folder_is_rejected_without_reading_external_profile(self):
        for shell in SHELLS:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                parent=Path(folder);source=self.fixture(parent);output=parent/'release'
                external=parent/'personal profile';external.mkdir()
                (external/'Preferences').write_bytes(b'private')
                (source/'locales/escape').symlink_to(external,target_is_directory=True)
                result=self.invoke(shell,source,output)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('symbolic link or junction',result.stderr)
                self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()
