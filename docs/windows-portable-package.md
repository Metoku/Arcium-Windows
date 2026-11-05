# Package an existing Windows build

Close Arcium and finish any running build before copying its runtime files.
The PowerShell helper creates a candidate ZIP from your existing output; it
does not compile, install, launch, sign or publish a browser.

From `D:\src\Arcium-Windows`, run:

```powershell
git switch main
if ($LASTEXITCODE -ne 0) { throw 'Branch switch failed.' }
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw 'Repository update failed.' }
.\scripts\package_windows_portable.ps1 -Version '0.1.0-alpha.3'
```

Windows PowerShell 5.1 and PowerShell 7 are supported. No additional Python,
archiver or browser rebuild is required by this helper.

Default input:
`work\windows-platform\build\src\out\Default`

Outputs:

- `dist\Arcium-Windows-0.1.0-alpha.3\` -- staged runtime files.
- `dist\Arcium-Windows-0.1.0-alpha.3.zip` -- ZIP with that folder at its root.
- `dist\Arcium-Windows-0.1.0-alpha.3.zip.sha256` -- checksum.

The version names the package; it does not change the compiled browser version.
The helper refuses an existing output folder, ZIP or checksum. For another
candidate, use a new version or `-OutputDirectory` rather than overwriting it.

For a read-only file list:

```powershell
.\scripts\package_windows_portable.ps1 -ListOnly
```

For different paths:

```powershell
.\scripts\package_windows_portable.ps1 -BuildDirectory 'D:\another-build\out\Default' -OutputDirectory 'D:\Arcium-Packages' -Version '0.1.0-alpha.4'
```

The list follows the runtime categories of pinned Chromium
156.0.8078.47's Windows packaging manifest, with a conservative inclusion of
all top-level DLLs and PAKs. It includes known browser/helper executables,
snapshot/ICU data, application manifests, notices and the `locales`,
`MEIPreload`, `IwaKeyDistribution`, `WidevineCdm`, bundled `Extensions` and
`VisualElements` folders when present. Folder structure is retained.

The helper requires nonempty core executable/resource files and the default
English locale, plus an external V8 snapshot. Missing files stop packaging
before output is created. It rejects links/junctions in selected runtime
entries and excludes debug/build files, logs and CSV exports. It does not
traverse arbitrary build-output folders, `obj`, `gen`, `Default`, `Profile *`,
`User Data`, caches, installers or the Helium updater executable.

The project license is copied as `LICENSE.Arcium.txt`. Existing build notices
and bundled component notices are retained; embedded credits stay in the PAKs.
Keep source/version and license information with any eventual release.

## Test the extracted copy

Extract the ZIP into a different folder, then run from the extracted folder
that contains `chrome.exe`:

```powershell
$testProfile = Join-Path $env:TEMP ('Arcium-Package-Test-' + [guid]::NewGuid())
.\chrome.exe "--user-data-dir=$testProfile"
```

A fresh test profile makes first-run setup visible and avoids handing the
launch to an existing Arcium profile's process. Your normal Arcium preferences,
extensions, flags and saved passwords are not part of this ZIP. Fresh profiles
start with the browser's defaults; profile customization must be chosen again.

Check `helium://version` for the executable path in the extracted folder and
the temporary profile path. Test browsing, restart with the same test profile,
onboarding, imports, window controls and any features you intend to offer.
Archive creation and a checksum do not prove the standalone browser works.
Publish only the candidate you have extracted and tested.

## Automated checks

Synthetic runtime fixtures exercise the script under the available PowerShell
hosts, including Windows PowerShell 5.1 and PowerShell 7 on Windows CI. They
check file selection, ZIP contents, checksum, unchanged source files, missing
runtime files, existing-output refusal, output placement and link rejection.
No real browser is launched by these tests.
