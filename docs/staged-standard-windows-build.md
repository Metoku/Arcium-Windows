# Arcium-Windows staged compilation on GitHub's STANDARD Windows runner

This is for **Metoku/Arcium-Windows**, with no GitHub larger runner and no local Windows build machine. It reuses **eligible compiler outputs through sccache** over GitHub Actions' cache service. It does **not** recover the previous 22,400 compiled steps from failed [run #41356619052](https://github.com/Metoku/Arcium-Windows/actions/runs/41356619052): that run uploaded only logs and its temporary VM was discarded.

## What will happen

1. The **first** run of `native-windows-chrome-staged.yml` starts **once** when the workflow is merged into `main` (push event on this exact workflow file), using the standard `windows-2025` runner.
2. It verifies tests, installs `sccache`, configures GitHub's cache backend, provisions the signed Microsoft SDK **10.0.28000.0**, applies all **551** reviewed patches, and runs GN.
3. It compiles **only** the `chrome` target with `-j 3`. The **first** stage runs for approximately **120 minutes of source preparation + compilation** (builder timer), plus setup time. It then stops Siso and Clang safely.
4. The adapter records `status: TIMEOUT` and the latest reported Siso progress. The workflow treats *only the deliberate exit code 124* as an **expected cache-warming stage**, prints a visible `ARCIUM_STANDARD_WINDOWS_CACHE_STAGE_ENDED` marker, then reports `sccache --show-stats`. Green status here means the stage ended in its planned time budget, **not** that `chrome.exe` exists.
5. Eligible compiler results are written to the shared GitHub Actions cache during compilation. The original extracted Chromium source and Ninja `out/Default` files are **not** saved. On the next run, the runner re-prepares source/GN and attempts to reuse cached compiler results. Cache hits depend on identical source, compiler, flags, correct backend configuration and remaining cache quota. This is **compiler-result reuse, not an exact continuation of Ninja's previous step number**.
6. If a full browser build unexpectedly completes within a stage, the workflow verifies `chrome.exe` is present, runs the existing disposable-profile headless smoke, and uploads logs only.

## To run the SECOND and later stages

1. Open [GitHub → Metoku/Arcium-Windows → Actions](https://github.com/Metoku/Arcium-Windows/actions).
2. Select **Windows native chrome staged compilation (standard runner, cached)** from the left workflow list.
3. Click **Run workflow** on the right. Make sure the branch dropdown is **main** (important for reusing the same cache).
4. Pick `compile_minutes`: **120** is recommended initially; **60, 180 or 240** are alternatives. Longer stages may build more objects but still end at their time limit.
5. Click **Run workflow**, open its run, then open **Cache verified Chromium compilation (standard Windows, no installer)**.
6. Under **Print compiler-cache hits, misses and errors**, inspect `Cache hits` and `Cache misses`. If the *second* stage has no meaningful hits or reports GitHub cache capacity problems, **do not repeatedly rerun it**; caching is not yet effective.
7. Under **Artifacts**, download `arcium-standard-windows-cache-stage-<run-number>`. Read `browser-only-build.json`. **TIMEOUT is an expected partial stage; BROWSER_BINARY_CREATED_NOT_LAUNCHED means the binary was built.** Only a subsequent successful headless smoke confirms a basic launch.

## Limits and cost notes

- **Previous runner outputs cannot be recovered**; the first staged cache run is cold.
- GitHub's standard Windows runner is still a small machine; the stage simply avoids losing *cacheable* compile work. A full build may take many such runs and might **never converge** if cache entries are evicted faster than the build benefits from them.
- The standard GitHub Actions cache storage limit is **10 GB per repository** with eviction as required. Increasing it beyond 10 GB can incur charges. We have **not** changed billing or cache capacity. See [GitHub Actions cache limits](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).
- The cache backend can be rate-limited; `sccache` may continue compiling without storing some outputs. Treat actual hit/miss metrics as the acceptance test rather than assuming every object persists.
- This workflow creates caches from **push/main** and **workflow_dispatch/main**, because GitHub isolates caches built in pull-request merge refs and they cannot be read from main. See [GitHub cache scope rules](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).
- Never run the large-runner-only workflow for this task: `native-windows-chrome-cached.yml` still rejects the standard 4-core Windows runner.
- The workflow never creates an installer, signs a browser, runs auto-update, reuses personal Chrome profiles, or uploads browser binaries.

## What success looks like

A successful **cache stage** shows `ARCIUM_STANDARD_WINDOWS_CACHE_STAGE_ENDED`, `status: TIMEOUT` and actual `sccache` statistics. A successful **browser compilation** shows `ARCIUM_STANDARD_WINDOWS_FULL_CHROME_BUILD_PASSED`, and the binary is checked locally. A successful **smoke test** separately confirms the browser can start with a disposable profile. **None of these successes have been demonstrated by this new staged workflow yet.**

The project's previously verified milestone score remains **42%** until the full native browser build and launch are proven.
