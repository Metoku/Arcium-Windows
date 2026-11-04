# Windows onboarding and separate browser data

Arcium now uses `%LOCALAPPDATA%\Arcium\User Data` for its default Windows
profiles, extensions, settings, history and saved passwords. Helium continues to
use `%LOCALAPPDATA%\imput\Helium\User Data`. The change leaves all existing
Helium files intact, including data saved there by earlier Arcium builds.

The application name/ID, browser and PDF ProgIDs, direct-launch protocol,
application/Active Setup identity, notification/elevation/tracing class IDs,
product registry path, external-extension registry root (`Software\Arcium\Extensions`)
and Windows policy root are distinct. Existing COM
interface contracts stay unchanged. The build output still uses `chrome.exe`;
installer production, signing and update distribution remain separate work.

## Apply to an existing build

Close Arcium, update the integration branch, and apply the new catalog:

```powershell
cd D:\src\Arcium-Windows
git pull --ff-only origin codex/arc-workflow-windows
if ($LASTEXITCODE -ne 0) { throw 'Stop: repository update failed.' }
python -m scripts.apply_windows_arc_workflow --feature onboarding --apply
if ($LASTEXITCODE -ne 0) { throw 'Stop: onboarding was not applied.' }
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 8 -KeepGoing
```

The application marker is `ARCIUM_WINDOWS_ONBOARDING_APPLIED`. It validates all
eleven existing source files together, supports reapplication, and preserves
compiled output and user data. It also participates in the atomic
`--feature all` bundle. The optional Mac-style buttons remain a separate
`--feature mac-buttons` catalog and coexist with this change.
If the first published ten-file onboarding catalog was already applied, the
helper reports `UPDATE_AVAILABLE` and adds the separate external-extension
registry key only after the complete current catalog reverse-checks. Unknown
partial edits remain rejected without writes.

New `scripts/browser_only_build.py` builds apply onboarding, the independent
identity and native password support after the shared/Windows patch stages and before GN. An existing build
should use the source application and resume commands above; do not restage or
clean its output. A shared install header changes, so the incremental rebuild
can include more native files than a WebUI-only change.
The changed onboarding pages and localization are explicit GN action inputs,
so an incremental build regenerates the onboarding resources.

## First launch and import

Launch the rebuilt `work\windows-platform\build\src\out\Default\chrome.exe`
without an old `--user-data-dir` pointing at Helium. The new default profile
starts fresh, so previous appearance preferences and flags need to be chosen
again. Check **Profile Path** on `helium://version`; it should begin with
`%LOCALAPPDATA%\Arcium\User Data`.

The shared Arcium welcome screen then offers:

- **Arc:** the existing Space/Pin/Folder/Favorite import and Space picker.
- **Other browsers:** choose a detected browser/profile and import its supported
  bookmarks and history. Windows Helium is now explicitly listed when it has
  importable data. Its extensions and password database are excluded.
- **Start fresh:** continue setup without importing browser data.
- **Saved passwords:** the other-browser import screen links to the built-in
  password manager's settings in a new tab. Export a password CSV from the old
  browser, choose Import in Arcium, and select that local file. Password saving
  and filling also need the existing `passwords` catalog (included in `all`).

Browser import does not clone a profile or transfer extensions, cookies or
signed-in sessions. Arcium may still include its own bundled default extension;
that is independent of installed Helium extensions. Source discovery/import
errors retain their retry controls, and importing is optional.

Setup completion belongs to the Arcium profile. Completed profiles skip setup
on ordinary startup; private/guest windows and `--no-first-run` retain the
existing exclusions. Later imports are available in `helium://settings/importData`
and the Arc-specific route `helium://setup/?import=arc`.

`--feature onboarding --revert` restores the earlier source identity. It does
not move or delete either profile directory; a rebuilt reverted browser would
use the earlier Helium default again. Use the focused feature selector when
reverting unrelated appearance code.

## Validation and runtime acceptance

The pinned Windows replay reconstructs the actual onboarding release from the
core's SHA256-verified dependency. It applies all shared and Windows overlays,
checks both onboarding/catalog orders with LF, CRLF, mixed and absent-final-
newline files, verifies idempotence and exact reversion, and retains output and
an existing-profile sentinel. The default five-catalog bundle is exercised next
to the optional Mac captions.

Two isolated C++ contracts compile the real install constants/declaration,
default directory/registry functions and Helium discovery/filtering functions.
The source replay verifies both complete headers and all seven function bodies
against pinned Chromium/core/Windows source. It also checks the startup route
and separate policy root. These contracts do not constitute a Chromium link.

The actual onboarding frontend passes generated localization, Svelte/TypeScript
checking, its 124 existing interaction tests, Vite production build and GRD
generation. Chromium's separate Settings lint remains scoped to Chrome WebUI
resources. Full native compilation, fresh/second-launch behavior, simultaneous
Helium/Arcium use, taskbar/default-browser integration, real imports and password
save/fill remain Windows runtime acceptance checks.
