# Faster native Windows Chromium builds

## Why run #41356619052 timed out

The archived GitHub Actions [run #41356619052](https://github.com/Metoku/Arcium-Windows/actions/runs/41356619052) stopped because its **310-minute compilation timeout** expired, **not** because of a C++ compiler error. The archived Siso log ended around **22,400/81,338 reported steps** (about 27.5%). The runner still had **121.6 GiB free**, so disk exhaustion was not the cause. It was a cold, full Chromium 156 browser build with only **three parallel jobs** and about 16 GiB RAM. No `chrome.exe` was produced and the isolated launch did not run.

An unattended repeat on the same small runner with the same configuration is not a useful next experiment.

## What changed

- `scripts/browser_only_build.py` now supports **1–32 parallel compiler jobs** (rather than 1–4), exposes approximate completed/total Ninja/Siso steps in its periodic heartbeat, saves the last reported progress on timeout, and offers `--require-cache` to abort if `sccache` is missing. This does **not** bypass Windows SDK requirements or install anything.
- The pinned Helium-Windows builder already writes `cc_wrapper = "sccache"` to `args.gn` **when** the executable is on PATH and no remote-execution address is configured. The new workflow installs that tool before GN, enabling C/C++ compilation caching. `chrome_pgo_phase=0` is already set in the reviewed core GN flags.
- The **manually invoked** [cached build workflow](../.github/workflows/native-windows-chrome-cached.yml) uses Mozilla's sccache action and GitHub Actions cache as a persistence backend, includes cache hit/miss statistics, and calculates a memory-aware parallel-job count.
- It refuses to run on Windows machines with fewer than **16 logical CPUs, 56 GiB RAM, or 145 GiB free SSD** before downloading any Chromium source. This gate prevents repeating the expensive timeout on the default hosted `windows-2025` runner.
- The workflow retains full patch application (521 Arcium + 30 Windows), the exact reviewed Chromium 156 SDK **10.0.28000.0**, only the native `chrome` build target, bounded runtime, and isolated headless smoke. It never invokes an installer, updater, signing, distribution, or browser-binary upload.

## How to enable the faster run

1. Provision an eligible **Windows x64 GitHub larger runner**, preferably the 16-vCPU / 64-GiB / 600-GB specification or stronger, or a suitably secured self-hosted runner. Verify whether your GitHub account/organization has access and review billed runtime. Merely selecting `windows-2025` will fail the resource gate, intentionally.
2. Obtain the exact runner **label** from GitHub's runner settings. Under the repository **Settings → Secrets and variables → Actions → Variables**, create `ARCIUM_NATIVE_WINDOWS_RUNNER` with that label. A self-hosted runner must use an appropriate unique label, not the generic `self-hosted` alone.
3. Once this workflow is merged into the default branch, open **Actions → Native Windows Chrome-only build (cached, high-capacity) → Run workflow**. It will **not** run automatically on PRs or commits, avoiding surprise paid build hours.
4. Inspect `sccache --show-stats` at the end, `browser-only-build.json`, and the first actual compiler error if any. Only a successful complete build plus passing separate headless smoke can establish a working prototype. A full UI/identity audit will still be needed.

## Limits and alternatives

- The **first** cache-enabled build is still a *cold* build and is likely to take hours, albeit with more cores. `sccache` mainly helps later repeated compilations if the compiler, GN flags, environment, and source inputs still match.
- GitHub Actions' hosted cache has quota and eviction behavior. Cache hits are **not guaranteed**, and it cannot fully preserve the multi-gigabyte object tree. Repeated fresh runners still download and patch Chromium and run GN; the cache only reuses eligible compiler outputs.
- A dedicated, well-provisioned **self-hosted Windows builder with a persistent, trusted source+output tree** can preserve the full incremental Ninja state across runs. The current browser-only adapter intentionally refuses a preexisting source tree to avoid applying all patches twice. True self-hosted incremental/resume support requires a separate validated manifest and clean/reuse guard; **it is not implemented by this workflow**.
- Do not increase `-j` blindly on the small 16-GiB runner: swapping or memory exhaustion may make builds slower.
- Do not bypass Chromium's Windows SDK 28000 checks. The pinned source explicitly requires that SDK for native compilation.
- Never use a self-hosted runner for untrusted PR code or expose personal Chrome/Helium browser profiles to it.

This is build tooling only. It does **not** mean that native browser compilation or launch is already successful.
