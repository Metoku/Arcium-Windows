#!/usr/bin/env python3
"""Reviewable bridge between pinned Helium-Windows and newer Arcium version API.

Helium-Windows 0.20.1.1 appends HELIUM_* fields through two functions that
no longer exist in dr-baker/Arcium's utils/helium_version.py.
Arcium's refresh_version(path, parts) replaces both safely and idempotently.

Only rewrite an exact, reviewed block from the pinned Windows build.py.
Reject unknown future upstream layouts instead of silently patching them.
"""

from __future__ import annotations

from pathlib import Path


OLD_VERSION_BLOCK = (
    "        # Set version\n"
    "        version_parts = helium_version.get_version_parts(_ROOT_DIR / 'helium-chromium', _ROOT_DIR)\n"
    '        chrome_version_path = source_tree / "chrome" / "VERSION"\n'
    "        helium_version.check_existing_version(chrome_version_path)\n"
    '        with open(chrome_version_path, "a") as f:\n'
    "            for name, version in version_parts.items():\n"
    "                helium_version.append_version(f, name, version)\n"
)

NEW_VERSION_BLOCK = (
    "        # Set version using the pinned Arcium core's supported API.\n"
    "        version_parts = helium_version.get_version_parts(_ROOT_DIR / 'helium-chromium', _ROOT_DIR)\n"
    '        chrome_version_path = source_tree / "chrome" / "VERSION"\n'
    "        helium_version.refresh_version(chrome_version_path, version_parts)\n"
)


def adapt_builder_version_api(source: str) -> str:
    """Replace the known obsolete Windows version call sequence exactly once."""
    if source.count(OLD_VERSION_BLOCK) != 1:
        raise ValueError(
            "Pinned Helium-Windows version block no longer matches; "
            "review the platform builder before updating this adapter"
        )
    if "helium_version.refresh_version(" in source:
        raise ValueError("Version API replacement already present")
    adapted = source.replace(OLD_VERSION_BLOCK, NEW_VERSION_BLOCK, 1)
    compile(adapted, "arcium_windows_compat_builder.py", "exec")
    return adapted


def assert_arcium_version_api(script_file: Path) -> None:
    """Assert the source core at the pinned commit still has the expected API."""
    code = script_file.read_text(encoding="utf-8")
    if ("def refresh_version(" not in code or
            "def get_version_parts(" not in code):
        raise ValueError("Arcium version module API changed unexpectedly")
    if "def check_existing_version(" in code or "def append_version(" in code:
        raise ValueError("Arcium core version API no longer matches review")
