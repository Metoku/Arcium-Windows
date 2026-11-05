# Compile Arcium-Windows on your PC, and resume without losing progress

**Goal:** Make a first local **experimental Chromium 156 Windows chrome.exe**, then resume the same compilation later. This is a developer build only: no installer, code signing, auto-updater, application identity/branding assurance, or use of existing Chrome/Helium browser profiles.

The current repository uses:
- Chromium version **156.0.8078.47**
- Pinned Arcium core `4e8f8e2bd3cdcab014ae9663907db93e915cb850`
- Pinned Helium-Windows platform `e4b527255e3e0546ac140b7cb52d285fadb2d7d0`
- 521 Arcium + 30 Windows patches (551 total)
- Windows SDK **10.0.28000.0** for native compilation.

**Do not use the normal upstream `build.py` directly.** Its default targets include `setup` and `mini_installer`. This guide prepares an **Arcium-patched GN source tree**, then uses only the **`chrome`** target.

## 1. Check free disk and Windows prerequisites

Chromium requires an NTFS disk. For this project, plan for **250–300 GiB free** on the same SSD before starting; the official Chromium docs give **100 GB minimum**, but additional space helps for compiler outputs, archives and tools.

Open **Windows PowerShell (not Git Bash)** and check:

```powershell
Get-Volume -DriveLetter C | Select-Object DriveLetter,FileSystem,SizeRemaining
```

A PC with Ryzen 7 5700G and 32 GiB RAM can attempt a local build, but first compilation may take many hours. Reserve free SSD space. If your C: drive doesn't have it, use a different **NTFS SSD** and change `C:\src` in every command consistently. Avoid OneDrive-synced folders and spaces/non-ASCII characters in the repository path.

Install the following programs:

1. [Visual Studio 2026 Community](https://visualstudio.microsoft.com/vs/community/) (or a compatible version confirmed by the pinned Chromium revision). In the installer, select **Desktop development with C++**, **MSVC x64/x86 C++ build tools**, and **C++ ATL/MFC**. The current upstream Chromium Windows guide documents Visual Studio 2026, Desktop C++, ATL/MFC. Do not remove your existing Visual Studio installation just to do this.
2. [Windows SDK downloads (Microsoft)](https://learn.microsoft.com/en-us/windows/apps/windows-sdk/downloads): install the **Windows SDK for Windows 11 (10.0.28000.2957)** (September 2026), which installs the **10.0.28000.0** SDK folder used by this pinned build. Install the native Desktop C++ x64/x86 components and **Debugging Tools for Windows** (Chromium's current Windows instructions require Debugging Tools version 10.0.26100.3323 or later). **Do not run `scripts/provision_chromium_sdk.ps1 -Install` locally:** that unattended helper assumes GitHub runner environment variables; its plain form is read-only verification.
3. [Git for Windows](https://git-scm.com/install/windows). Use the installer option to make Git available from PowerShell.
4. [Python 3.12 for Windows](https://www.python.org/downloads/windows/). Check **Add python.exe to PATH**, and use the installer option **Disable path length limit**. Use an ordinary Python installation, not the Windows Store alias.
5. [7-Zip for Windows](https://www.7-zip.org/). The prepared Chromium archive is compressed; Helium's download/extraction helpers use 7-Zip.
6. In Windows **Settings → System → For developers**, enable **Developer Mode**. Also enable Windows long-path support. Restart PowerShell and, if Windows requests it, reboot once.

Chromium's own [Windows compilation instructions](https://chromium.googlesource.com/chromium/src/+/main/docs/windows_build_instructions.md) explain the Visual Studio tools, SDKs and long path requirements. The SDK version above is a stricter requirement of our **pinned Chromium 156** (verified by previous Arcium CI object compilation), rather than a general version guess.

## 2. Verify the tools (one-time)

Open a fresh **PowerShell** window. Run:

```powershell
git --version
python --version
& "C:\Program Files\7-Zip\7z.exe" i
```

Confirm Git and Python report their versions. If `python` opens Microsoft Store or errors, repair Python PATH/app execution aliases rather than continuing.

For this pinned build, use Microsoft's **Windows SDK 28000**. A later step performs a read-only SDK installation check. If PowerShell refuses to execute the project's local scripts, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` for **that terminal session only**; do not change your computer's machine-wide execution policy.

## 3. Clone Arcium-Windows into a short local directory (one-time)

In **PowerShell**:

```powershell
New-Item -ItemType Directory -Path C:\src -Force | Out-Null
cd C:\src
git clone https://github.com/Metoku/Arcium-Windows.git
cd C:\src\Arcium-Windows
git checkout main
python -m pip install requests Pillow
```

Do not separately clone `chromium/chromium`, `imputnet/chromium-tarballs`, or `helium-windows` into the build folder. Our staging and preparation scripts fetch the **exact pinned versions** and the matching Chromium tarball for you.

## 4. Stage exact Arcium and Helium-Windows source (one-time)

Run from `C:\src\Arcium-Windows`:

```powershell
python scripts\windows_port.py stage
```

This checks out the pinned Windows build scripts into `work\windows-platform` and the pinned Arcium core into its `helium-chromium` directory. It **does not download Chromium yet** or compile anything.

If successful, proceed to the SDK check:

```powershell
.\scripts\provision_chromium_sdk.ps1
```

**No `-Install` flag.** This only verifies that SDK `10.0.28000.0` has complete Include and Lib directories. If it fails, return to the official Microsoft SDK installer above.

If `stage` says the destination directory already exists, **do not delete it**. It is deliberately protected against replacing an existing staged build. Continue with `python scripts\windows_port.py audit` or inspect the existing directory.

## 5. Download the matched Chromium source, apply all patches, and generate GN (once)

This command is *different* from actually compiling Chrome:

```powershell
python scripts\gn_smoke.py --execute --max-minutes 160
```

This runs the project's verified preparation adapter. It downloads the pinned Windows x64 Chromium archive and the required other dependencies, verifies archive hashes, restores missing patch fixtures, applies Arcium + Windows patch sets, then runs GN to create the `out\Default\build.ninja` graph. It **never invokes the Ninja compiler**.

The Chromium archive is defined in the pinned Helium-Windows file `downloads.x64.ini`:

```text
https://tarballs.imput.net/chromium-156.0.8078.47/chromium-156.0.8078.47-win-x64.tar.zst
```

Its hash manifest is referenced through [imputnet/chromium-tarballs](https://github.com/imputnet/chromium-tarballs). **Do not download an unrelated Chromium release or bypass hash checking.**

Expect a large download and a lengthy extraction. The source will live at:

```text
C:\src\Arcium-Windows\work\windows-platform\build\src
```

Once you have a successful GN preparation, **never rerun `gn_smoke.py --execute` on that same source tree**. Its one-time preparation script refuses this to avoid reapplying the same 551 patches.

If it times out **before completing** this one-time preparation, do not assume it left a usable source tree. Share `work\gn-generation.log` and `work\gn-generation.json` for diagnosis; incomplete patch application requires careful recovery.

## Recovery if GN fails because Windows launches Microsoft Store Python

If source preparation reached GN but displays:

- `Python was not found; run without arguments to install from the Microsoft Store`
- `WindowsApps/python3.exe`
- `ERROR at //build/toolchain/concurrent_links.gni`

**Do not delete `work/windows-platform/build/src`, re-clone, or rerun `gn_smoke.py --execute`**. Your source and patches were already prepared; the initial adapter won't allow a second full preparation over this tree.

1. In Windows **Settings**, search for **Manage app execution aliases**. Disable the **App Installer** aliases for both `python.exe` and `python3.exe` so Windows doesn't intercept Chromium's Python calls. Close and reopen PowerShell.
2. From the cloned project directory, verify that the Python command resolves to your installed Python and is not in `WindowsApps`:

```powershell
cd D:\src\Arcium-Windows
python -c "import sys; print(sys.executable)"
where.exe python
where.exe python3
```

   A missing `python3` can be handled by the recovery helper below, which passes the real `sys.executable` to GN using `--script-executable`. **Do not copy or rename the WindowsApps aliases.**
3. First validate the previously failed GN state, preserving the current tree:

```powershell
python scripts\recover_gn_python_alias.py
```

4. If it prints `GN recovery prerequisites passed`, run **only** the failed GN generation step:

```powershell
python scripts\recover_gn_python_alias.py --execute
```

The helper requires the original failed `work/gn-generation.json` and `work/gn-generation.log`, validates the pinned builder and source state, selects verified Windows SDK 28000, invokes GN in an actual Visual Studio C++ environment with the working Python executable, and marks success **only** if `gn.exe gen` returns successfully and `out/Default/build.ninja` is created. It does not re-download source, reapply patches, or run a compilation.

If recovery succeeds, continue at **Step 6** below. If another GN error appears, inspect `work/gn-recovery.log` and fix that specific issue before retrying. This special recovery method is **only for this confirmed Python Store-alias failure**, not arbitrary incomplete patching.

## 6. Start the *incremental* compilation (and resume later)

The repository provides this local resume helper:

```powershell
.\scripts\local_windows_resume.ps1 -Mode check
```

This confirms pinned platform/core revisions, the GN marker, Visual Studio tools, SDK 28000 and required Ninja files without starting compilation.

If that reports `ARCIUM_LOCAL_RESUME_PREREQUISITES_PASSED`, start compiling **only** the native `chrome` target:

```powershell
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 5
```

For an eight-core Ryzen 7 5700G with 32 GiB RAM, **5 parallel jobs** is a conservative starting point. If you run out of memory or the PC becomes unusably slow, retry with `-Jobs 3`. Do not set `-Jobs 12` blindly.

**Resuming later is the exact same command**:

```powershell
cd C:\src\Arcium-Windows
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 5
```

Ninja/Siso uses previously built outputs in `work\windows-platform\build\src\out\Default` and recompiles only what is required. Stopping with Ctrl+C is generally safe, though any interrupted object may need to be rebuilt. You may shut down the PC after the compiler fully exits. Keep the build tree intact.

To collect independent compiler failures in one incremental build, add the
optional `-KeepGoing` switch:

```powershell
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 8 -KeepGoing
```

This passes Siso's documented `-k=0` flag. It continues tasks whose prerequisites
are available, records their errors in `out\Default\siso_output`, and returns a
failure if any task fails. Tasks blocked by a failed dependency cannot run. It
can take longer after an error, but completed outputs are reusable. Omitting the
switch keeps the existing stop-on-failure behavior. See the
[Chromium Siso guidance](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/docs/siso_tips.md#run-steps-as-much-as-possible).

Do not run `git clean -xfd` in the staged Chromium tree, delete `out\Default`, or re-run patch preparation to resume.

### V8 metagen fails because `gn desc` uses the Windows Store Python alias

If the compile gets past the protobuf plugin but fails `//v8:metagen_instance_types_h` with `gn desc` and `Python was not found`, it is **still Python resolution**, not a V8 C++ compiler failure. The earlier temporary `python3.cmd` works for Windows command scripts but is **not recognized by GN's Windows interpreter search**, which explicitly checks `python3.exe` and `python3.bat`.

Update and retry the incremental helper:

```powershell
cd D:\src\Arcium-Windows
git pull --ff-only origin main
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 5
```

The updated helper creates a disposable `python3.bat` wrapper pointing to the same installed Python executable. It now **checks `gn.exe desc` for the V8 target before launching Siso**. Look for `ARCIUM_LOCAL_GN_DESC_PASSED`; if it doesn't appear, share that preflight error and **do not** regenerate Chromium or delete build output. On success, the helper launches the same incremental `chrome` target and reuses prior build results.

### Missing compiled chrome.exe immediately after the Python 3 version preflight

If the local resume script prints the temporary `python3.cmd` path and `Python 3.14.x`, but **never prints `siso ninja`** and instead reports a missing `chrome.exe`, the original preflight launched the temporary batch file without CMD's required `call` keyword. The build was not started; the completed output was not deleted.

Update the helper and retry:

```powershell
cd D:\src\Arcium-Windows
git pull --ff-only origin main
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 5
```

The corrected preflight uses `call python3 --version`, so control returns to the parent batch and proceeds to Siso. Do not rerun source preparation or GN.

### Python 3 command missing during an otherwise successful local build

If Siso reports `protoc-gen-ts_proto: Plugin failed with status code 9009` and mentions the Microsoft Store, GN already succeeded; **do not rerun GN or source preparation**. The generated Chromium batch file `tools/protoc_wrapper/protoc-gen-ts_proto.bat` invokes `python3`, whereas the build's other scripts invoke your installed `python.exe` directly.

The local resume helper now creates a project-local, temporary `python3.cmd` that forwards to the same installed Python interpreter. It prepends that directory to the build session's PATH, verifies `python3 --version`, and removes the temporary shim on normal completion or failure. It does not alter system PATH or the compiled Chromium source. To use the fix:

```powershell
cd D:\src\Arcium-Windows
git pull --ff-only origin main
.\scripts\local_windows_resume.ps1 -Mode resume -Jobs 5
```

Existing `out\Default` objects should remain reusable. If another step fails, preserve the build tree and share its first full `FAILED:` block.

## 7. Verify locally if chrome.exe finishes

Only after the compilation prints `ARCIUM_LOCAL_CHROME_COMPILED` and the `chrome.exe` exists:

```powershell
python -m scripts.windows_browser_smoke --timeout 60
```

This launches the new executable **headlessly with a disposable profile**, opens `about:blank`, then deletes the temporary profile. This **does not** install the browser, validate its full Arc-like Windows UI, or make it safe for regular browsing/distribution.

Run this from the repository root. Success prints `HEADLESS_LAUNCH_PASSED` and
the report path (`work\browser-launch-smoke.json` by default). The direct-file
invocation `python scripts\windows_browser_smoke.py --timeout 60` is also
supported; the script resolves its own root without importing the `scripts`
package. Updating this Python helper does not require a browser rebuild.

## If something fails

| Symptom | Action |
| --- | --- |
| `Python` is not found | Fix Python PATH and Windows App Execution Aliases; restart terminal |
| `protoc-gen-ts_proto.bat` fails with `Python was not found` / exit 9009 | Chromium 156's TypeScript protobuf plugin calls `python3`, while Python.org may install only `python.exe`. Update the checked-out Arcium-Windows helper via `git pull --ff-only origin main` and rerun `local_windows_resume.ps1 -Mode resume -Jobs 5`. It adds a temporary `python3.cmd` on PATH using the current installed Python, without modifying Chromium or deleting completed outputs. The next console log should show the local shim as the first `where python3` result and print its Python version. |
| `7-Zip` unavailable | Install 7-Zip normally and confirm `C:\Program Files\7-Zip\7z.exe` works |
| SDK check says 28000 missing | Install the matching SDK from Microsoft's **Windows SDK downloads** page. Don't spoof SDK/version headers |
| Source download fails | Inspect `work\gn-generation.log`; its download cache uses resume-capable curl when present. Don't manually mix mismatched tarballs |
| GN preparation times out | Inspect the GN log before deciding what to retain; an incomplete source is not safe for the resume command |
| Compiler reports C++ error | Save the first `FAILED:` block and related compiler diagnostics; previous valid output stays on disk |
| No `chrome.exe` yet | Normal until all compilation/linking steps complete; continue the resume command |
| Windows path length errors | Ensure long paths are enabled and repository lives under `C:\src` rather than a deep user or OneDrive directory |

**No browser binary has been built yet.** The previous GitHub Actions attempt timed out at about 22,400/81,338 reported compilation steps. The initial local compile starts cold, but the resulting build directory is kept for subsequent sessions.
