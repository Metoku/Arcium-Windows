# Windows platform patch compatibility: first comprehensive target check

The `Windows` scope of the [Chromium patch-hunk workflow](../.github/workflows/patch-hunk-compatibility.yml) successfully exercised **every file targeted by Helium Windows's 30 patches**, with Arcium patch changes affecting those same files applied first.

## Verified run

- [GitHub Actions run #11](https://github.com/Metoku/Arcium-Windows/actions/runs/41312387379)
- [Detailed JSON artifact](https://github.com/Metoku/Arcium-Windows/actions/runs/41312387379/artifacts/13085747479)
- Chromium **156.0.8078.47**
- Arcium core commit `4e8f8e2bd3cdcab014ae9663907db93e915cb850`
- Helium-Windows platform commit `e4b527255e3e0546ac140b7cb52d285fadb2d7d0`

| Check | Verified outcome |
|---|---:|
| Distinct files targeted by Windows patches | 123 |
| Existing source files obtained from pinned repositories | 104 |
| New files introduced by the patch stack | 19 |
| Relevant Arcium patch operations applied | 39 |
| Helium Windows patch operations applied | 30 |
| Total selected patch operations applied | **69** |
| Patch hunk failures | **0** |

No fuzz was permitted (`--fuzz=0`), and the patch operations were applied sequentially using GNU `patch -p1`. The original nine-file overlapping-scope job also passed in the same run.

## Source provenance

- Chromium source files came from the exact version tag via the [Chromium GitHub mirror](https://github.com/chromium/chromium) or official Gitiles source.
- ANGLE and Dawn were fetched at **their exact commit IDs from Chromium's pinned `DEPS`**: ANGLE `3b89d84e9d59f75675ac4e2bef58fc068a9f0577`, Dawn `1da41e55bb915dd03f61028fad64a99ee1786d48`.
- WinSparkle source was fetched from the Windows platform's pinned release **0.9.3**.
- Every downloaded source file's SHA-256 is recorded in the report.

## What this proves—and what it does not

This validates that the **selected patch sections** targeting Windows-patched files can apply to original source files with the correct accumulated Arcium modifications. It is substantive source compatibility evidence.

It does **not** validate every patch that changes only Arcium-owned files. No GN project generation, C++ compilation, browser launch, UI integration test, binary signing, installer or updater has run. Those gates remain mandatory before a distributable Windows version.

## Next engineering gate

Run a fully provisioned Windows Chromium build with all Arcium and Windows patch files. Ensure the Windows platform uses its pinned `0.20.1.1` baseline, preserve logs from the first patch or compiler failure, and fix any missing Windows-specific integration. The current manual [build experiment workflow](../.github/workflows/windows-build-experiment.yml) is explicitly opt-in because of Chromium's large toolchain/storage requirements.

**Never publish a build under the Arcium name until branding, profile/installer identity, licensing and native Windows smoke tests have been addressed.**
