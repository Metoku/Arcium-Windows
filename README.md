# Arcium-Windows

> **Status: experimental Windows port. The first portable alpha is published; native build and runtime acceptance are user reports. Installer candidates receive separate Windows validation.**

Unofficial experimental Windows platform project for [Arcium](https://github.com/dr-baker/Arcium), a Chromium/Helium-based browser. This project is independent of, and not endorsed by, the upstream maintainers.

## Architecture

[dr-baker/Arcium](https://github.com/dr-baker/Arcium) owns shared browser behavior and Chromium patches. [dr-baker/Arcium-macOS](https://github.com/dr-baker/Arcium-macOS) is a macOS reference, not a Windows build source. This repository will own Windows platform integration, build scripts, testing and packaging.

## Automation

For a per-user installer and an on-demand update checker, see
[Windows installer and updates](docs/windows-installer-updates.md).
The GitHub installer workflow reuses a published portable ZIP, validates
installation/upgrades/uninstall and creates an installer candidate without
rebuilding Chromium. Installed users get a **Check for Arcium updates** shortcut.

To copy your existing browser runtime into a test ZIP, see
[Windows portable packaging](docs/windows-portable-package.md).
`.\scripts\package_windows_portable.ps1` creates a staged folder, ZIP and SHA256
checksum under `dist` while retaining the existing build output. It requires
no browser rebuild; the extracted package still needs a standalone launch test.

For synchronized Space colors, Windows Mica/Acrylic, rounded-frame and sidebar
controls, see [Windows workspace appearance](docs/arc-appearance-windows.md).
`--feature all --apply` validates and applies all five integrations as
one source transaction before an incremental build. Native compilation and
visible acceptance are still required for the appearance port.

For first-launch setup, browser import and an independent Windows profile, see
[Windows onboarding and profile isolation](docs/windows-onboarding.md).
Arcium uses `%LOCALAPPDATA%\Arcium\User Data` instead of Helium's profile folder.
Existing prepared trees need `--feature onboarding --apply` and an incremental
build; new browser-only builds apply this integration automatically before GN.

For the optional Windows workflow controls and reversible shortcut preset, see
[Arc workflow on Windows](docs/arc-workflow-windows.md). The integration applies
to an already prepared tree and requires an incremental browser build.

For opt-in red/yellow/green controls at the top left, see
[Mac-style window buttons](docs/mac-window-buttons.md). This separate frame
style keeps Windows actions and requires an incremental build, then enabling
its browser flag. Its native compilation and visible acceptance remain pending.

For the optional Windows Arc sidebar importer and Space picker, see
[Import from Arc on Windows](docs/arc-import-windows.md). It reuses Arcium's
saved-Pins importer with corrected Windows discovery and additional sidebar
format support. Windows browser compilation and real-data acceptance remain
required before calling migration complete.

The optional [Windows saved-password integration](docs/arc-password-import-windows.md)
restores local password-manager support and imports an Arc CSV export through
Chromium's native UI. It is separate from saved-sidebar migration and needs
Windows runtime acceptance after rebuilding.

CI can detect upstream changes and open reviewable update proposals. Until a Windows port compiles successfully, it must **not** claim to produce working binaries or automatically publish releases. Upstream revisions will be pinned and tested before adoption.

## Implemented repository foundation

- **Pinned upstream core:** [tracked SHA](upstream/arcium-core.sha).
- **Upstream monitoring:** [scheduled workflow](.github/workflows/upstream-sync.yml) (every six hours, opens reviewable update PRs).
- **Source validation:** [Linux and Windows checks](.github/workflows/validate.yml), including unit tests, upstream revision verification, and Windows checkout of the exact pinned core.
- **Windows source bootstrap:** [PowerShell script](scripts/fetch_core.ps1), which fetches the pinned source but **does not compile Chromium**.
- **Maintenance:** [Automation and GitHub settings](docs/automation.md) and [first Windows build milestone](https://github.com/Metoku/Arcium-Windows/issues/1).

## Roadmap

1. Track upstream core revisions and validate repository metadata.
2. Audit core patches for Windows compatibility.
3. Adapt a Windows Chromium/Helium toolchain and compile a first working browser.
4. Add Windows UI integration, smoke tests, and regression coverage.
5. Implement installer, signing, release channels, and secure updates.

## Licensing

Preserve original copyright notices and applicable GPL and third-party licenses when importing code. Review trademark and branding requirements before distribution.
