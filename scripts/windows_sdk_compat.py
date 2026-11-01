#!/usr/bin/env python3
"""Select a *complete* Windows SDK, and adapt pinned Windows vcvars calls.

GitHub Windows runner images can contain partial SDK versions, for example a
vcvars-selected 10.0.28000.0 with missing Include/<version>/um. Require an
actual complete, installed SDK and pass it explicitly to Microsoft's documented
vcvarsall.bat amd64 <winsdk_version> invocation.

Only adapt exactly two pinned Helium-Windows build.py call sites.
"""

from __future__ import annotations

import os
from pathlib import Path
import re


ORIGINAL_VCVARS_CALL = """    cmd_input = ['call "%s" >nul' % _get_vcvars_path()]"""
PINNED_VCVARS_CALL = (
    '    cmd_input = [\'call "%s" amd64 %s >nul\' % (\n'
    "        str(_get_vcvars_path().parent / 'vcvarsall.bat'),\n"
    "        os.environ['ARCIUM_WINDOWS_SDK'])]"
)


def adapt_windows_vcvars(source: str) -> str:
    """Fail closed if either original Windows toolchain call has changed."""
    if source.count(ORIGINAL_VCVARS_CALL) != 2:
        raise ValueError(
            "Pinned Helium-Windows vcvars invocation changed; "
            "cannot safely select an explicit SDK"
        )
    adapted = source.replace(ORIGINAL_VCVARS_CALL, PINNED_VCVARS_CALL)
    compile(adapted, "arcium_sdk_compat_builder.py", "exec")
    return adapted


def windows_kits_root() -> Path:
    pf86 = os.environ.get("ProgramFiles(x86)")
    if not pf86:
        raise EnvironmentError("No ProgramFiles(x86); requires native Windows")
    return Path(pf86) / "Windows Kits" / "10"


def installed_complete_sdks(root: Path) -> list[str]:
    """Require Include+Lib x64 components, not merely SDK folder existence."""
    include = root / "Include"
    if not include.is_dir():
        return []
    selected: list[str] = []
    for entry in include.iterdir():
        if not entry.is_dir() or not re.fullmatch(
            r"10[.]0[.][0-9]+[.][0-9]+", entry.name
        ):
            continue
        version = entry.name
        needed = [
            include / version / "um",
            include / version / "shared",
            include / version / "ucrt",
            root / "Lib" / version / "um" / "x64",
            root / "Lib" / version / "ucrt" / "x64",
        ]
        if all(p.is_dir() for p in needed):
            selected.append(version)
    return sorted(
        selected, key=lambda v: tuple(int(n) for n in v.split(".")),
        reverse=True
    )


def select_windows_sdk(root: Path | None = None) -> str:
    root = root or windows_kits_root()
    candidates = installed_complete_sdks(root)
    if not candidates:
        available = (
            [p.name for p in (root / "Include").iterdir() if p.is_dir()]
            if (root / "Include").is_dir() else []
        )
        raise EnvironmentError(
            f"No complete x64 Windows SDK under {root}. "
            f"Include folders: {available}"
        )
    selected = candidates[0]
    print(
        f"Complete Windows SDK candidates: {candidates}; "
        f"selected {selected}", flush=True
    )
    return selected
