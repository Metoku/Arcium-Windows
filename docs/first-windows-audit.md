# First Windows source-staging result

The **Windows source staging** CI job completed successfully on 2026-11-01.

- [Successful workflow run](https://github.com/Metoku/Arcium-Windows/actions/runs/41310834472)
- [Downloadable JSON audit artifact](https://github.com/Metoku/Arcium-Windows/actions/runs/41310834472/artifacts/13085093486)
- Arcium core: `4e8f8e2bd3cdcab014ae9663907db93e915cb850`
- Helium-Windows platform: `e4b527255e3e0546ac140b7cb52d285fadb2d7d0` (0.20.1.1)
- Chromium: `156.0.8078.47`
- Shared patch entries: **521**
- Windows patch entries: **30**
- Chromium files touched by both sets: **9**
- Shared patches with simple macOS-code hints: **83**

**Interpretation:** The pinned source trees, patch manifests and Windows build entry points were retrieved and statically validated. The full Chromium patch series was **not** applied to source code; neither GN nor the compiler was run. These numbers do not prove patch conflicts, Windows API incompatibility, or a working browser.

## Nine intersecting Chromium files

1. `chrome/BUILD.gn`
2. `chrome/app/chrome_command_ids.h`
3. `chrome/browser/BUILD.gn`
4. `chrome/browser/chrome_content_browser_client.cc`
5. `chrome/browser/policy/configuration_policy_handler_list_factory.cc`
6. `chrome/browser/safe_browsing/BUILD.gn`
7. `chrome/browser/signin/signin_util_win.cc`
8. `chrome/common/BUILD.gn`
9. `chrome/test/chromedriver/BUILD.gn`

A file modified by two patches is **not necessarily a conflict**. Most Chromium builds intentionally touch the same build files in separate hunks. Review actual patch application logs rather than stripping out either patch set prematurely.

## macOS-specific implementation risk

The audit identified **83** shared patches that contain `BUILDFLAG(IS_MAC)` or likely macOS Objective-C++ paths (`.mm`). This is an intentionally broad *textual heuristic*. Much of the Helium browser legitimately contains platform-guarded code that is safe on Windows. These patches should be inspected for **unguarded** references or GN source list conditions when Windows compilation begins. In particular, prioritize Arcium's window title bar, glass surface, sidebar presentation, command bar, Spaces and Peek integration.

## Next acceptance gates

- [ ] Run patch application on an actual Chromium **156.0.8078.47** Windows source tree and capture first failing patch, if any.
- [ ] Fix/guard any Windows-incompatible Arcium code.
- [ ] Generate GN build files successfully.
- [ ] Compile browser binary successfully.
- [ ] Launch the browser with isolated profile on Windows.
- [ ] Validate Spaces/Pins/Favorites/command bar before any packaging or release.

The next operation is a heavy native Chromium build/patch attempt, which needs a Windows build host with ample disk space and a supported Visual Studio/Windows SDK toolchain. The [manual experiment workflow](../.github/workflows/windows-build-experiment.yml) supports an opt-in compile attempt on a configured runner but does not publish builds.
