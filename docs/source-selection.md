# Technical decision: Arcium core with selective Xelium references

**Decision (2026-11-01):** Continue building **Arcium-Windows** on the shared [dr-baker/Arcium](https://github.com/dr-baker/Arcium) core, with [imputnet/helium-windows](https://github.com/imputnet/helium-windows) as the Windows build-system reference. Use [minervanet/xelium-macos](https://github.com/minervanet/xelium-macos) only as a source of *ideas or individually reviewed patches*, never as a blanket patchset.

## Why

- Arcium's upstream README explicitly declares the repository to be the **shared browser product** and describes the architecture of separate platform repositories that pin a core commit. Arcium's shared patch series contains its own implementations of Spaces, Pins, Favorites, Peek, Little Arc and omnibox/command features.
- Xelium's README describes a personal Helium-based macOS build. Its `.gitmodules` points to the generic Helium core, not a separate shared Xelium browser core. It currently documents experimental workspaces outside the release branch.
- Helium's Windows repository is specifically the **Windows packaging layer**; its README documents native Windows toolchain prerequisites. None of the examined projects provides a ready-made Arcium-on-Windows patch stack.

## Xelium patch evaluation

The following are **candidates for analysis only**. All must be validated against the exact Arcium + Chromium revision using actual patch, compile and runtime tests.

| Xelium area | Existing Arcium capability | Windows-port recommendation |
|---|---|---|
| `helium/ui/floating-url-bar.patch` | Core `personal/arcium-omnibox.patch` plus its command-bar system | **Avoid direct import**: overlapping command-bar behavior, preferences and command IDs may conflict. Review interaction patterns, not implementation wholesale. |
| `helium/ui/link-peek.patch` | Core `personal/arcium-peek.patch` | **Avoid direct import**: both change link interception and preview behavior. Xelium's patch explicitly includes `helium_link_peek_modifiers_mac.mm`, so Windows input/modifier handling needs its own implementation. |
| `helium/ui/layout/address-bar-in-sidebar.patch` | Arcium has its own sidebar/omnibox UI | **Review selectively** for Chromium Views layout and preference wiring; likely overlap with existing layout/omnibox changes. |
| `helium/core/visual-tab-switcher.patch`, `helium/ui/visual-tab-switcher.patch` | Arcium has `personal/arcium-mru-tab-switcher.patch` | **Compare behavior and tests**, but do not replace or merge the patch sets unreviewed. |
| Sidebar sizing, native frame, compact toolbar patches | Arcium and Helium's own layout and glass system | **Reference as design/porting examples**; test Windows title-bar hit-testing and DPI behavior independently. |
| macOS signing, Sparkle update, rebrand patches | Windows release/update pipeline not implemented | **Do not port**; requires Windows-specific signing, packaging, and updater. |
| `experimental/workspaces` | Arcium already has shared Spaces and Pins | **Do not use as core**; Arcium is more aligned with this project's intended functionality. |

### Evidence

- [Arcium shared core README](https://github.com/dr-baker/Arcium/blob/main/README.md), [Arcium patch series](https://github.com/dr-baker/Arcium/blob/main/patches/series), [Arcium Peek](https://github.com/dr-baker/Arcium/blob/main/patches/personal/arcium-peek.patch), [Arcium Omnibox](https://github.com/dr-baker/Arcium/blob/main/patches/personal/arcium-omnibox.patch).
- [Xelium README](https://github.com/minervanet/xelium-macos/blob/main/README.md), [submodule](https://github.com/minervanet/xelium-macos/blob/main/.gitmodules), [patch series](https://github.com/minervanet/xelium-macos/blob/main/patches/series), [floating command bar patch](https://github.com/minervanet/xelium-macos/blob/main/patches/helium/ui/floating-url-bar.patch), [link peek patch](https://github.com/minervanet/xelium-macos/blob/main/patches/helium/ui/link-peek.patch).
- [Helium Windows build documentation](https://github.com/imputnet/helium-windows/blob/main/README.md).

## Implementation sequence

1. Audit Arcium core patch applicability on Windows at the pinned commit; record `IS_WIN`, `IS_MAC` and native Views code paths.
2. Reuse/adapt Helium Windows's source fetching, GN/Ninja settings, and packaging tools while retaining Arcium as the browser core.
3. Compile a minimal launchable Windows build *without Xelium patches*; validate browser startup and profile handling.
4. Exercise Arcium Spaces, Pins, Favorites, tab switching, Peek, and command bar on Windows with isolated profiles.
5. Only after establishing a functional baseline, compare Xelium behavior against concrete bugs or UX gaps. Import a small patch only when compatibility and regression tests pass.
6. Add binary CI, installer, update signing, and release channels after a working build exists.

## Safety gate

The current repository workflows validate source metadata and pinned checkout only. **They do not build a browser or prove patch compatibility.** This decision is based on inspecting upstream code and documentation, not a successful Windows compilation.
