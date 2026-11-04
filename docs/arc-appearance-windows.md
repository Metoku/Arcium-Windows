# Windows workspace appearance

This optional integration adapts Arcium's Space palette and glass model to
Windows and combines it with the compact sidebar and adjustable frame approach
shown by Xelium. It is a source port: a successful patch replay is not evidence
that a Windows browser compiled or rendered correctly.

## Apply to an existing build

Update to the current `codex/arc-workflow-windows` branch, then run from the
Arcium-Windows repository root:

```powershell
python .\scripts\apply_windows_arc_workflow.py --feature all --check
python .\scripts\apply_windows_arc_workflow.py --feature all --apply
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 8
```

The bundle includes workflow controls, Arc sidebar discovery/import, saved
password CSV support and appearance. Source files may use LF, CRLF, mixed endings
or omit the final newline. Formatting is normalized only in temporary snapshots;
the original source ending style and final-newline presence are preserved. It rehearses the complete operation in a
temporary copy before committing source changes together. Existing outputs and
browser profiles are retained; a later mismatch cannot leave earlier catalogs
partly applied. Already applied catalogs are retained. The known old shortcut
lint error can be upgraded by the existing helper.

If an earlier appearance patch is already installed, the helper recognizes its
exact CSS, WebUI handlers, surface-label expression, snapshot signatures and
gradient color block and
reports `UPDATE_AVAILABLE`. Applying again upgrades those source files only after
the complete corrected appearance catalog can be reversed. This covers all five
previous appearance versions. Unknown source edits inside the catalog's hunks
or an incomplete catalog are rejected without source writes. Generated output
is retained.

The Settings snapshot declaration and definition are non-const because they
use Chromium's non-const `WebUIMessageHandler::web_ui()` accessor. The frame
gradient uses `SkColor4f::FromColor` for its two stops, matching the pinned
`PaintShader::MakeRadialGradient` API. Reapplying to the latest installed version
changes only that gradient block. It does not require reverting the integrations
or cleaning `out/Default`.

`--feature appearance` selects only this integration. `--feature all --revert`
reverts all four optional source integrations; it does not undo user appearance
choices or delete imported records. Rebuild after either application or reversion.

Header and Mojo changes can invalidate more than a few object files. Reusing the
existing build avoids a deliberate clean build but does not guarantee a short
incremental compilation. Do not delete `out/Default`, rerun staging or clean the
source to apply these catalogs.

After compilation finishes, close the previous browser process, launch the
rebuilt executable, and open `chrome://settings/appearance`. **Workspace
appearance** appears in the Layout view. Select **Apply Arc + Xelium layout**
for left vertical tabs, navigation in the sidebar, a 220 px sidebar, 110% browser
UI scale, rounded content and a 5 px base frame inset. This explicit action turns
Frameless mode off and selects the fully hidden collapsed-sidebar style. It
does not write the collapsed state, shortcuts, colors, saved tabs or imported
records. All preset preferences are checked before the first write;
managed settings reject the action. Individual controls remain available.

## One Space palette, two entry points

Workspace appearance and Customize Chrome/Helium use Arcium's existing settings
model and Space palette writer. The model captures the hosting window's
**explicitly assigned Space**, never whichever browser happens to be last active.
Private/guest, detached, unassigned and mismatched-profile contexts fail closed.
The Space picker chooses a target within this profile; switching foreground
windows does not redirect a pending edit. Each mutation carries its target ID.
Deleted targets reject old mutations and can be recaptured by refreshing.

Color, up to four gradient points, their positions/radii/opacities, and control
and panel color intensity are edited through the shared model. Palette writes
preserve Space names, icons, Pins, Favorites, page mode and other recipe fields.
Reset colors affects only the selected Space's palette. Layout, the decorative
color-effect mode and material choices retain the shared core's profile scope.
Browser appearance and page appearance are separate Space choices; pages can
follow the browser. Changing appearance does not toggle optional services.

The legacy color picker reads/writes the same Space palette on Windows. Its
profile-wide light/dark/device-color controls are omitted in favor of the Space
appearance editor. Wallpaper upload and toolbar customization remain available.
An already-open compact Space editor observes externally saved theme changes;
it updates its draft palette so a later Save cannot restore an older palette.
Changes to names, Pins or unrelated Spaces do not replace that draft.

The right-side Customize panel has a visible **Close** button and handles
**Escape**. Handled/composing keys are respected, listeners are removed when the
component disconnects, and the host coordinator transfers focus back to the page.
**Workspace appearance** opens the same Settings editor. Navigation and dismissal
use the panel's own browser context. The native Space form retains Cancel/Escape.

## Windows materials and geometry

Window material offers Mica, Frosted/Acrylic and Solid. Windows 11 build 22621+
and Chromium's DirectComposition window surface are required for the native
path. Mica uses `DWMSBT_MAINWINDOW`; Frosted uses `DWMSBT_TRANSIENTWINDOW`. The
frame paints the captured Space tint and gradients above the Windows backdrop,
then applies the shared palette's readability floor. The opacity slider cannot
reduce that readability minimum. macOS Liquid Glass is not advertised as a
Windows renderer; imported Liquid Glass selections resolve through the shared
fallback to Acrylic where available.

Native setup must succeed before the shared Views surfaces become transparent.
DWM installation/extension failures, unsupported composition, private/guest/app
windows, policy themes, high contrast, disabled Windows transparency, and
explicit opaque renderer overrides retain solid rendering. Windows settings
messages refresh cached OS availability. The UI distinguishes an active material
from fallback; native browser acceptance must still verify the actual pixels.

Caption buttons, hit-testing and resize/drag/Snap layouts remain owned by the
existing Windows frame. This patch supplies a background painter, not replacement
caption buttons. Floating panels retain the existing Chromium glass renderer.
Controls expose surface presets, command/preview backing opacity and tint,
sidebar width, collapsed style, browser scale, frame inset, content border and
content shadow. These are backed by existing render/layout consumers.

## Requested feature coverage

| Requested area | Integration and remaining acceptance |
| --- | --- |
| Arcium Space colors, gradients and appearance controls | This integration uses the shared model and palette; native Windows visual/restart acceptance pending. |
| Xelium compact sidebar, comfortable sizing and rounded frame | Explicit layout preset and adjustable existing Arcium geometry; verify narrow widths, DPI and keyboard navigation. Overlapping Xelium implementations are not stacked on top of Arcium. |
| Window glass | Windows DWM implementation with supported-system checks and opaque fallback; native compilation/rendering pending. |
| Right-side customization dismissal | Close and Escape use the owning panel coordinator; native focus/close acceptance pending. |
| Command bar, Favorites/Pins suggestions, Peek and recent-tab switcher | Existing shared runtime plus workflow switches; verify the actual actions, not just their saved values. |
| Spaces, Favorites, Pins, folders and Arc migration | [Windows sidebar integration](arc-import-windows.md); test real exports and profile isolation. Machine-tagged identities remain excluded when unverifiable. |
| Saved passwords | [Native CSV import](arc-password-import-windows.md) in the matching destination profile; saving/fill/restart acceptance pending. |
| Shortcuts and Little Arc | Existing shared functionality and reversible Windows preset; availability is separate from assigning a shortcut. |
| Retained sign-ins, extensions and Xelium experimental workspaces | Not established by these patches. Cookies/extensions require separate migration; Arcium Spaces remain the workspace data model. |

## Validation and native acceptance

Repository tests compile the actual new Windows availability, backdrop controller
and window-to-Space capture functions in small C++ hosts with API contract
doubles. Another host compiles the actual Settings snapshot declaration,
preference table and complete method body against a non-const `web_ui()` API.
The old declaration/definition must fail compilation with a `web_ui` diagnostic;
the corrected pair must compile and pass snapshot-state checks. A frame-paint
host compiles the complete actual `OnPaint` method against the gradient API
excerpt in `tests/fixtures/paint_shader_radial_gradient.h`. Source replay verifies
that excerpt verbatim against the pinned Chromium header before accepting it.
The old integer-color call must fail compilation; the corrected float-color call
must pass RGB/alpha, center/radius, readability-layer order, opaque-backdrop and
standard-titlebar fallback checks. They check OS/accessibility settings, DWM failures, composition surface
requirements, private/guest/policy contexts, mismatched profiles and explicit
Space ownership. They do **not** link against Chromium or call Windows DWM.

The pinned-source replay checks all 24 catalog orders with LF, CRLF, mixed
endings and missing final newlines (96 combinations), idempotence, read-only
checks, exact reversion, resource XML and retained build output. The optional TypeScript checker exercises actual patched event
handlers, panel dismissal and template controls with typed WebUI adapters.
Appearance CSS also runs through Stylelint 17.0.0 and the unmodified rules from
Chromium 156.0.8078.47's `stylelint.config_base.mjs`, with its pinned stylistic
plugin. The earlier compact stylesheet reproduces the 29 native build errors;
the corrected stylesheet passes with zero warnings. CI uses the pinned
TypeScript 6.0.2 compiler for the isolated typed adapters and exercises the
already-installed CSS upgrade against reconstructed source.

The checker also downloads Chromium's exact ESLint config and WebUI rules at the
pinned revision. It checks all seven patched TypeScript/template files, including
click/change handler names and lifecycle method order. The six rules requiring
the absent transitive/generated graph are explicitly listed as skipped in the
partial-source report. The strictly typed Settings adapter additionally runs all applicable default
rules on both the class and HTML template, including unnecessary assertions,
reactive-property and expression-binding checks. It preserves the actual Lit
import names so the upstream template rules execute. Compiler flags come from
the pinned Chromium `tools/typescript/tsconfig_base.json`; the pair also passes
with indexed-access checking disabled for compatibility with existing builds.
Negative controls must reproduce the two reported panel errors and the Settings
lifecycle/assertion errors and the reported surface-label assertion before
validation passes.

Twenty installed-version upgrade replays cover all five earlier appearance catalogs
with LF, CRLF, mixed endings and absent final newlines. They check exact source
results, read-only detection, unchanged unrelated source and retained build output.

Chromium's complete transitive TypeScript/Mojo/C++ build remains a separate gate.

Before marking this port accepted, use a disposable browser profile to verify:

1. Two Spaces with different palettes; both customization entry points and the
   compact editor agree after editing, switching Spaces and restarting. Edit in
   one of two profile windows and confirm another window cannot redirect it.
2. Close and Escape from the right panel, focus restoration, reopen and wallpaper
   upload. Check input composition and nested menus before testing Escape.
3. Mica/Acrylic/Solid transitions, transparency/high-contrast changes, older Windows
   or software rendering, disabled effects and managed appearance.
4. Caption buttons, maximize/restore, dragging, resize and Windows Snap at 100%,
   125%, 150% and 200% display scaling, plus full screen and narrow sidebars.
5. Command bar results, Peek, Ctrl+Tab preview, Pins, Favorites, splits, imports,
   password saving/fill/restart and the existing shortcut restore path.

## References

- [Arcium macOS features and settings contracts](https://github.com/dr-baker/Arcium-macOS/blob/main/docs/feature-settings-audit.md)
- [Xelium appearance and workflow references](https://github.com/minervanet/xelium-macos/blob/main/README.md)
- [Microsoft DWM system backdrop contract](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type)
- [Chromium desktop window host](https://github.com/chromium/chromium/blob/156.0.8078.47/ui/views/widget/desktop_aura/desktop_window_tree_host_win.cc)
