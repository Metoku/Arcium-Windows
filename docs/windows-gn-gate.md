# Windows GN configuration gate

**Status:** Implemented as a separate experimental gate. The adapter can be validated without downloading Chromium; a complete GN test must be explicitly started through GitHub Actions.

## Purpose

Chromium build troubleshooting should have distinct gates:

1. **Shared/platform source checkout and pinned version verification** — already passed.
2. **Selective patch-hunk checks** — 123 Windows-targeted paths and 69 selected patch operations passed.
3. **Full pinned Chromium extraction and complete patch stack application** — independent full-source PR #7.
4. **GN configuration generation** — this experiment.
5. **Native Ninja compilation and executable launch** — future milestones.

GN generation is useful because it can uncover platform GN target/source-list issues **before** native compilation, but is not a test of browser runtime behavior.

## Implementation

The [GN-only adapter](../scripts/gn_smoke.py) reads the exact pinned upstream Helium-Windows `build.py` from our Windows platform checkout. It checks for the known GN/Ninja transition and inserts an unconditional exit **after a successful GN generation and before Ninja**.

It preserves the upstream builder's full download, checksum verification, source extraction, Arcium and Windows patch application, resource substitution and GN flags. It intentionally does not run Ninja, sign, package, install, launch or distribute anything. A machine-readable JSON report, bounded runtime and diagnostic log are provided.

### Cheap validation on a PR

```powershell
python scripts/windows_port.py stage
python scripts/gn_smoke.py --validate
```

This does not download Chromium or run GN. The workflow also runs offline unit tests to prove the stop-before-Ninja logic.

### Full source and GN experiment (opt-in)

In [GitHub Actions → Windows GN generation (experimental)](https://github.com/Metoku/Arcium-Windows/actions/workflows/gn-generation.yml), choose **Run workflow** with `attempt_full_gn = true` to explicitly permit the full source download and GN generation. This consumes substantial Actions resources and may fail; don't trigger it repeatedly without examining the last report.

To run locally on a properly provisioned Windows builder:

```powershell
python scripts/windows_port.py stage
python -m pip install requests Pillow
python scripts/gn_smoke.py --execute --max-minutes 75
```

The command needs at least **95 GiB** free disk before download. The GitHub-hosted runner has around 147 GiB free at its initial state, but this alone is no guarantee of success.

## What qualifies as success

- Complete pinned Arcium and Windows patches have applied without error in that run.
- GN creates `build/src/out/Default/build.ninja` in the Windows source tree.
- The temporary builder emits a verified GN-only marker and exits before Ninja.
- The report's `gn_generation_verified` field is true.

**Do not count GN generation as finished until a full execution report verifies it.** Passing the cheap validation tests proves only that the stop-after-GN adapter matches the upstream build script.

The next stage after a successful GN run will be a suitably provisioned native Chromium compilation and a disposable-profile Windows browser smoke test. Packaging and automatic updates must remain disabled until Arcium has its own application identity, profile directory, installer and signing chain.
