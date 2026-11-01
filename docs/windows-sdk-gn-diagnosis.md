# Windows GN SDK selection: first real GN error

**Failure:** [GitHub Actions run #41322260439](https://github.com/Metoku/Arcium-Windows/actions/runs/41322260439), Windows Server 2025.

The complete Arcium + Helium Windows source patching stage succeeded, version writing was corrected by [PR #13](https://github.com/Metoku/Arcium-Windows/pull/13), and the Windows builder **ran `gn gen` for the first time**.

GN failed during Visual Studio toolchain setup because the default SDK selected by the runner advertised a path that did not exist:

```text
Exception: Path "C:\Program Files (x86)\Windows Kits\10\include\10.0.28000.0\um"
from environment variable "include" does not exist.
```

This establishes an SDK selection/environment error **after reaching GN**, not an Arcium patch conflict and not successful GN configuration.

The next [full GN experiment #41323654809](https://github.com/Metoku/Arcium-Windows/actions/runs/41323654809) found a **complete SDK 10.0.26100.0** and explicitly selected it in the outer Windows builder, but `gn gen` still attempted SDK `10.0.28000.0`. Inspection of pinned Chromium 156 showed two internal `SDK_VERSION = '10.0.28000.0'` definitions, in `build/toolchain/win/setup_toolchain.py` and `build/vs_toolchain.py`. The GN toolchain setup calls its own `vcvarsall.bat` using the former constant, independently of the outer builder's environment. Selecting only the outer vcvars invocation is therefore insufficient.

## Corrective integration

The [Windows SDK compatibility helper](../scripts/windows_sdk_compat.py):

1. Enumerates installed Windows SDK directories under `Windows Kits/10`.
2. Requires `Include/<version>/{um,shared,ucrt}` and `Lib/<version>/{um,ucrt}/x64` to be present before considering a version usable.
3. Selects the highest *complete* version instead of trusting a possibly partial/default SDK.
4. Rewrites exactly two pinned Helium-Windows `vcvars` invocation sites to call Microsoft's documented `vcvarsall.bat amd64 <winsdk_version>` with the selected version.
5. Fails closed if the platform build script changes unexpectedly.

Both GN-only preparation and the browser-only native build adapter use this same selection. It does not download or install SDKs or alter installed Windows tools.

### Chromium's independently hardcoded SDK version

The [Chromium SDK pin helper](../scripts/chromium_sdk_pin.py) additionally adjusts **exactly two known constants in the disposable extracted Chromium source**, immediately before invoking GN. Both must still match `10.0.28000.0` from the reviewed Chromium 156 baseline; otherwise the helper fails without writing either file. It accepts only a well-formed, locally verified installed SDK version. Unit tests cover both constant rewrites, preservation of CRLF source formatting, and strict rejection of divergent sources.

This changes only the temporary build workspace. It does not patch installed SDKs, modify upstream Arcium/Helium repositories, skip source patches, or alter the production installer. [One-time GN diagnostic PR #18](https://github.com/Metoku/Arcium-Windows/pull/18) validates the fix with a real Windows runner, without Ninja or binaries.

[Microsoft's Visual Studio command-line documentation](https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line) explicitly supports selecting a Windows SDK version using `vcvarsall.bat`. The [preflight script](../scripts/windows_build_preflight.ps1) now reports detected and complete SDK versions, not just whether the Windows Kits directory exists.

## Acceptance

- [x] Verify on a real GitHub Windows runner that a complete Windows SDK can be selected (10.0.26100.0; run #41323654809).
- [ ] Run the full pinned Windows source preparation and GN configuration, and verify `out/Default/build.ninja` is generated.
- [ ] Later: attempt native browser-only C++ compile, isolated-profile launch, UI testing, unique app identity, and installer signing.

The project remains approximately **34% complete** until real GN generation succeeds.
