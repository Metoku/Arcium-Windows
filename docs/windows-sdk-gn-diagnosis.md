# Windows GN SDK selection: first real GN error

**Failure:** [GitHub Actions run #41322260439](https://github.com/Metoku/Arcium-Windows/actions/runs/41322260439), Windows Server 2025.

The complete Arcium + Helium Windows source patching stage succeeded, version writing was corrected by [PR #13](https://github.com/Metoku/Arcium-Windows/pull/13), and the Windows builder **ran `gn gen` for the first time**.

GN failed during Visual Studio toolchain setup because the default SDK selected by the runner advertised a path that did not exist:

```text
Exception: Path "C:\Program Files (x86)\Windows Kits\10\include\10.0.28000.0\um"
from environment variable "include" does not exist.
```

This establishes an SDK selection/environment error **after reaching GN**, not an Arcium patch conflict and not successful GN configuration.

## Corrective integration

The [Windows SDK compatibility helper](../scripts/windows_sdk_compat.py):

1. Enumerates installed Windows SDK directories under `Windows Kits/10`.
2. Requires `Include/<version>/{um,shared,ucrt}` and `Lib/<version>/{um,ucrt}/x64` to be present before considering a version usable.
3. Selects the highest *complete* version instead of trusting a possibly partial/default SDK.
4. Rewrites exactly two pinned Helium-Windows `vcvars` invocation sites to call Microsoft's documented `vcvarsall.bat amd64 <winsdk_version>` with the selected version.
5. Fails closed if the platform build script changes unexpectedly.

Both GN-only preparation and the browser-only native build adapter use this same selection. It does not download or install SDKs, alter system installations, or modify upstream Arcium/Helium source.

[Microsoft's Visual Studio command-line documentation](https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line) explicitly supports selecting a Windows SDK version using `vcvarsall.bat`. The [preflight script](../scripts/windows_build_preflight.ps1) now reports detected and complete SDK versions, not just whether the Windows Kits directory exists.

## Acceptance

- [ ] Verify on a real GitHub Windows runner that a complete Windows SDK can be selected.
- [ ] Run the full pinned Windows source preparation and GN configuration, and verify `out/Default/build.ninja` is generated.
- [ ] Later: attempt native browser-only C++ compile, isolated-profile launch, UI testing, unique app identity, and installer signing.

The project remains approximately **34% complete** until real GN generation succeeds.
