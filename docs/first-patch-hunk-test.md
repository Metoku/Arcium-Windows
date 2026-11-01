# Chromium 156 patch hunk compatibility — first passing run

GitHub Actions [run #2](https://github.com/Metoku/Arcium-Windows/actions/runs/41311528260) applied **47 selected patch operations** successfully to the **9 Chromium files** modified by both the pinned Arcium shared patch series and Helium Windows's platform patch series.

## Reproducibility

- Arcium shared core: `4e8f8e2bd3cdcab014ae9663907db93e915cb850`
- Windows platform: `e4b527255e3e0546ac140b7cb52d285fadb2d7d0` (`0.20.1.1`)
- Original Chromium tag: `156.0.8078.47`
- Linux runner: `ubuntu-latest` with GNU `patch` (`-p1 --forward --ignore-whitespace --fuzz=0`)
- Downloaded source provenance: official Chromium Gitiles tag, with SHA-256 recorded in the JSON report

## Tests completed

| Check | Outcome |
|---|---|
| Python unit tests | Passed |
| Source repository staging and pinned revision verification | Passed |
| Download nine unmodified Chromium release files | Passed |
| Extract shared patch hunks affecting overlapping paths | Passed |
| Apply Arcium portions in series order | Passed |
| Apply Windows portions after Arcium | Passed |
| Strict hunk matching (`--fuzz=0`) | Passed |
| Full patch stack / Windows compilation | **Not tested** |
| Browser launch, UI features, installer | **Not tested** |

The report can be found under the workflow's `overlapping-patch-application-report` artifact; the full historical audit and the nine overlapping paths are in [first-windows-audit.md](first-windows-audit.md).

## Caveats

This is *real patch application on a carefully selected subset of source files*, not a substitute for full patch application. Files unique to either patch series have not been applied; test filters ignore non-unified-diff metadata and binary patches. Running GNU patch on Linux also cannot catch C++ Windows link errors or Windows-specific UI runtime bugs. Follow-up work must validate the entire patch stack and produce a launchable Windows executable.

## Next steps

1. Expand coverage to Windows-specific patch targets and exercise the full platform patch sequence.
2. Prepare a sufficiently capable Windows runner and apply **all** Chromium patches with the official build scripts, capturing exact failures.
3. Resolve Windows-specific Arcium source/compilation issues and assign a separate Windows application identity.
4. Build and launch the browser with a disposable profile before distributing binaries.
