# Build the reviewed update candidate on your Windows PC

Use this procedure for the reviewed `automation/arcium-core-update` proposal.
It prepares every Windows integration before branding, generates GN once, then
uses the existing local resume command for the native `chrome` target. There
is no five-hour compilation timer. Source preparation and compilation report
their outcomes separately. The candidate is not installed or published.

Use a separate short folder such as `D:\src\Arcium-Candidate`. Reserve
250–300 GiB of free NTFS SSD space for a fresh source/build workspace. Your
working `D:\src\Arcium-Windows` build stays available. The new workspace does
not inherit its compiled objects, so this first candidate build may take hours.
Do not expect the old Ninja step counter to continue in this folder.

The existing Git, Python, 7-Zip, Visual Studio C++/ATL/MFC and complete Windows
SDK `10.0.28000.0` are required. Verify the SDK with the read-only command below.
No unattended SDK installation, runner registration or billing change is part
of this procedure.

## Select an exact checked revision

First fetch the proposal in your existing repository:

```powershell
Set-Location D:\src\Arcium-Windows
git fetch origin automation/arcium-core-update
if ($LASTEXITCODE -ne 0) { throw 'Could not fetch the candidate.' }
git rev-parse FETCH_HEAD
```

Compare the printed SHA with the exact revision whose checks passed on the
proposal. Use that full SHA in place of `CHECKED_CANDIDATE_SHA` below. If the
proposal advanced after validation, use the checked revision or wait for the
new checks rather than assuming an unchecked branch tip is accepted.

```powershell
git worktree add --detach D:\src\Arcium-Candidate CHECKED_CANDIDATE_SHA
if ($LASTEXITCODE -ne 0) { throw 'Could not create the separate candidate checkout.' }
Set-Location D:\src\Arcium-Candidate
```

If that folder already exists, inspect it and its reports instead of deleting
it or rerunning one-time source preparation.

## Prepare once, then compile

Run in the candidate folder. Stop if a command fails:

```powershell
python -m pip install requests Pillow
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
python scripts\windows_port.py stage
if ($LASTEXITCODE -ne 0) { throw 'Candidate source staging failed.' }
.\scripts\provision_chromium_sdk.ps1
if ($LASTEXITCODE -ne 0) { throw 'The required Windows SDK is incomplete.' }
python scripts\gn_smoke.py --validate --release-candidate
if ($LASTEXITCODE -ne 0) { throw 'The candidate preparation adapter is incompatible.' }
python scripts\gn_smoke.py --execute --release-candidate --max-minutes 160
if ($LASTEXITCODE -ne 0) { throw 'Source or GN preparation failed; inspect work\gn-generation.log.' }
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 5
```

The `--release-candidate` option includes Arc settings/import, saved-password
import, appearance, onboarding/profile isolation, extension services and Mac
window buttons. It applies those catalogs before domain/name substitution,
using the same entry as the fresh release builder, then stops after GN creates
`out\Default\build.ninja`. The GN marker enables the existing resume helper.
The helper retains completed output and compiles only `chrome`.

After a successful GN preparation, resume a stopped or failed compilation with
only this command, from the same candidate checkout:

```powershell
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 5
```

If GN itself failed, inspect `work\gn-generation.json` and
`work\gn-generation.log`; do not reapply the source patch stacks over the
partial workspace. The existing Python-alias recovery helper applies only to
the documented Store-alias failure. Avoid deleting `out\Default` to retry a
compiler error.

## Verify launch before accepting the candidate

After compilation succeeds:

```powershell
python scripts\windows_browser_smoke.py --timeout 60
```

That uses a disposable profile and checks headless launch. Separately test
normal browsing, extensions, Spaces, password filling, restart persistence,
the new features and window buttons. Keep the proposal unmerged until native
compilation and interactive acceptance are recorded. Then package the newly
compiled runtime with a new version as described in
[the release procedure](automation.md#publish-an-accepted-candidate).
