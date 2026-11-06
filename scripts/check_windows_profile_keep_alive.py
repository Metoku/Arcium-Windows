"""Verify the shared Arcium profile origin and compile its real enum/logger.

The compiler contract copies only those two actual source files to a temporary
tree, with minimal build_config/NOTREACHED support. It is not a Chromium build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from scripts.apply_windows_arc_workflow import PROFILE_KEEP_ALIVE_METRICS, ROOT

HEADER = "chrome/browser/profiles/keep_alive/profile_keep_alive_types.h"
LOGGER = "chrome/browser/profiles/keep_alive/profile_keep_alive_types.cc"
PROFILE_KEEP_ALIVE_CONSUMERS = (
    "chrome/browser/ui/views/helium/arcium_space_editor_view.cc",
    "chrome/browser/ui/views/tabs/vertical/vertical_tab_strip_bottom_container.cc",
    "chrome/browser/importer/arcium_arc_spaces_import.cc",
    "chrome/browser/importer/arcium_arc_import_browsertest.cc",
)


def compile_contract(source: Path) -> dict:
    compiler = shutil.which("g++") or shutil.which("c++")
    if compiler is None:
        raise RuntimeError("A C++ compiler is required for the profile-origin contract")
    with tempfile.TemporaryDirectory(prefix="arcium profile origin ") as tmp:
        root = Path(tmp)
        files = {
            HEADER:(source / HEADER).read_bytes(),
            LOGGER:(source / LOGGER).read_bytes(),
            "build/build_config.h":b"#pragma once\n",
            "base/notreached.h":b"#pragma once\n#include <cstdlib>\n#define NOTREACHED() std::abort()\n",
            "contract.cc":b'''#include <iostream>
#include <sstream>
#include "chrome/browser/profiles/keep_alive/profile_keep_alive_types.h"
static_assert(static_cast<int>(ProfileKeepAliveOrigin::kArciumSettingsWindow) == 47);
static_assert(ProfileKeepAliveOrigin::kMaxValue == ProfileKeepAliveOrigin::kArciumSettingsWindow);
int main() {
  std::ostringstream out;
  out << ProfileKeepAliveOrigin::kArciumSettingsWindow;
  std::cout << out.str();
  return out.str() == "kArciumSettingsWindow" ? 0 : 1;
}
''',
        }
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        binary = root / "origin-contract.exe"
        build = subprocess.run(
            [compiler, "-std=c++20", "-Wall", "-Wextra", "-Wswitch-enum", "-Werror",
             "-I", str(root), str(root / LOGGER), str(root / "contract.cc"), "-o", str(binary)],
            text=True, encoding="utf-8", errors="replace", capture_output=True)
        if build.returncode:
            raise RuntimeError("Profile-origin C++ contract failed:\n" + build.stdout + build.stderr)
        run = subprocess.run([str(binary)], text=True, capture_output=True)
        if run.returncode or run.stdout != "kArciumSettingsWindow":
            raise RuntimeError("The compiled profile-origin logger returned the wrong result")
    return {"status":"PROFILE_ORIGIN_CPP_CONTRACT_PASSED",
            "minimal_transitive_support":True, "chromium_compiled":False}


def verify_profile_keep_alive(source: Path, *, compile_cpp: bool = False,
                              consumers: tuple[str, ...] = ()) -> dict:
    header = (source / HEADER).read_text(encoding="utf-8")
    definitions = dict(re.findall(r"^\s*(k\w+)\s*=\s*([^,\n]+),\s*$", header, re.MULTILINE))
    if (definitions.get("kArciumSettingsWindow") != "47" or
            definitions.get("kMaxValue") != "kArciumSettingsWindow"):
        raise RuntimeError("The Windows ProfileKeepAliveOrigin lacks kArciumSettingsWindow = 47")
    numeric = {name:int(value) for name, value in definitions.items() if value.isdecimal()}
    if len(numeric.values()) != len(set(numeric.values())):
        raise RuntimeError("Profile keep-alive enum values collide")
    root = ET.parse(source / PROFILE_KEEP_ALIVE_METRICS).getroot()
    matches = [node for node in root.iter("enum") if node.get("name") == "ProfileKeepAliveOrigin"]
    if len(matches) != 1:
        raise RuntimeError("Profile keep-alive metrics enum is ambiguous")
    entries = [(int(n.get("value")), n.get("label")) for n in matches[0].findall("int")]
    if len(entries) != len({number for number, _ in entries}):
        raise RuntimeError("Profile keep-alive metric values collide")
    metrics = dict(entries)
    logger = (source / LOGGER).read_text(encoding="utf-8")
    cases = dict(re.findall(
        r'case ProfileKeepAliveOrigin::(k\w+):\s*return out << "(k\w+)";', logger))
    for name, number in numeric.items():
        if metrics.get(number) != name or cases.get(name) != name:
            raise RuntimeError(f"Profile origin declaration/logger/metrics disagree: {name}")
    for relative in consumers:
        refs = set(re.findall(r"ProfileKeepAliveOrigin::(k\w+)",
                              (source / relative).read_text(encoding="utf-8")))
        if not refs or not refs <= definitions.keys():
            raise RuntimeError(f"Profile origin consumer has an unresolved reference: {relative}")
    return {"status":"PROFILE_ORIGIN_DECLARATION_LOGGER_AND_METRICS_VERIFIED",
            "origin":47, "consumer_count":len(consumers),
            "source_sha256":{p:hashlib.sha256((source / p).read_bytes()).hexdigest()
                             for p in (HEADER, LOGGER, PROFILE_KEEP_ALIVE_METRICS)},
            "cpp_contract":compile_contract(source) if compile_cpp else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "work/windows-platform/build/src")
    parser.add_argument("--compile", action="store_true")
    options = parser.parse_args()
    print(json.dumps(verify_profile_keep_alive(options.source_dir,
          compile_cpp=options.compile, consumers=PROFILE_KEEP_ALIVE_CONSUMERS), indent=2))


if __name__ == "__main__":
    main()
