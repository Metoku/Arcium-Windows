# Automation and personal maintenance

## Published state

[Windows x64 v0.1.0-alpha.3](https://github.com/Metoku/Arcium-Windows/releases/tag/v0.1.0-alpha.3) includes the corrected browser ZIP, installer, matching checksums and installer provenance. The maintainer reports local compilation, the New Tab caption fix and successful installer use. Source tests and installer CI provide additional, separate evidence; they do not establish every Windows UI or migration configuration.

The installer supplies an on-demand **Check for Arcium updates** shortcut. It selects published installer releases from this repository, verifies the download and asks before installation. Preview installs can see prereleases. Background updating and code signing are not implemented. Current packages are unsigned.

## Upstream monitoring

`Monitor Arcium upstream` runs every six hours, on manual dispatch and when its workflow/handler changes on main. It compares the pinned Arcium commit with `dr-baker/Arcium` main. Pull requests do not run this write-capable monitor.

When upstream differs, the monitor:

1. Starts a new `automation/arcium-core-update` branch from a snapshot of main, or merges current main into the existing candidate without rewriting its history. A merge conflict stops the run for manual resolution.
2. Updates only the candidate's `upstream/arcium-core.sha` file. Main and installed browser files are not updated.
3. Checks validation runs for the exact candidate head and requests metadata, Chromium-hunk checks and the full Windows source replay when absent. Token-authored commits do not start ordinary push/PR checks, so these dispatches are explicit. A dispatch failure fails the monitor run. Matching runs are reused; a failed run needs a manual retry or a changed candidate rather than being repeated every six hours.
4. Opens a draft PR, or refreshes its managed status while preserving owner review notes.
5. Writes current/proposed revisions, comparison links and per-workflow `REQUESTED`, `RUNNING`, `PASSED` or `FAILED` status to the proposal and summary. Status is for the recorded candidate SHA. Requested validation is not a passed result or a native build.

If repository policy denies automatic PR creation, the candidate and validation request are retained. A single permission issue is created/reused; its managed status is updated only when necessary. Other API failures remain failures rather than being mislabeled as a permission setting.

The monitor does not approve or merge PRs, publish packages, install updates or verify that the pin is the latest Chromium security release. Review Chromium security changes alongside upstream Arcium and the Windows platform, even when no browser features are needed.

## Engine and feature watch

**Watch engine and feature updates** runs every six hours, separately from the
core-pin proposal. It compares the actual core/Chromium/Windows pins with:

- `dr-baker/Arcium` main, for shared feature changes.
- `dr-baker/Arcium-macOS` main and `minervanet/xelium-macos` main, for changes to review and port.
- `imputnet/helium-windows` main, for the Windows build/platform layer.
- Google's actively served Chrome Stable releases on Windows x64, as an engine release baseline.

The [VersionHistory API](https://developer.chrome.com/docs/web-platform/versionhistory/reference)
is queried for active Stable releases. Zero-fraction and ended rollouts are
excluded and versions are compared numerically. Chrome Stable is a baseline;
a matching number is not a security certification or proof of fork compatibility.

One **Upstream update watch: Chromium, Arcium and Xelium** issue holds the
comparison links and next steps. Its managed block preserves owner notes and
does not change when the source versions are unchanged. Closing an unchanged
issue acknowledges its current report; a new upstream revision/version can
reopen it. Failed API requests fail the run rather than reporting that everything
is current. Manual dispatch offers a report-only mode with no issue writes.

`upstream/feature-watch.json` records the two Mac watch baselines. They identify
where watching started or was acknowledged; they do not mean those features
have all been ported. Update them after reviewing the corresponding changes.
The core and Windows baselines come from the actual build pins. The watcher
does not alter any build pin or import patches, so AppKit/Cocoa or other Mac
changes cannot silently enter the Windows browser.

## One repository setting for automatic PRs

The initial monitor run was blocked by **GitHub Actions is not permitted to create or approve pull requests**. This is a repository administration setting, separate from the scoped token permissions already declared in the workflow.

On 2026-11-05, [the live monitor](https://github.com/Metoku/Arcium-Windows/actions/runs/42059498295) successfully created [draft PR #41](https://github.com/Metoku/Arcium-Windows/pull/41) as `github-actions[bot]`. This verified automatic PR creation and resolved [issue #28](https://github.com/Metoku/Arcium-Windows/issues/28). The steps below apply if the setting is disabled again.

Open [Settings > Actions > General](https://github.com/Metoku/Arcium-Windows/settings/actions). Under **Workflow permissions**, enable **Allow GitHub Actions to create and approve pull requests**, then **Save**. The workflow creates draft proposals; it contains no approval or merge operation. Keeping manual PR creation is also supported through the summary's compare link.

Run **Actions > Monitor Arcium upstream > Run workflow** on main afterward. An actual Actions-created draft PR verifies that the permission is enabled. Keep any new permission diagnostic open until that succeeds. The connected GitHub app used for project maintenance cannot change repository administration settings.

Workflow permissions remain scoped to the operations needed by the monitor. Other validation jobs retain read-only contents access. This change does not require a broader default token setting, personal access token or automatic merge rule.

## Reviewing an upstream candidate

Check the candidate's comparison and source metadata result. Then audit the Arcium core, Chromium version and Windows platform pins together. The optional integration catalogs are tied to those versions and may need refreshing.

Before adopting a candidate, run the appropriate patch/source checks and a native Windows build in a separate prepared checkout. Reusing the existing working build for source restaging can invalidate compiled output; preserve it for the current release. Confirm normal browsing, profile persistence and the features used personally before replacing the installed version.

For an installed update, quit Arcium, back up `%LOCALAPPDATA%\Arcium\User Data`, and use the update checker or the tested installer. Source changes require a compiled runtime before packaging; rebuilding an installer around an older ZIP does not include new browser code.

## Release procedure and remaining work

### Fresh native release candidate

**Build Windows release candidate** is a manual workflow. Select the reviewed
integration branch and a new package version. It requires the existing
`ARCIUM_NATIVE_WINDOWS_RUNNER` repository variable to name a suitable dedicated
Windows runner label (or a sufficiently large hosted runner). The preflight
requires at least 16 logical CPUs, roughly 64 GiB RAM and 150 GiB free SSD.
An ordinary hosted runner fails before downloading Chromium. No paid runner is
started or configured by these source changes, and scheduled monitoring never
launches this expensive workflow. Your existing local incremental build remains
available for personal maintenance.

The candidate workflow runs source checks, applies all reviewed Windows
catalogs and the optional Mac-button implementation **before branding**, then
compiles `chrome` with the reviewed SDK and compiler cache. It launches the
native browser with disposable data, creates a ZIP from that build, launches
the packaged runtime with another disposable profile, and builds the installer
from that ZIP. It never downloads an old released browser as its build input.

The final gate verifies the exact integration/core/Windows/Chromium revisions,
native-build success, both launch results and executable hashes, every ZIP
file against the newly compiled output, both checksum sidecars and installer
provenance. A different DLL/resource, stale ZIP, incomplete runtime, profile
file, failed launch or mismatched receipt prevents candidate upload. The
receipt records that interactive acceptance, signing and publication are still
incomplete; it is CI evidence, not a cryptographic build attestation.

Successful runs upload six release-candidate files: ZIP, ZIP SHA256, installer,
installer SHA256, installer provenance JSON and the release-candidate receipt.
Failed runs upload diagnostics only. No installer is run on a potentially
personal build runner, and nothing is published to GitHub Releases automatically.
Test normal browsing, service/extension installation, Spaces, password filling,
restart persistence and an installed upgrade before publishing. The separate
installer CI continues to exercise setup lifecycle behavior on disposable hosts.

### Publish an accepted candidate

Download the candidate artifact, retain its receipts and test it on Windows.
Create the matching `v<package-version>` prerelease and upload the exact six
files. Keep the published checksums and provenance together. The installed
**Check for Arcium updates** can then discover that Windows installer; it does
not install Mac releases or source commits. This remains on-demand updating.

### Distribution-only repackaging

The [installer workflow](../.github/workflows/windows-installer.yml) now defaults to the published alpha.3 runtime and an alpha.4 installer candidate. That default rebuilds distribution tooling around the same browser bytes. Choose a newly compiled runtime's published tag when native browser code changes. The workflow uploads test artifacts and never publishes a release itself.

Use a new package version, test the extracted ZIP and installer, then publish the exact installer, ZIP, both SHA256 sidecars and installer provenance. Keep alpha/beta releases marked as prereleases. Source checks, native compilation, headless launch, user-reported UI acceptance and signing are distinct release facts.

Remaining work includes native acceptance of future revisions, broader update/profile/import coverage, optional signing, background updating and more complete Arc migration. DRM is outside the current personal-use scope. Monitoring does not guarantee that every future Arcium/Xelium feature can be adopted without Windows porting.

## References

- [GitHub token authentication](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)
- [GitHub Actions repository settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)
- [Windows installer and updates](windows-installer-updates.md)
- [Incremental build](local-windows-incremental-build.md)
