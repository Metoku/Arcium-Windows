# Hosted Windows runner capacity (2026-11-01)

The read-only [Windows build preflight workflow run](https://github.com/Metoku/Arcium-Windows/actions/runs/41312752547) succeeded on GitHub's `windows-2025` runner. Its [JSON preflight artifact](https://github.com/Metoku/Arcium-Windows/actions/runs/41312752547/artifacts/13085748208) is the source for these observations.

| Attribute | Observed |
|---|---|
| Windows | Microsoft Windows Server 2025 Datacenter, x64 |
| Workspace volume | D:\\, 150.0 GiB total |
| Free workspace disk space | **147.0 GiB** |
| Physical/visible RAM | **15.99 GiB** |
| Visual Studio | Installed (`C:\\Program Files\\Microsoft Visual Studio\\18\\Enterprise`) |
| Windows SDK | Found |
| 7-Zip, Python 3.12, Git | All present |
| Long Windows file paths | Enabled |
| Developer Mode | Enabled |

## Interpretation

The runner looks suitable for **source checkout, full Chromium patch application, and some preliminary compilation experiments**. That is more favorable than an assumed minimal Windows CI machine.

However, the conservative preflight check currently reports **`recommended_for_first_compilation_attempt = false`**, because its strict 16 GiB minimum compares against **15.99 GiB** of visible memory. In practice this is a nominal 16 GiB runner, but large Chromium link steps can exceed memory or the remaining disk budget. The script deliberately records this as uncertain instead of claiming the runner can complete a browser release.

Do not equate a successful read-only preflight with working GN generation, Chromium compilation, running Windows UI, or distributable installer readiness.

## Next actions

1. Add a **source-preparation-only** build-stage mode that downloads the full Chromium `156.0.8078.47` Windows source package and applies all **521 Arcium** patches plus the **30 Helium Windows** patches (not just the selected hunks already tested).
2. Run that only as an opt-in workflow because Chromium downloads are large and may consume paid Actions minutes.
3. Capture the first failing patch or environment issue, and fix it in a separately reviewed change.
4. If patch application succeeds, test GN generation and later C++ compilation on a sufficiently capable Windows runner.
5. Assign a unique Windows application identity and test profile isolation **before** installing or releasing the browser.
