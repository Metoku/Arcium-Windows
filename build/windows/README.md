# Windows build bootstrap

> **Not yet buildable.** This directory is a placeholder for a real, reproducible Windows Chromium build system. No script here compiles an Arcium browser.

## Intended implementation

1. Verify the exact commit in `../../upstream/arcium-core.sha` against `dr-baker/Arcium`.
2. Audit Arcium's shared Chromium patches for `is_win` compatibility. Keep macOS-only code in the macOS platform repository.
3. Adapt a proven Helium/Chromium **Windows** toolchain, GN arguments, dependency fetching, and patch application process. Pin toolchain and Chromium versions.
4. Implement or adapt native Windows browser UI behavior: sidebar, title bar, spaces, favorites, tab management, Peek, and command bar.
5. Compile on an appropriately provisioned Windows runner with persistent cache (Chromium requires significant storage, RAM, and compute).
6. Add an actual executable launch smoke test and feature regression tests.
7. Only after runtime success, package, sign, and publish builds.

Do not add a workflow that uploads an arbitrary `.exe` and calls it Arcium. A successful source checkout or Python test is **not** a successful Windows browser build.

Consider the upstream [Helium repository](https://github.com/imputnet/helium) and its Windows build distribution as build-system references; confirm licenses, paths, and current versions before adopting them.
