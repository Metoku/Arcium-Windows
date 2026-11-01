# Arcium-Windows

> **Status: early scaffolding. No functional Windows build yet.**

Unofficial experimental Windows platform project for [Arcium](https://github.com/dr-baker/Arcium), a Chromium/Helium-based browser. This project is independent of, and not endorsed by, the upstream maintainers.

## Architecture

[dr-baker/Arcium](https://github.com/dr-baker/Arcium) owns shared browser behavior and Chromium patches. [dr-baker/Arcium-macOS](https://github.com/dr-baker/Arcium-macOS) is a macOS reference, not a Windows build source. This repository will own Windows platform integration, build scripts, testing and packaging.

## Automation

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
