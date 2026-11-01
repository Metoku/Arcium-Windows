# Windows build bootstrap — experimental

## Why these exact versions?

The pinned [Arcium shared core](../upstream/arcium-core.sha) uses Chromium **156.0.8078.47**. Current [Helium](https://github.com/imputnet/helium) has moved forward, so this first build experiment instead pins [Helium-Windows 0.20.1.1](https://github.com/imputnet/helium-windows/releases/tag/0.20.1.1), whose source and build patches were maintained for Chromium 156.0.8078.47. The exact Windows platform commit is tracked in [upstream/helium-windows.sha](../upstream/helium-windows.sha).

Matching Chromium versions reduces risk; it **does not imply** Arcium and Helium Windows patches apply cleanly to one another.

## What we implemented

The [Windows source-preparation script](../scripts/windows_port.py):

1. Clones the pinned Helium-Windows *platform* revision without initializing its standard Helium submodule.
2. Checks out the exact **Arcium shared core** revision in the build system's expected `helium-chromium` directory.
3. Verifies both commit SHAs and the pinned Chromium version.
4. Checks all referenced platform and shared patch files exist.
5. Produces a static JSON report with shared/Windows patch counts, intersecting target paths, and possible macOS-specific code hints. **Overlap is diagnostic, not a proven conflict.**

There is **no build**, no real patch application, no executable, no signing, and no release in the staging step.

## Run a source audit locally

Prerequisites: Windows 11 (or equivalent Windows build host), Git, Python 3.12+, and sufficient disk space for source checkouts.

From the repository root:

```powershell
python -m unittest discover -s tests -v
python scripts/windows_port.py plan
python scripts/windows_port.py stage
```

The staging directory is `work/windows-platform/`, and the report appears at `work/windows-audit.json`. The script refuses to overwrite an existing checkout. For a clean restart, rename or remove the prior `work/windows-platform` directory *after preserving anything you need*.

The output is **not** a browser, and you should not install or distribute anything from the staging phase.

## Optional, heavy Windows compilation experiment

A manual workflow is defined at [Actions → Windows source staging and experimental build](../.github/workflows/windows-build-experiment.yml).

1. Select **Run workflow** and choose the feature branch while testing, or `main` after the PR is merged.
2. For a source audit, leave `compile_browser = false` (default).
3. For an actual compile attempt, set `compile_browser = true` and choose a Windows runner with at least **100 GiB free space**. GitHub-hosted Windows runners may not satisfy this; a large Windows self-hosted runner with persistent caches is preferable.
4. The workflow stages the pinned source, records a JSON report, and, if compilation was explicitly requested and sufficient storage is detected, invokes the upstream Helium-Windows `build.py --tarball -j 4` with Arcium substituted for its regular core.

**There is no automatic binary upload, installer creation, publication, or browser updater.** Even if the upstream Windows script completes, its binary may still be Helium-branded and may conflict with an existing Helium installation. Do **not** install, publish, or distribute it without Windows-specific brand/installer identity work and runtime validation.

For a local compilation outside Actions, follow the [Helium Windows Windows SDK, Visual Studio, 7-Zip, Python, long paths and build prerequisites](https://github.com/imputnet/helium-windows/blob/main/README.md). In the staged platform directory (using a Visual Studio Developer Command Prompt):

```powershell
python -m pip install requests Pillow
python build.py --tarball -j 4
```

This is an **experimental attempt**; patch failures, missing build dependencies, GN errors, resource mismatches and platform assumptions must be fixed before the first successful build.

## What comes next

- Review the audit findings: overlapping patch targets and macOS-only code.
- Run the actual patch application stage and record the first reproducible errors.
- Refactor affected patches for Windows and add Windows UI integration, starting with launch, sidebar, Spaces, Pins, Favorites and the command bar.
- Develop isolated-profile launch and browser regression tests.
- Assign distinct installer identity, filenames, branding, code signing, and a secure updater before any public release.

Track progress in [the first working Windows build issue](https://github.com/Metoku/Arcium-Windows/issues/1).
