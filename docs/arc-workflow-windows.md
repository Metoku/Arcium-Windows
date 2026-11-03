# Arc workflow on Windows

This integration exposes shared Arcium features in Windows Settings and adds a
reviewable, reversible Windows shortcut preset. It is maintained against Arcium
core `4e8f8e2bd3cdcab014ae9663907db93e915cb850` / Chromium `156.0.8078.47`.

The existing command bar, Spaces, Favorites, Pins, Peek and MRU preview code
remain the foundation. Xelium is a reference for discoverable settings and
comfortable layout; its overlapping command-bar and Peek implementations are
not imported.

## Add the controls to an existing local build

Close the Arcium instance using `out\Default\chrome.exe` before rebuilding.
From the Arcium-Windows repository root:

```powershell
python .\scripts\apply_windows_arc_workflow.py --check
python .\scripts\apply_windows_arc_workflow.py --apply
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 8
```

The first command is read-only. The apply command changes only the source
files in the catalog. It does not reapply the upstream patch stack, download
Chromium, change GN options, delete `out\Default`, or edit a browser profile.
The existing build regenerates affected Mojo/resource outputs and recompiles
the changed dependencies. The added UI requires this incremental compilation;
checking out the branch alone does not change an already-built executable.

The helper accepts `--source-dir` for a different prepared Chromium tree.
Repeated application is a no-op. A source mismatch fails before any write.
LF/CRLF differences between a Windows Git checkout and Chromium's source are
handled in temporary copies. Unchanged source lines retain their exact bytes;
inserted lines use each target file's dominant newline style. The helper never
normalizes the real source tree. Code/context differences still fail. Source
edits made during staging stop the write, and a write failure triggers rollback
of files already updated by the helper.
To remove the source integration, run the following, then resume the build:

```powershell
python .\scripts\apply_windows_arc_workflow.py --revert
```

Reverting source does not undo a shortcut preset you applied inside the browser.
Use **Restore previous shortcuts** in Settings before removing the UI if desired.

## Find the features

Open **Settings → Appearance and behavior → Layout** and look for **Arc
workflow**. The section provides:

- Sidebar navigation and its optional Extensions button. Sidebar navigation
  applies to left-side Vertical layout in supported normal windows.
- Peek link previews. Test with a normal HTTP(S) link's **Open Link in Peek**
  context-menu action; Xelium's Shift-click trigger is not assumed.
- Favorites and Pins in command-bar suggestions.
- Recent-use tab cycling and its thumbnail preview path. Hold Ctrl, press Tab,
  and release Ctrl to select. Site eligibility and existing browser settings
  still affect which previews can be shown.
- Little Arc's existing external-link preference. Windows external-link routing
  needs a runtime check; a visible toggle is not proof that routing works.
- Browser interface size, independently of website zoom.

Favorites, Pins and folders are persistent sidebar records, not ordinary tab
groups or new-tab-page shortcut tiles. Test creating one, closing its live tab,
and restarting the same isolated profile to verify the persistent record.

## Windows shortcut preset

Open **Settings → System → Keyboard shortcuts**. Choose **Review Arc shortcuts**
to see the supported mappings and any unavailable/reserved bindings. Applying
requires a separate confirmation. The existing shortcut service validates the
whole transaction, resolves modifiable conflicts, and saves the previous custom
configuration. Policy-managed settings remain authoritative.

Selected mappings are:

| Action | Windows preset |
| --- | --- |
| Pin/unpin current tab | Ctrl+D |
| Show/hide sidebar | Ctrl+S |
| Save page | Ctrl+Shift+S |
| Copy current URL | Ctrl+Shift+C |
| Recent / previous recent tab | Ctrl+Tab / Ctrl+Shift+Tab |
| Previous / next Space | Ctrl+Alt+Left / Ctrl+Alt+Right |
| Select Space 1–9 | Alt+1–9 |
| Previous / next tab in order | Ctrl+PageUp / Ctrl+PageDown |
| Add / separate split view | Alt+Shift+= / Alt+Shift+- |
| Focus split pane 1 / 2 | Alt+Shift+1 / Alt+Shift+2 |

These are Windows adaptations, not a claim of exact Arc shortcut parity.
Unlisted commands retain their configured shortcuts unless a listed mapping
takes a conflicting key. The preset does not change Space data, profiles,
cookies, sidebar layout preferences, or browser appearance. **Restore previous
shortcuts** restores the first saved configuration, including displaced
bindings; later shortcut edits are replaced. Review again after changing layout
or feature availability. A binding does not enable a disabled browser feature.

## Migration and remaining work

| Area | Current evidence / next requirement |
| --- | --- |
| Command bar | User screenshots show it opening on Windows. Verify search, open-tab switching and persistent-item results independently. |
| Settings and preset in this patch | Source replay and helper tests can run here; Windows compilation and visible UI acceptance are still required. |
| Arc sidebar import | Shared code exists. Windows source discovery, machine/profile identity and real Windows sidebar fixtures must be verified before claiming one-click Windows migration. |
| Passwords, cookies and extensions | Separate migration work. Do not promise retained sign-ins from a sidebar import or copy whole Arc profile directories into Arcium. |
| Window controls | First check `chrome://flags/#hide-window-buttons` and Frameless mode. Missing controls with both disabled need a Windows frame/layout investigation. |
| Glass, Space colors and full appearance editor | The Mac native renderer/settings layer needs a Windows implementation. This patch supplies existing workflow controls, not Mac glass parity. |
| Xelium workspaces | Its README marks them experimental/unreleased. Preserve Arcium Spaces as the existing data model. |

Before migration, preserve an Arc export/backup using Arc's own UI. Do not assume
that Mac import demonstrations establish Windows sidebar compatibility. The
import flow must show a preview, preserve source data, and report omitted or
unsupported records before it can be presented as a completed migration path.

## Runtime acceptance

Use the isolated test profile already used for the first Windows build.

1. Check every new toggle's saved value against `chrome://prefs-internals`,
   reopen Settings and relaunch to check persistence. Confirm managed settings
   cannot be changed.
2. Check each control's actual behavior, including ordinary windows, right-side
   tabs, private windows and full screen where relevant. Verify the current
   sidebar layout and persistent records survive toggling.
3. Record custom shortcuts, apply the preset, exercise sidebar/Pin/Space/recent
   tab actions, edit one binding, then restore. Verify original bindings return.
   Repeat with a reserved key and managed shortcut preferences.
4. Verify caption buttons, resizing, window dragging and Windows Snap in normal
   and maximized windows. Keep this separate from successful compilation.

## Sources

- [Arcium shared core](https://github.com/dr-baker/Arcium/tree/4e8f8e2bd3cdcab014ae9663907db93e915cb850)
- [Arcium Mac feature/settings contracts](https://github.com/dr-baker/Arcium-macOS/blob/main/docs/feature-settings-audit.md)
- [Xelium screenshots and feature list](https://github.com/minervanet/xelium-macos/blob/main/README.md)
- [Source selection and selective Xelium references](source-selection.md)
