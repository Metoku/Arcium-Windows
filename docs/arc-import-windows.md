# Import Arc's saved sidebar on Windows

This optional integration connects Windows Arc installations to Arcium's shared
Space picker and saved-Pins importer. It is maintained against the pinned
Arcium core `4e8f8e2bd3cdcab014ae9663907db93e915cb850` and Chromium
`156.0.8078.47`. Source replay and isolated parser fixtures are verified;
compilation and visible acceptance in the Windows browser are still required.

## Add it to the existing build

Let the running build finish or stop it before changing source. Close the
Arcium instance that uses `out\Default\chrome.exe`. From the repository root:

```powershell
python .\scripts\apply_windows_arc_workflow.py --feature arc-import --check
python .\scripts\apply_windows_arc_workflow.py --feature arc-import --apply
if ($LASTEXITCODE -ne 0) { throw 'Arc importer patch was not applied.' }
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 5
```

The check reports `ARCIUM_WINDOWS_ARC_IMPORT_READY` before application and
`ARCIUM_WINDOWS_ARC_IMPORT_APPLIED` afterwards. This optional patch can be
applied before or after the workflow-settings patch. Repeated application is
a no-op. The helper retains compilation output, respects source-file line
endings, and stops on source conflicts before writing. It does not reapply the
551 upstream patches or change GN build settings.

To remove only this integration, run `--feature arc-import --revert`, then
resume the build. Reverting source does not remove data already imported.

## Open the picker

After rebuilding, open **Settings → Appearance and behavior → Behavior →
Import from Arc**, or navigate directly to:

```text
chrome://setup/?import=arc
```

The query opens the existing standalone Arc picker. It does not restart the
setup wizard or change setup-completion and optional-service preferences.

1. Quit Arc normally so its latest sidebar is saved. Keep Arc installed until
   you have checked the result, and retain a backup of its data.
2. Review the detected Spaces and their attached profiles. Select the Spaces
   you want. A profile containing only Favorites has a selectable entry too.
3. Keep History off unless you deliberately want it. Click Import to start;
   merely opening the picker does not import anything.
4. Review the result and open an imported Space. Check nested folders and
   Favorites, then quit and reopen Arcium to verify persistence.

The existing shared coordinator keeps Spaces attached to the same Arc profile
together and creates separate Arcium destination profiles for distinct sources.
Imported records are dormant saved Pins, rather than every page opening at once.
The older `chrome://settings/importData` route remains available; choose Arc
and enable **Import sidebar as Pins** to import into the current Arcium profile.

## What is supported

| Data | Behavior |
| --- | --- |
| Saved Spaces and supported emoji/icons | Become Arcium Spaces in the selected source's destination profile |
| Pinned links and nested folders | Preserve saved order, folder hierarchy and collapsed state |
| Favorites | Import once per selected source profile |
| Empty folders | Remain folders |
| Split views | Their saved pages appear in order; the split layout is flattened |
| Cached favicons | Use the shared importer when source icons are available |
| History | Optional through the shared picker; starts off |
| Passwords, cookies, extensions and sign-ins | Not migrated by this sidebar flow |
| Today tabs, Little Arc windows, Easels and Boosts | Not converted into saved Pins by this integration |

Refreshing selected imported Spaces uses Arcium's existing reconciliation:
their imported saved trees can be replaced, while unselected Spaces are kept.
Keep independently maintained items in a separate local Space. Stopping an
import does not undo records already delivered; the shared result UI reports
partial completion. Arc's source data is read-only throughout the import.

## Windows discovery and format support

The previous Windows discovery path omitted the `Arc` component. The integration
checks each current-user package matching `TheBrowserCompany.Arc_*` under
`%LOCALAPPDATA%\Packages`, looking for `LocalCache\Local\Arc\User Data`.
It also checks `%LOCALAPPDATA%\Arc\User Data`. Older packaged layouts are
accepted only when the corresponding Arc sidebar actually exists. Unrelated
packages and incomplete installations are ignored.

Local State supplies profile names and directory IDs. The generic empty-ID
fallback is corrected to the actual `Default` directory; absolute paths,
parent traversal and missing profile directories are rejected. Several detected
installations are presented separately instead of arbitrarily choosing one.

The parser accepts existing alternating ID/object arrays and explicit-ID object
arrays, older `containerIDs` and enum-keyed `newContainerIDs`, and explicit
Default identities encoded as a boolean or an empty enum object. When a record
omits `childrenIds`, parent links preserve its stored item-array order. An
explicit children list, even an empty one, remains authoritative.

Only an unambiguous saved sidebar is accepted. Little Arc payloads, conflicting
record IDs, conflicting section IDs and ambiguous unkeyed collections are not
silently merged. Malformed JSON is reported through the existing unreadable-data
state; this integration does not rewrite escaping inside Arc's source file.

The shared machine-identity restrictions remain in force. Legacy custom profile
descriptors without machine IDs are supported. A machine-tagged custom profile
is excluded when its local identity cannot be verified; the Windows port does
not guess an Arc machine ID from a hostname, Windows registry ID or basename.
This can leave some profiles unavailable. Actual Windows snapshots must still
be checked before claiming complete migration coverage.

## Validation and references

- The optional workflow and import catalogs are replayed against the exact
  pinned source files, in both application orders with LF, CRLF and mixed file
  endings. Read-only checks, idempotence, byte-exact reversion and retained build
  output are checked. Windows CI also includes the pinned platform patches.
- The parser's C++ fixture suite includes nested folders, Favorites, split
  flattening, profile isolation, conflicting inputs and Windows serialization.
  Local isolated runs use compatibility adapters for Chromium base/GURL; they
  do not establish native Chromium API, URL-parser or Windows runtime behavior.
  Native `ArcSidebarSnapshotTest.*` and `ArcWindowsDiscoveryTest.*` remain the
  required C++ test targets when a Windows test build is available.
- The Settings resource XML and the changed TypeScript are checked separately.
  A successful patch replay is not a successful browser build or GUI import.

The implementation reuses Arcium's existing importer. Windows paths and format
variants were cross-checked against these open-source references; their browser
profile/session writers are not imported:

- [Arcium macOS import guide](https://github.com/dr-baker/Arcium-macOS/blob/main/docs/import-from-arc.md)
- [Zen's Arc migration and Windows discovery](https://github.com/zen-browser/desktop/blob/8f3ca12613c8d1794467389fcb287766107fd7f3/src/external-patches/firefox/arc_browser_migrator.patch)
- [Windows-compatible arc-export](https://github.com/andreafuredy/arc-export)
- [Arc-to-Zen path and sidebar references](https://github.com/Thinkscape/arc-to-zen)
