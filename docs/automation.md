# Automation and release policy

## What works today

- `upstream/arcium-core.sha` pins an exact shared Arcium commit.
- `Monitor Arcium upstream` checks `dr-baker/Arcium` every six hours (and on manual dispatch). When the upstream commit differs, it updates a candidate branch and opens a pull request **for review**, not an automatic merge.
- `Validate upstream tracking` runs offline Python unit tests on Linux and Windows and verifies the pinned commit exists upstream on Linux.
- The upstream workflow explicitly dispatches validation on its candidate branch because commits made with `GITHUB_TOKEN` ordinarily do not trigger subsequent push or pull-request workflows.

## Not implemented yet

There is **no Windows browser executable, Chromium build, browser-level smoke test, installer, signing, stable release, or automatic client updater**. Passing metadata tests must not be interpreted as functional browser compatibility. Do not advertise or publish binary releases until the browser actually compiles and passes runtime tests.

## Required GitHub settings

1. Go to **Settings > Actions > General** for this repository.
2. Allow GitHub Actions to run. Ensure **Workflow permissions** give the token enough access for the upstream workflow (`contents: write`, `pull-requests: write`, `issues: write`, `actions: write` as scoped in the workflow).
3. Enable **Allow GitHub Actions to create and approve pull requests**, if your repository settings expose that option. If this is disabled, the upstream monitor attempts to open a diagnostic issue instead.
4. Optionally protect `main` and require the validation checks and review before merging.
5. Confirm the workflows are enabled in the **Actions** tab; schedules may be delayed by GitHub and operate on the default branch.

## Manual verification

- In **Actions > Validate upstream tracking > Run workflow**, run on `main`.
- In **Actions > Monitor Arcium upstream > Run workflow**, check the log. If upstream has moved, expect a branch named `automation/arcium-core-update` and an open PR.
- On that PR, verify Windows patch compatibility yourself. Merge only once the Windows port has working build and integration checks.
- After any CI failure, inspect the Actions logs. Do not treat a source-validation pass as a build pass.

## Future release pipeline

When a launchable Windows port exists, add Windows Chromium compilation, UI smoke tests, persistence/regression tests, packaging tests, and signed artifacts. Restrict development artifacts to tested commits, and gate beta/stable releases separately. Stable client updates must verify signatures and protect user profiles. Upstream Chromium security fixes should be evaluated independently of feature commits.

## References

- Shared core: https://github.com/dr-baker/Arcium
- macOS reference: https://github.com/dr-baker/Arcium-macOS
- Project: https://github.com/Metoku/Arcium-Windows
