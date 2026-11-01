# Browser-only Windows build experiment

The first Arcium-Windows native compilation should build **only the Chromium `chrome` target**, not the inherited Helium `setup` or `mini_installer` targets.

This project is **not safe to install or distribute yet** because the Windows build inherits Helium-specific application identifiers, profile handling and updater assumptions.

## Implementation

- [`scripts/browser_only_build.py`](../scripts/browser_only_build.py) uses the exact pinned Helium-Windows `0.20.1.1` build script and Arcium core.
- It restores Chromium test files with pinned Git blob verification, replaces the obsolete Windows version writer with Arcium's supported `refresh_version`, and changes the precise upstream release targets to **`chrome` only**.
- It refuses unfamiliar source/build layouts and existing source workspaces, rejects updater/signing environment keys, checks free storage, caps concurrency, and records detailed failure logs.
- It never launches, installs, signs, uploads or distributes the compiled executable. If `chrome.exe` exists after a successful run, the report marks **`BROWSER_BINARY_CREATED_NOT_LAUNCHED`**, not a verified working browser.

## Fast validation

```powershell
python scripts/windows_port.py stage
python scripts/browser_only_build.py --validate
python -m unittest discover -s tests -p test_browser_only_build.py -v
```

These tests **do not** compile Chromium.

## Heavy compile attempt: explicitly opt in

Use the existing [Windows staging and experimental build workflow](../.github/workflows/windows-build-experiment.yml) with `compile_browser = true`. The compilation stage is disabled on PR checks and by default. The environment must have a native Windows C++ toolchain, at least **105 GiB available storage**, and sufficient RAM/CPU for Chromium. The default helper uses only **2 compilation jobs** initially to reduce memory pressure.

The Windows runner preflight previously reported ~16 GiB of RAM, so a full Chromium build may still fail because of resource limits. Prefer a large self-hosted Windows runner for substantial compilation.

**Do not enable automatic releases or make a publicly installable package from this experiment.** First satisfy [unique Windows application identity and profile isolation](https://github.com/Metoku/Arcium-Windows/issues/8), plus actual executable launch and UI persistence tests.

Current verified milestone: complete **521+30 patch application**. GN-generation and native compilation are separate gates.
