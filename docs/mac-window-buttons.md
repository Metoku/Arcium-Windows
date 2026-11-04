# Mac-style window buttons on Windows

This optional frame style places Close (red), Minimize (yellow), then
Maximize/Restore (green) at the top left. The circles show symbols on hover or
press, darken when pressed, and turn gray for inactive or disabled controls.
The buttons retain their Windows actions and accessible names. Green uses
Windows maximize/restore; it does not enter macOS full screen.

The style is disabled by default. Normal browser windows with a custom titlebar
can opt in. App/popup windows, native system titlebars, right-to-left layouts,
touch mode and forced-color/high-contrast themes retain Windows controls.

## Apply to an existing build

Exit the running Arcium build, then run from the repository root:

```powershell
git pull --ff-only origin codex/arc-workflow-windows
python -m scripts.apply_windows_arc_workflow --feature mac-buttons --apply
```

After `ARCIUM_WINDOWS_MAC_BUTTONS_APPLIED`, resume the existing build:

```powershell
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 8 -KeepGoing
```

Source and compiled output are retained. This is a separate opt-in style;
`--feature all` retains its existing four-catalog workflow/import/appearance
scope. The caption style can be applied before or after that bundle.

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

CI replays the style before and after the full four-catalog bundle with LF,
CRLF, mixed endings and absent final newlines. It checks idempotence, exact
reversion and retained build output. Compiler contracts exercise the actual
patched eligibility, painting, button ordering, layout/exclusion and frame-hit
functions, with each function excerpt verified against reconstructed pinned
source. New Canvas/View API declarations are checked against their effective
pinned headers. These checks do not establish full Chromium compilation or
native Windows rendering for this new style.

Before accepting it, check all three actions, green maximize/restore after
resize, dragging between buttons, Windows Snap, full screen, frameless/sidebar
reveal, theme/accessibility changes and 100/125/150/200% display scaling in
Classic and Vertical layouts. The previously working browser build establishes
the baseline; this new style still needs its own native build and UI checks.
