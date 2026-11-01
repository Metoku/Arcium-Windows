# Complete Windows Chromium patch-stage verification

**Passed: 2026-11-01**, on GitHub Actions Windows Server 2025.

- [Verified full-source CI run](https://github.com/Metoku/Arcium-Windows/actions/runs/41319549555)
- [Machine-readable report and diagnostics](https://github.com/Metoku/Arcium-Windows/actions/runs/41319549555/artifacts/13088469352)

| Gate | Verified result |
|---|---|
| Pinned shared core | `dr-baker/Arcium` `4e8f8e2bd3cdcab014ae9663907db93e915cb850` |
| Windows platform | `imputnet/helium-windows` `e4b527255e3e0546ac140b7cb52d285fadb2d7d0` |
| Chromium | `156.0.8078.47` |
| Full Arcium shared patch series | **521 / 521 applied** |
| Complete Windows platform patch series | **30 / 30 applied** |
| Completion marker | `ARCIUM_WINDOWS_FULL_PATCH_APPLICATION_PASSED` |
| Job conclusion | **success** |
| GN generation | Not executed |
| Native Windows compilation | Not executed |
| Browser launch, UI, installer and updater | Not executed |

The Windows build tooling's prepared Chromium archive omitted some WebUI test files targeted by Arcium patches. `scripts/restore_chromium_fixtures.py` restores explicitly pinned originals; `scripts/restore_patch_webui_tests.py` finds other missing original WebUI test files referenced by the pinned Arcium patch series. Restored files are validated against immutable Chromium Git blob SHA values. None of the 521 shared patches or 30 Windows patches was removed to obtain the passing result.

## Interpretation

This is the project's **first verified full-source patch success**, not merely static overlap analysis or a selective hunk check. This milestone earns the source-preparation **14% weight** in the [progress roadmap](progress-roadmap.md), taking the estimated project total from **20% to 34%**.

The next gate is `gn gen` on the full patched Windows source. Successful GN generation will not alone prove the C++ browser can compile, launch, or maintain Windows profiles safely. Do **not** ship the Helium-branded Windows installer or enable automatic updates until unique Arcium product identity, code signing, licensing, install/uninstall and disposable-profile runtime tests are addressed.
