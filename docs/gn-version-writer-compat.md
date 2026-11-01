# First full Windows GN run: version-writer API mismatch

**Diagnostic run:** [GitHub Actions #41320793151](https://github.com/Metoku/Arcium-Windows/actions/runs/41320793151), on Windows Server 2025.

## Observed result

Chromium `156.0.8078.47` was prepared, the **521 Arcium and 30 Windows** patches applied, and the upstream Windows builder reached the version-writing stage after domain/name substitutions and translations.

The job **failed before GN generation** with:

```text
AttributeError: module 'helium_version' has no attribute 'check_existing_version'
```

The pinned Helium-Windows platform (`0.20.1.1`) expects two methods that no longer exist in the pinned Arcium core:

- `helium_version.check_existing_version(path)`
- `helium_version.append_version(file, name, version)`

Arcium provides `helium_version.refresh_version(path, version_parts)` instead. It rewrites generated `HELIUM_*` fields idempotently and preserves Chromium version fields.

## Fix

The Windows-only [version API adapter](../scripts/windows_version_compat.py) recognizes the **exact pinned Windows build-script sequence**, replaces it with `refresh_version`, and rejects any unexpected future builder layout or Arcium module API. GN-only generation uses this adapter before processing downloads, source patches and GN. The upstream repositories are unchanged.

Tests verify the replacement block, idempotence guards, and use of `refresh_version` before the GN/Ninja exit gate. This is source compatibility code, **not a successful Windows GN execution**.

## Next gate

An isolated diagnostic workflow reruns full source preparation and `gn gen`. Treat GN as **unverified** until `out/Default/build.ninja` and the strict marker are produced. Only then can the progress estimate rise from **34%** to **42%**. No native C++ compile, browser execution or installer is implied.
