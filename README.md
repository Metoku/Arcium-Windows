# Arcium-Windows

> **Windows x64 alpha: [v0.1.0-alpha.3 is published](https://github.com/Metoku/Arcium-Windows/releases/tag/v0.1.0-alpha.3). The maintainer reports a working local browser, installer and corrected Mac-style window controls. Automated source checks and installer tests are separate from those runtime reports.**

Unofficial Windows platform project for [Arcium](https://github.com/dr-baker/Arcium), a Chromium/Helium-based browser. Independent of, and not endorsed by, the upstream maintainers.

## Install and use

Download **Arcium-Windows-0.1.0-alpha.3-Setup.exe** from the [alpha.3 release](https://github.com/Metoku/Arcium-Windows/releases/tag/v0.1.0-alpha.3), or extract its ZIP and launch `chrome.exe`. The release includes both checksum files and installer provenance. The installer and application are currently unsigned.

The installer provides Start-menu shortcuts, an optional desktop shortcut, the original Arcium icon at Windows display sizes, and **Check for Arcium updates**. Setup can register Arcium in Windows Default Apps; choosing it remains the user's action.

Arcium stores its profile in `%LOCALAPPDATA%\Arcium\User Data`, separately from Helium. Quit Arcium before backing up that folder. Updates and uninstall retain the profile. See [onboarding and profile isolation](docs/windows-onboarding.md) and [installer/update behavior](docs/windows-installer-updates.md).

If extension downloads are disabled after setup, see [services review and extension installation](docs/windows-extension-services.md).

Mac-style red/yellow/green buttons are optional. Enable `helium://flags/#arcium-mac-window-buttons` and relaunch. Alpha.3 includes the duplicate Windows-caption correction from [PR #39](https://github.com/Metoku/Arcium-Windows/pull/39). The maintainer confirmed the New Tab correction after a local incremental rebuild on 2026-11-05.

## Features and limits

The shared core supplies Spaces, profiles, Pins, Favorites, folders, split views, the command bar, Peek, recent-tab previews and Little Arc. Windows integrations expose their workflow and appearance controls, Arc sidebar discovery, password CSV import, first-run setup and separate browser identity.

- [Workflow and shortcuts](docs/arc-workflow-windows.md)
- [Sidebar Tidy, Clear and optional inactive-tab cleanup](docs/sidebar-tab-tools.md): local website grouping and Chromium tab recovery; requires a native rebuild of this candidate.
- [Space colors, customization and Windows Mica/Acrylic](docs/arc-appearance-windows.md)
- [Arc sidebar import](docs/arc-import-windows.md): supported Spaces, Pins, folders and Favorites; optional history. Imported split layouts are flattened and some source identities remain unavailable.
- [Saved passwords](docs/arc-password-import-windows.md): separate CSV import into the chosen profile. Cookies, existing sign-ins, extensions and passkeys are not transferred by that flow.
- [Mac-style window buttons](docs/mac-window-buttons.md): Windows minimize/maximize/close actions with a leading-button style. Broader DPI/accessibility acceptance is still needed.

Widevine/PlayReady playback has not been established for this release. Do not describe DRM-protected streaming as supported until actual encrypted playback is tested. Native macOS Liquid Glass is not a Windows renderer.

## Personal maintenance and builds

Use **Check for Arcium updates** when you want to update an installed copy. Preview releases require the preview-channel option. This is an on-demand checker, not a background updater; it verifies the release's installer/checksum pair before offering installation.

The [upstream monitor](.github/workflows/upstream-sync.yml) checks Arcium every six hours and prepares a separate review candidate with metadata, Chromium-hunk and Windows source checks. The [engine/feature watch](.github/workflows/upstream-watch.yml) also follows Arcium macOS, Xelium, the Windows platform and Google's Windows Stable engine baseline in one review issue. Neither workflow changes the installed browser, merges patches or publishes releases. Mac changes still need review and Windows porting. See [automation and maintenance](docs/automation.md).

The manual [Windows release-candidate workflow](.github/workflows/windows-release-candidate.yml) can build fresh browser code on a suitable dedicated runner, verify the runtime and packaged launches, and produce a ZIP, installer, checksums and correlated receipts. It uploads candidates for testing; it does not publish or install updates automatically.

Windows source is pinned to Chromium **156.0.8078.47**, Arcium core [ea530f48](https://github.com/dr-baker/Arcium/tree/ea530f4818599a12754b77daaea8e593feb0b443), and the tracked [Windows platform revision](upstream/helium-windows.sha). Upstream compatibility and security changes need review before adopting a new pin.

Existing local builds use [incremental resume](docs/local-windows-incremental-build.md). Keep `out\Default`; Git updates alone do not change the compiled browser. [Portable packaging](docs/windows-portable-package.md) copies a finished runtime. [Installer packaging](docs/windows-installer-updates.md) wraps that ZIP without recompiling Chromium.

## Validation and next work

CI covers Linux/Windows repository tests, pinned source and patch replay, API/compiler contracts, and installer install/upgrade/uninstall tests. Some workflows can attempt a full Windows Chromium build on a suitable host, but a metadata check is not a browser compilation. Alpha.3 was built and accepted locally by the maintainer; it is not claimed to be a fully automated native release build.

Current priorities are upstream/security maintenance, broader profile/import/upgrade testing and accurate release records. Signing, background updates, DRM and more complete migration remain separate work. See [automation](docs/automation.md) for the evidence and release procedure.

## Architecture and licensing

[Arcium core](https://github.com/dr-baker/Arcium) owns shared browser behavior and Chromium patches; this repository owns Windows platform integration, build helpers, tests and packaging. [Arcium-macOS](https://github.com/dr-baker/Arcium-macOS) and [Xelium-macOS](https://github.com/minervanet/xelium-macos) are references, not Windows build sources.

Original copyright notices and GPL/Chromium/third-party licenses are retained. Original Arcium icon attribution is in [installer assets](installer/windows/assets/README.md). Distribution and branding verification remain part of release maintenance.
