# Installing extensions after first-run setup

The download error **Extension downloads are disabled** means the optional
extension download proxy is blocked by the browser services preferences.
It requires service consent, **Allow connecting to browser services**, and
**Proxy extension downloads and updates**. No custom service URL is required.

Earlier builds sent **Complete setup** back to the welcome page. If setup was
already complete, that page correctly stayed on Done, leaving no way to review
service consent. The optional `services` catalog fixes that recovery path.
It does not enable services automatically.

## Apply to an existing prepared build

Close Arcium, then run this in PowerShell. Stop on any error; keep the existing
Chromium source, `out\Default` directory and profile.

```powershell
cd D:\src\Arcium-Windows
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw 'Repository update failed.' }
python -m scripts.apply_windows_arc_workflow --feature services --check
if ($LASTEXITCODE -ne 0) { throw 'Services recovery does not match this tree.' }
python -m scripts.apply_windows_arc_workflow --feature services --apply
if ($LASTEXITCODE -ne 0) { throw 'Services recovery was not applied.' }
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 8
```

The application marker is `ARCIUM_WINDOWS_SERVICES_APPLIED`. These are WebUI,
frontend and build-input changes; no native C++ source is changed by this
catalog. Resume performs an incremental build. New browser-only builds and
`--feature all` include the catalog.

Launch the rebuilt `work\windows-platform\build\src\out\Default\chrome.exe`.
An installed copy still runs its earlier resources until it is repackaged and
updated with the existing installer process.

## Enable extension downloads

1. Open `helium://settings/privacy/services` and click **Review services**.
   You can also open `helium://setup/?services=1` directly.
2. Enable **Allow connecting to browser services** and **Proxy extension
   downloads and updates**. Other service choices remain yours.
3. Press **Next** to save consent and return to services settings. Check the
   two switches there. **Back** leaves the review without granting consent.
4. Reload the Chrome Web Store page and retry the extension installation.

The review works independently of first-run completion. It does not restart
Arc/browser imports or alter setup completion, default-browser or search-engine
preferences. The existing upstream extension proxy and verification remain in
use. Disabling the master service or extension-proxy switch blocks downloads
again. A different error after enabling these settings needs its own diagnosis.

## Validation

The pinned Chromium/core/Windows replay checks the Settings entry and strings,
both catalog orders, LF/CRLF/mixed/missing-final-newline input, repeat application
and exact reversion. It retains build output and an existing-profile sentinel.
The real onboarding frontend runs Svelte/TypeScript checks, interaction tests,
production bundling and resource generation. Regression tests cover completed
profiles, import-route precedence, no consent on entry/Back, unavailable
preferences, pending or rejected writes, retries and repeat clicks.

These checks do not compile Chromium or prove Windows runtime installation.
After rebuilding, confirm that the review returns to settings, the switches
remain enabled after restart, and a Chrome Web Store extension installs and
opens. Keep that runtime result separate from source validation.
