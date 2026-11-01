#!/usr/bin/env python3
"""Pin Chromium's own Windows SDK constants to a verified installed SDK.

Chromium 156's build/toolchain/win/setup_toolchain.py invokes vcvarsall.bat
with its own SDK_VERSION constant, independently of the Windows builder's
outer vcvars invocation. Likewise build/vs_toolchain.py retains a matching
SDK_VERSION. A runner can contain an incomplete preview SDK: modify both
constants in disposable extracted source ONLY, and only if they exactly
match the reviewed Chromium baseline. No installed tools are modified.
"""

from __future__ import annotations

from pathlib import Path
import re


CHROMIUM_BASELINE_SDK = "10.0.28000.0"
CHROMIUM_SDK_FILES = (
    "build/toolchain/win/setup_toolchain.py",
    "build/vs_toolchain.py",
)
# Chromium 156 assumes the BR (28000) SDK in its Windows version config.
# Older SDKs do not define NTDDI_WIN11_BR, so #if tests accidentally
# remove FILE_INFO_BY_HANDLE_CLASS from the Windows headers.
CHROMIUM_WINVER_FILE = "build/config/win/BUILD.gn"
CHROMIUM_WINVER_BASELINE = b'"NTDDI_VERSION=NTDDI_WIN11_BR",'
CHROMIUM_SDK_NTDDI = {
    "10.0.26100.0": b'"NTDDI_VERSION=NTDDI_WIN11_GE",',
    "10.0.28000.0": CHROMIUM_WINVER_BASELINE,
}
SDK_PIN_ANCHOR = "    # Enter source tree to run build commands\n"
SDK_PIN_STEP = (
    "    # Use a complete, validated Windows SDK for Chromium's own toolchain.\n"
    "    from scripts.chromium_sdk_pin import pin_chromium_sdk_version\n"
    "    pin_chromium_sdk_version(source_tree, os.environ['ARCIUM_WINDOWS_SDK'])\n"
)
SDK_VERSION_PATTERN = re.compile(rb"(?m)^SDK_VERSION = '([^'\r\n]+)'\r?$")


def pin_chromium_sdk_version(source_tree: Path, selected_version: str) -> list[str]:
    """Align pinned Chromium SDK constants and Windows NTDDI before GN generation.

    Fully validate both targets before writing either; fail on unknown sources.
    This intentionally fails closed for a future Chromium release.
    """
    if not re.fullmatch(r"10\.0\.\d+\.\d+", selected_version):
        raise ValueError("Invalid Windows SDK version")
    if selected_version not in CHROMIUM_SDK_NTDDI:
        raise ValueError("Unsupported Windows SDK for pinned Chromium 156 NTDDI")
    if not (source_tree / "BUILD.gn").is_file():
        raise FileNotFoundError("Chromium source root missing BUILD.gn")

    updates: list[tuple[Path, bytes]] = []
    for relative in CHROMIUM_SDK_FILES:
        target = source_tree / relative
        content = target.read_bytes()
        matches = SDK_VERSION_PATTERN.findall(content)
        if matches != [CHROMIUM_BASELINE_SDK.encode("ascii")]:
            raise ValueError(
                f"Unknown pinned Chromium SDK declaration in {relative}: {matches}"
            )
        old = ("SDK_VERSION = '" + CHROMIUM_BASELINE_SDK + "'").encode("ascii")
        new = ("SDK_VERSION = '" + selected_version + "'").encode("ascii")
        updated = content.replace(old, new)
        if updated.count(new) != 1:
            raise ValueError(f"Unexpected SDK replacement count in {relative}")
        updates.append((target, updated))

    # Ensure the Windows API target matches the selected installed SDK.
    # Validate all three files before writing any of them, failing closed
    # if the pinned Chromium 156 source structure changes.
    winver_file = source_tree / CHROMIUM_WINVER_FILE
    original_winver = winver_file.read_bytes()
    if original_winver.count(CHROMIUM_WINVER_BASELINE) != 1:
        raise ValueError("Unexpected Chromium Windows NTDDI declaration")
    updates.append((
        winver_file,
        original_winver.replace(
            CHROMIUM_WINVER_BASELINE, CHROMIUM_SDK_NTDDI[selected_version], 1
        ),
    ))

    for target, updated in updates:
        target.write_bytes(updated)
    print(
        f"Pinned Chromium toolchain SDK {CHROMIUM_BASELINE_SDK} -> "
        f"{selected_version}, Windows NTDDI "
        f"{CHROMIUM_SDK_NTDDI[selected_version].decode('ascii')} "
        f"in {len(updates)} source files",
        flush=True,
    )
    return [*CHROMIUM_SDK_FILES, CHROMIUM_WINVER_FILE]


def inject_chromium_sdk_pin(builder: str) -> str:
    """Inject before GN; strictly require the reviewed pinned builder anchor."""
    if builder.count(SDK_PIN_ANCHOR) != 1:
        raise ValueError("Expected exactly one upstream pre-GN source entry point")
    result = builder.replace(SDK_PIN_ANCHOR, SDK_PIN_STEP + SDK_PIN_ANCHOR, 1)
    compile(result, "arcium_sdk_pin_builder.py", "exec")
    return result
