# Windows installer and updates

The installer wraps an existing portable ZIP. It compiles a small launcher
and setup program; Chromium is not rebuilt. Browser data stays in
`%LOCALAPPDATA%\Arcium\User Data`. Installation, updates and uninstall
do not copy or delete that profile or Helium's files.

## Build on GitHub

Open **Actions → Windows installer and updates → Run workflow**. Select the
published portable source tag and new package version, for example
`v0.1.0-alpha.1` and `0.1.0-alpha.2`. The job downloads this
repository's ZIP and sidecar, checks the SHA256 and GitHub asset digests,
then builds an installer candidate.

PRs changing distribution code also build a candidate from the existing alpha
ZIP. The artifact contains the `-Setup.exe`, `.sha256` sidecar,
`.json` provenance record and installed-browser smoke report.
Use candidates from successful runs only. The workflow has read-only repository
permission and uploads Actions artifacts; it does not publish or alter a release.

## Build locally

Install Inno Setup 7, then run from the repository in PowerShell:

```powershell
.\scripts\package_windows_installer.ps1 -PortableZip .\dist\Arcium-Windows-0.1.0-alpha.1.zip -Version '0.1.0-alpha.2'
```

The ZIP's matching `.sha256` file is required. Set `ARCIUM_ISCC` or
`-InnoCompiler` to an ISCC.exe path if necessary; `-OutputDirectory`
changes the output directory. Existing output candidates are refused. The
original ZIP and compiled browser output are retained.

The package version can differ from the portable source version for a release
that changes distribution tooling only. Both versions and the ZIP SHA256 are
recorded in the provenance. Chromium's compiled version is unchanged. Unexpected
archive roots, traversal, links, duplicate paths, profile files and unsupported
runtime entries are rejected.

## Installed behavior

The default application directory is `%LOCALAPPDATA%\Programs\Arcium`.
Setup requests no administrator privileges. Start-menu shortcuts open Arcium
and **Check for Arcium updates**. A desktop shortcut is optional. The launcher
forwards URLs and browser arguments directly without a command shell.
Windows can offer Arcium in Default Apps; setup does not force the default.

Browser files live under `versions\<package-version>`. Setup records
the active version after deploying files and retains the previous version.
Lower package versions are refused. A running launcher mutex makes setup and
uninstall ask the user to close Arcium. Existing unrelated application folders
are refused. Uninstall removes application files and owned registration while
retaining browser data. Use installed shortcuts rather than bypassing the
launcher to start a version folder's executable.

The inherited Helium updater is not used: this runtime layout does not meet
its Chromium installer/module-directory eligibility checks. Use **Check for
Arcium updates**. This change adds an on-demand update checker; it does not add
a browser-integrated update button or background update task.

## Channels and publishing

Setup's **Include alpha, beta and other preview updates** option selects
preview; clearing it selects stable. Preview packages select preview by
default. Inno Setup retains task choices on subsequent installations.
Stable excludes GitHub prereleases and semantic prerelease versions. Preview
includes stable and preview installers. SemVer ordering handles numeric
prerelease components correctly and never offers downgrades.

The updater reads published releases only from `Metoku/Arcium-Windows`.
A newer release must include these exact assets:

- `Arcium-Windows-<version>-Setup.exe`
- `Arcium-Windows-<version>-Setup.exe.sha256`

It asks before downloading/installing, validates URLs, sizes, checksums and
available GitHub digests, then runs setup. Download or verification failure
leaves the installed version available. ZIP-only releases are not installer
updates. API, network and rate-limit errors are reported.

Test the Actions candidate, then publish its installer, exact checksum and
provenance on the matching `v<version>` release. Checksums verify bytes;
they are not Authenticode signatures. Signing and signed release distribution
remain separate work. Current candidates are unsigned and may show Windows
publisher/SmartScreen prompts.

## Tests

PowerShell 5.1/7 contracts cover versions, channels, foreign URLs, checksums,
archive paths, profile exclusion, x64 PE headers and installation metadata.
The Windows job compiles real setup EXEs around a synthetic browser, installs,
forwards quoted/empty arguments, upgrades, rejects a downgrade and uninstalls
while retaining a CI-owned profile sentinel. It then builds an installer from
the real published browser and performs an isolated headless launch.

These tests do not establish interactive onboarding, real credential import,
Default Apps selection or every Windows UI/accessibility configuration.
