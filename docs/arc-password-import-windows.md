# Import saved Arc passwords on Windows

The optional password integration restores Chromium's local password manager
on Windows and adds **Import saved passwords** to Settings. Import uses
Chromium's existing CSV picker, validation, duplicate-conflict review and
password store. It does not copy Arc's encrypted databases.

Source and policy-handler checks are available in this repository. A complete
Windows browser rebuild and a synthetic-password import/restart test are still
required before calling runtime acceptance complete.

## Add it to the existing build

Finish or stop a running build before applying source changes, and close the
Arcium instance using `out\Default\chrome.exe`. From the repository root:

```powershell
python .\scripts\apply_windows_arc_workflow.py --feature passwords --check
python .\scripts\apply_windows_arc_workflow.py --feature passwords --apply
if ($LASTEXITCODE -ne 0) { throw 'Password integration was not applied.' }
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 5
```

The markers are `ARCIUM_WINDOWS_ARC_PASSWORDS_READY` before application and
`ARCIUM_WINDOWS_ARC_PASSWORDS_APPLIED` afterwards. Existing compilation output
is retained. The password catalog is independent of the workflow-settings and
Arc sidebar catalogs; all application orders are checked during source replay.

To remove this source integration, use `--feature passwords --revert` and
rebuild. This removes the integration and restores the upstream password-manager
restriction. It does not delete already imported credentials from the profile.

## Export from Arc, then import into the matching Arcium profile

1. In Arc, select the source browser profile and use its Password Manager to
   export saved passwords to CSV. Complete any authentication Arc requests.
2. In Arcium, switch to the profile that should receive those passwords. If
   the sidebar importer created separate profiles, open the corresponding
   imported Space first. Password CSV files do not reliably identify their
   source browser profile, so no automatic cross-profile mapping is attempted.
3. Open **Settings → Appearance and behavior → Behavior → Import saved
   passwords**, or navigate to:

   ```text
   chrome://password-manager/settings
   ```

4. Under **Import passwords**, choose **Select file** and select the CSV.
   Review the native result and any duplicate-password conflicts. Existing
   credentials are not silently replaced by custom migration code.
5. Check the imported entries in `chrome://password-manager/passwords`, test
   filling on a site you control, and restart Arcium to verify persistence.
6. Delete the exported CSV after verifying the import. The CSV contains
   readable passwords. Keep it off GitHub, chat attachments and build logs.

Repeat these steps for each Arc profile, choosing the matching Arcium profile
each time. Saved passwords help fill sign-in forms; cookies, existing sessions,
passkeys and extension-vault data are not imported through this flow.

If an export is rejected, use Chromium's displayed error and check the CSV
format. A browser password CSV normally includes `url`, `username` and
`password` columns; optional names and notes follow the native importer's
format. Unsupported or malformed rows are handled by Chromium, not rewritten
by an additional parser in this project.

## Windows behavior and policy

The shared upstream handler unconditionally sets credential saving to false.
This integration stops imposing that artificial value on Windows, allowing
the normal user preference and `PasswordManagerEnabled` policy to apply. A
real policy that disables saving is preserved; a policy permitting saving is
also preserved. The native Password Manager settings control offers to save
and automatic sign-in according to the user's preferences and applicable
policies. Built-in passkey restrictions remain as before.

The destination uses Chromium's configured password store and Windows OSCrypt
support. The integration does not change encryption settings, create a Google
account, configure sync, read source encryption keys or use Arc's elevation
service. CSV parsing and saving happen through Chromium's existing browser
UI. No migration script handles real passwords, and CI uses no credentials.

Windows setup also receives a corrected localized subtitle describing the
built-in password manager and the optional extension choices. Other platforms
retain their existing upstream behavior.

## Validation

- Repository tests compile and run the actual patched policy-handler body in
  a small C++ host under Windows and non-Windows build flags. They verify
  absent, enabled and disabled existing policy values, and the unchanged
  passkey restriction. This checks the handler contract, not the complete
  Chromium policy service or native password store.
- Source replay checks all three optional catalogs in every application order
  with LF, CRLF and mixed source endings, including no-op reapplication,
  byte-exact reversion and retained compilation-output sentinels.
- Settings resource XML is parsed. Native CSV parsing, conflict resolution,
  Windows encryption, password filling and restart persistence still require
  the rebuilt Windows browser. The integration reuses those Chromium features;
  no successful real-password migration is claimed from source replay alone.

Reference: [Chromium's password CSV import instructions](https://support.google.com/chrome/answer/13068232).
