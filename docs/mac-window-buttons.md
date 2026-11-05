# Mac-style window buttons on Windows

This optional frame style places Close (red), Minimize (yellow), then
Maximize/Restore (green) at the top left. The circles show symbols on hover or
press, darken when pressed, and turn gray for inactive or disabled controls.
The buttons retain their Windows actions and accessible names. Green uses
Windows maximize/restore; it does not enter macOS full screen.

The HWND host uses the same eligibility check as the buttons, including before
the FrameView exists. Eligible windows select custom frame drawing so native
caption glyphs do not show underneath transparent New Tab chrome. A deferred
native-frame transition can become custom during a theme/full-screen change;
the handler refreshes that client frame without taking the system-only path.
Other window types and the existing RTL/touch/high-contrast fallbacks keep
their previous frame behavior.

The style is disabled by default. Normal browser windows with a custom titlebar
can opt in. App/popup windows, native system titlebars, right-to-left layouts,
touch mode and forced-color/high-contrast themes retain Windows controls.

## Apply to an existing build

Exit the running Arcium build, then run from the repository root:

```powershell
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Repository fetch failed.' }
git switch main
if ($LASTEXITCODE -ne 0) { throw 'Could not switch to main.' }
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw 'Repository update failed.' }
python -m scripts.apply_windows_arc_workflow --feature mac-buttons --apply
if ($LASTEXITCODE -ne 0) { throw 'Caption fix was not applied.' }
```

After `ARCIUM_WINDOWS_MAC_BUTTONS_APPLIED`, resume the existing build:

```powershell
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 5
```

Source and compiled output are retained. This is a separate opt-in style;
`--feature all` covers workflow, imports, appearance and independent Windows
onboarding/profile identity. The caption style can be applied before or after
that bundle.

The helper recognizes the earlier caption patch that called
`button->PreferredSizeChanged()`. That method is protected in Chromium 156.
It also recognizes the complete earlier six-file caption catalog and upgrades
the shared policy, host mode and transition handler in temporary snapshots.
The frozen earlier catalog and the complete new catalog must both validate
before source files are committed. The protected call, when present, becomes
the public `InvalidateLayout()`. A read-only check reports
`UPDATE_AVAILABLE`; unknown partial edits remain rejected.

This correction changes native C++ and needs an incremental browser rebuild.
Keep `out\Default` and resume the existing build; do not restage Chromium.
An installer rebuilt from the old portable ZIP still contains the old frame
code. Test the newly compiled `out\Default\chrome.exe` after exiting
Arcium completely, then package that updated runtime.

Launch the freshly built browser and open
`helium://flags/#arcium-mac-window-buttons`. Enable **Mac-style window buttons**
and relaunch. Keep **Hide window buttons** disabled. Once the new style is
compiled, selecting Disabled and relaunching restores the Windows appearance
without another rebuild.

For permanently visible controls, disable Frameless mode or pin the relevant
chrome. Top-bar pinning applies when navigation is outside the sidebar. The
separate **Show or hide toolbar** command controls toolbar visibility itself.

To remove the source integration, use the same helper with
`--feature mac-buttons --revert`, then rebuild incrementally.

## Verification

The existing Windows buttons, callbacks, IDs and accessibility names are reused.
The frame reserves leading space and hit-tests the relocated controls before
the client toolbar/sidebar can claim their clicks. Resize borders retain
priority, and the old right-side DWM button rectangle is ignored in the new
layout. Existing maximize/restore hit codes and action bindings remain in place.
Caption input follows the supplied reveal ratio, including sidebar navigation.

The additional handler write scope is limited to
`ui/views/win/hwnd_message_handler.cc`. Compiler contracts reproduce the
previous native-caption dispatch and the system-only transition CHECK, then
exercise the corrected paths, pending full-screen transitions and native
fallbacks. Pinned replay verifies the actual handler bodies and the public
static policy declaration. Both earlier complete caption variants upgrade
under LF, CRLF, mixed and absent-final-newline source formats without rewriting
unrelated source or compiled output.

CI replays the style before and after the workflow/import/appearance bundle with LF,
CRLF, mixed endings and absent final newlines. It checks idempotence, exact
reversion and retained build output. Compiler contracts exercise the actual
patched eligibility, painting, button ordering, layout/exclusion and frame-hit
functions, with each function excerpt verified against reconstructed pinned
source. New Canvas/View API declarations are checked against their effective
pinned headers, including public/protected access. The caption group contract
derives both controls and their container from a View model with the verified
access labels. It compiles the corrected call and requires the reported old
call to fail compilation. Four source-format cases upgrade the earlier caption
catalog without rewriting unrelated files. These checks do not establish full Chromium compilation or
native Windows rendering for this new style.

Before accepting it, check all three actions, green maximize/restore after
resize, dragging between buttons, Windows Snap, full screen, frameless/sidebar
reveal, theme/accessibility changes and 100/125/150/200% display scaling in
Classic and Vertical layouts. The previously working browser build establishes
the baseline. On 2026-11-05 the maintainer reported a successful incremental
build and confirmed that the duplicate Windows controls disappeared on New Tab
pages. The corrected runtime is in the published alpha.3 release. Broader
DPI, accessibility and theme/full-screen configurations remain acceptance work.
