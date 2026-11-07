# Sidebar tab tools

The vertical sidebar has **Tidy**, **Clear**, and **…** controls above New Tab.
The controls hide with the collapsed sidebar and return when it expands.
Their menu keeps an auto-hiding sidebar open while you use it.

## Local Tidy

Tidy groups two or more ordinary, ungrouped HTTP/HTTPS tabs by website. It
uses Chromium's registrable-domain rules, including private suffixes, rather
than treating unrelated sites on a shared hosting service as one website.
Groups receive the website's name. Single tabs, existing groups, Pins,
Favorites, and split views keep their existing organization.

This is local website grouping, not Arc Max's AI categorization. Tab contents
and browsing data are not sent to an AI service. Repeating Tidy does not
reorganize groups it has already created.

## Clear and recovery

Clear invokes the existing **Clear unpinned tabs in this window** command.
That command retains durable Pins/Favorites and uses normal historical-tab
closure. Its Windows Arc shortcut preset is **Ctrl+Shift+K**.

Open **… → Restore last closed tab**, or press **Ctrl+Shift+T**, to restore a
closed tab. **… → Search tabs and recently closed** opens Chromium's tab
search and its recently closed list. Recovery uses Chromium's normal bounded
session history; this is not an unlimited tab archive or a profile backup.
Private browsing follows Chromium's normal private-session recovery limits.

## Optional automatic cleanup

Open **… → Automatically clean up inactive tabs** and select **Off**, **12
hours**, **24 hours**, **3 days**, or **7 days**. Off is the default. The
setting persists separately in each Arcium profile, across its Spaces.

While a normal vertical-sidebar window is open, an enabled timer checks every
five minutes and closes at most eight eligible tabs per pass. Enabling the
feature, changing its duration, and starting the browser do not immediately
close tabs. Recently navigated pages receive the same inactivity grace period.

Automatic cleanup preserves active, visible, selected, pinned, persistent,
and split tabs. It also preserves edited forms/contenteditable pages,
before-unload pages, loading pages, playing video/audio, Picture-in-Picture,
capture/WebRTC sessions, connected devices, DevTools, and pages holding web or
blocking database locks. Unknown page state is preserved. Tabs with extension
auto-discard protection are preserved too.

It does not run in private profiles or when saving browser history is disabled.
Each candidate is checked again immediately before closing; a Space switch,
browser shutdown, disabled setting, or tab move cannot redirect the sweep to
another browsing context. At least one tab remains in the window.

## Add to an already prepared candidate

Finish or stop any running compilation before changing its source. Close the
browser executable from that output folder before rebuilding. In the reviewed
feature checkout, use the existing prepared tree:

```powershell
python -m scripts.apply_windows_arc_workflow --feature tab-tools
if ($LASTEXITCODE -ne 0) { throw 'Tab-tools compatibility check failed.' }
python -m scripts.apply_windows_arc_workflow --feature tab-tools --apply
if ($LASTEXITCODE -ne 0) { throw 'Tab-tools application failed.' }
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 8
```

Keep `work\windows-platform\build\src\out\Default`. The helper updates five
existing source/resource inputs atomically, recognizes an already-applied
catalog without rewriting timestamps, and retains unrelated compiled output.
It does not change the engine pin or GN flags. Fresh complete bundles include
the same integration before branding.

## Validation

Repository tests compile the actual grouping/eligibility functions and cleanup
loop in a C++ host. Browser adapters simulate protected page state, tab moves,
selection/edit changes, Space changes, settings/history-policy changes, and
shutdown during a sweep. Transaction tests cover all supported line endings,
read-only checks, idempotence, conflict rejection, and object/profile retention.

The pinned source replay checks the actual Chromium API declarations, default
preference registration, GRIT message bindings, all optional-catalog coexistence
orders, and the same C++ host against the effective patched source. These
checks do not compile the full native browser or verify Windows rendering.

After a native rebuild, check: expanded/collapsed/hover sidebars, Space editor
visibility, keyboard access, DPI/theme contrast, Tidy on grouped/split/pinned
tabs, Clear/recovery, cleanup duration persistence, and the protected-state
cases above. Keep native build/interactive acceptance separate from source
validation before packaging a new release.
