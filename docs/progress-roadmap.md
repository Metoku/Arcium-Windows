# Windows port progress and acceptance criteria

**Assessment date:** 2026-11-01

**Estimated completion:** **20% toward a usable, distributable Windows browser**, based on weighted engineering milestones. This is a planning estimate, not measured code completion. The most expensive and uncertain work remains. Reassess once a real Windows executable has compiled and launched.

## Progress breakdown

| Milestone | Weight | Verified? | Evidence / next acceptance gate |
|---|---:|---|---|
| Independent platform architecture and upstream tracking | 8% | **Complete** | Repository, pinned Arcium core, sync and validation workflows |
| Pinned Helium-Windows platform, version matching and source checkout | 6% | **Complete** | [First source audit](first-windows-audit.md) and passing Windows staging CI |
| Real patch-hunk compatibility tests | 6% | **Complete for targeted files** | [123 Windows patch targets and 69 applied operations](windows-platform-patch-results.md); not all shared patches |
| Complete Chromium source preparation and both full patch series | 14% | **Unverified** | [Full-source preparation workflow](../.github/workflows/full-chromium-patches.yml) must succeed |
| Windows GN generation and compile configuration | 8% | **Not attempted** | Reproducible successful Windows GN generation |
| Produce a launchable browser executable | 22% | **Not attempted** | Complete native Windows Chromium build with Arcium patches and isolated-profile smoke launch |
| Implement and adapt Arc-style Windows UI | 18% | **Not attempted** | Spaces, Pins, Favorites, command bar, Peek, split view and Windows title bar functional |
| Real browser runtime and regression testing | 10% | **Not attempted** | Automated Windows integration tests with isolated profiles and feature persistence |
| Installer, identity, distribution, signed updater and release gates | 8% | **Not attempted** | Distinct app IDs, safe installation/uninstallation, signed builds, update validation, licensing review |

**Total:** 100%. Completed baseline milestones: 8 + 6 + 6 = **20%**. Approximately **80% remains**.

The nine milestones are **not equally difficult**, and this estimate can change significantly as Chromium compiler errors reveal additional platform work. A green source test cannot substitute for a working browser.

## Current next gate: full Chromium patch application

Our exact baseline:

- [dr-baker/Arcium](https://github.com/dr-baker/Arcium) at `4e8f8e2bd3cdcab014ae9663907db93e915cb850`
- [imputnet/helium-windows](https://github.com/imputnet/helium-windows) at `e4b527255e3e0546ac140b7cb52d285fadb2d7d0` (0.20.1.1)
- Chromium 156.0.8078.47

The [full source adapter](../scripts/prepare_full_chromium.py) creates an ephemeral source-preparation script from the reviewed upstream Windows build script. It preserves download, integrity checks, source extraction, pruning and **both complete patch applications**, but stops **before GN generation and C++ compilation**. This is intentional: patch errors must be handled before incurring a large compiler run.

### Run only on an appropriately provisioned Windows builder

```powershell
python scripts/windows_port.py stage
python scripts/prepare_full_chromium.py --validate
python scripts/prepare_full_chromium.py --execute --max-minutes 55
```

The execution downloads large source archives and requires at least 95 GiB free. It is bounded by a timeout, writes a machine-readable `work/full-source-prepare.json` report and a separate detailed log, and **never publishes binaries**. A successful patch-stage marker proves both patch application calls returned successfully; it does not imply the browser builds or runs.

The GitHub Actions preparation workflow is limited to the full-source patch stage; a separate build workflow exists for opt-in native compilation. **Do not run both simultaneously on the same runner/workspace.**

## Why no automatic releases yet?

The Chromium installer and auto-update infrastructure inherited from Helium currently uses Helium-specific identifiers, which must not be copied into an Arcium distribution. The first usable Windows preview needs unique installer identity, stable profile storage, proper vendor/title-bar branding, license verification, signing policy and real Windows smoke tests before users can safely install it.

For progress discussions, link to [Issue #1](https://github.com/Metoku/Arcium-Windows/issues/1) and revise this table only with verified CI or Windows runtime results.
