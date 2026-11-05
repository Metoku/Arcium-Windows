# Automation and personal maintenance

## Published state

[Windows x64 v0.1.0-alpha.3](https://github.com/Metoku/Arcium-Windows/releases/tag/v0.1.0-alpha.3) includes the corrected browser ZIP, installer, matching checksums and installer provenance. The maintainer reports local compilation, the New Tab caption fix and successful installer use. Source tests and installer CI provide additional, separate evidence; they do not establish every Windows UI or migration configuration.

The installer supplies an on-demand **Check for Arcium updates** shortcut. It selects published installer releases from this repository, verifies the download and asks before installation. Preview installs can see prereleases. Background updating and code signing are not implemented. Current packages are unsigned.

## Upstream monitoring

`Monitor Arcium upstream` runs every six hours, on manual dispatch and when its workflow/handler changes on main. It compares the pinned Arcium commit with `dr-baker/Arcium` main. Pull requests do not run this write-capable monitor.

When upstream differs, the monitor:

1. Starts a new `automation/arcium-core-update` branch from a snapshot of main, or merges current main into the existing candidate without rewriting its history. A merge conflict stops the run for manual resolution.
2. Updates only the candidate's `upstream/arcium-core.sha` file. Main and installed browser files are not updated.
3. Explicitly requests `Validate upstream tracking` on the candidate, because token-authored commits do not start ordinary push/PR checks. A dispatch failure fails the monitor run.
4. Opens a draft PR, or refreshes its managed status while preserving owner review notes.
5. Writes current/proposed revisions, the manual comparison link and the validation-request status to the run summary. Requested validation is not a passed validation result or a native build.

If repository policy denies automatic PR creation, the candidate and validation request are retained. A single permission issue is created/reused; its managed status is updated only when necessary. Other API failures remain failures rather than being mislabeled as a permission setting.

The monitor does not approve or merge PRs, publish packages, install updates or verify that the pin is the latest Chromium security release. Review Chromium security changes alongside upstream Arcium and the Windows platform, even when no browser features are needed.

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

The [installer workflow](../.github/workflows/windows-installer.yml) now defaults to the published alpha.3 runtime and an alpha.4 installer candidate. That default rebuilds distribution tooling around the same browser bytes. Choose a newly compiled runtime's published tag when native browser code changes. The workflow uploads test artifacts and never publishes a release itself.

Use a new package version, test the extracted ZIP and installer, then publish the exact installer, ZIP, both SHA256 sidecars and installer provenance. Keep alpha/beta releases marked as prereleases. Source checks, native compilation, headless launch, user-reported UI acceptance and signing are distinct release facts.

Remaining work includes broader update/profile/import coverage, optional signing and signed distribution, background updating, DRM acceptance and more complete Arc migration. These are not prerequisites for continuing a personal alpha build, and they are not advertised as completed.

## References

- [GitHub token authentication](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)
- [GitHub Actions repository settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)
- [Windows installer and updates](windows-installer-updates.md)
- [Incremental build](local-windows-incremental-build.md)
