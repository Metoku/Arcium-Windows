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
SDK_PIN_ANCHOR = "    # Enter source tree to run build commands\n"
SDK_PIN_STEP = (
    "    # Use a complete, validated Windows SDK for Chromium's own toolchain.\n"
    "    from scripts.chromium_sdk_pin import pin_chromium_sdk_version\n"
    "    pin_chromium_sdk_version(source_tree, os.environ['ARCIUM_WINDOWS_SDK'])\n"
)
SDK_VERSION_PATTERN = re.compile(rb"(?m)^SDK_VERSION = '([^'\r\n]+)'\r?$")


def pin_chromium_sdk_version(source_tree: Path, selected_version: str) -> list[str]:
    """Change exactly two pinned Chromium source constants before GN generation.

    Fully validate both targets before writing either; fail on unknown sources.
    This intentionally fails closed for a future Chromium release.
    """
    if not re.fullmatch(r"10\.0\.\d+\.\d+", selected_version):
        raise ValueError("Invalid Windows SDK version")
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

    for target, updated in updates:
        target.write_bytes(updated)
    print(
        f"Pinned Chromium toolchain SDK {CHROMIUM_BASELINE_SDK} -> "
        f"{selected_version} in {len(updates)} source files",
        flush=True,
    )
    return list(CHROMIUM_SDK_FILES)


def inject_chromium_sdk_pin(builder: str) -> str:
    """Inject before GN; strictly require the reviewed pinned builder anchor."""
    if builder.count(SDK_PIN_ANCHOR) != 1:
        raise ValueError("Expected exactly one upstream pre-GN source entry point")
    result = builder.replace(SDK_PIN_ANCHOR, SDK_PIN_STEP + SDK_PIN_ANCHOR, 1)
    compile(result, "arcium_sdk_pin_builder.py", "exec")
    return result
