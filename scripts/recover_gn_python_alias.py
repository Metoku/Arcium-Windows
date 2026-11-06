#!/usr/bin/env python3
"""Resume ONLY GN generation after source preparation reached a failed GN call.

This is NOT a generic restart. Require a failed *prior* verified adapter run,
the exact generated builder, matching pinned audit, and the GN invocation log.
It never downloads/extracts sources, reapplies patches, or invokes Ninja.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.gn_smoke import create_gn_only_builder
from scripts.windows_port import ROOT, audit_staged
from scripts.windows_sdk_compat import select_windows_sdk

REQUIRED_SDK = "10.0.28000.0"
GN_MARKER = "PINNED_WINDOWS_GN_GENERATED\n"


def verify_prepared_state(platform: Path, report: dict, log: Path) -> Path:
    """Fail closed if this is not the post-patching GN failure path."""
    audit = audit_staged(platform)
    required = {
        "status": "FAILED",
        "source_download_attempted": True,
        "chromium_version": audit["chromium_version"],
        "core_commit": audit["arcium_commit"],
        "platform_commit": audit["platform_commit"],
        "windows_sdk_version": REQUIRED_SDK,
        "expected_core_patches": audit["shared_patch_count"],
        "expected_windows_patches": audit["windows_patch_count"],
    }
    for key, expected in required.items():
        if report.get(key) != expected:
            raise ValueError(
                f"GN recovery refused: report {key!r} is not {expected!r}. "
                "Do not delete or overwrite prepared Chromium sources."
            )
    source = platform / "build" / "src"
    generated = platform / "arcium_gn_only.py"
    marker = platform / "ARCIUM_GN_GENERATED.marker"
    if marker.exists():
        raise FileExistsError("GN marker already exists; do not run GN recovery")
    if not generated.is_file():
        raise FileNotFoundError("Original generated GN-only builder is missing")
    release_candidate = report.get("release_candidate_integrations", False)
    if type(release_candidate) is not bool:
        raise ValueError("GN recovery refused: release candidate mode is not a boolean")
    upstream = (platform / "build.py").read_text(encoding="utf-8")
    # Accept complete reviewed snapshots for this recorded mode, including
    # the pre-fix builder already used to prepare the user's Chromium tree.
    expected_builders = {
        create_gn_only_builder(upstream, release_candidate=release_candidate,
                               pin_python=pin_python)
        for pin_python in (True, False)
    }
    if generated.read_text(encoding="utf-8") not in expected_builders:
        raise ValueError("Generated GN-only builder differs from reviewed pinned input")

    files = (
        "BUILD.gn",
        ".gn",
        "out/Default/args.gn",
        "buildtools/win/gn.exe",
        "build/toolchain/get_concurrent_links.py",
    )
    for relative in files:
        if not (source / relative).is_file():
            raise FileNotFoundError(f"Missing prepared Chromium file {relative}")

    if not log.is_file():
        raise FileNotFoundError("Missing original GN preparation log")
    with log.open("rb") as stream:
        try:
            stream.seek(-131072, os.SEEK_END)
        except OSError:
            stream.seek(0)
        recent = stream.read().lower()
    # The patched builder invokes GN ONLY after both complete patch series,
    # domain/name substitution, version/resources and SDK pinning finished.
    if b"buildtools\\win\\gn.exe" not in recent or b"gen" not in recent:
        raise ValueError("Original preparation log does not prove it reached GN")
    if b"python was not found" not in recent or b"microsoft store" not in recent:
        raise ValueError("This recovery is only for the observed Python Store-alias failure")
    return source


def find_vcvarsall() -> Path:
    pf86 = os.environ.get("ProgramFiles(x86)")
    if not pf86:
        raise EnvironmentError("Windows x64 ProgramFiles(x86) is missing")
    vswhere = Path(pf86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        raise FileNotFoundError("Visual Studio vswhere.exe missing")
    result = subprocess.run(
        [str(vswhere), "-latest", "-prerelease", "-products", "*",
         "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
         "-property", "installationPath"],
        check=True, capture_output=True, text=True,
    )
    location = result.stdout.strip()
    if not location:
        raise EnvironmentError("Visual Studio desktop C++ x64 build tools missing")
    vcvars = Path(location) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    if not vcvars.is_file():
        raise FileNotFoundError(f"MSVC environment script missing: {vcvars}")
    return vcvars


def recover(platform: Path, report_path: Path, *, execute: bool) -> int:
    if sys.platform != "win32":
        raise OSError("GN recovery must execute on Windows")
    log = report_path.with_suffix(".log")
    if not report_path.is_file():
        raise FileNotFoundError(f"Missing original report {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    source = verify_prepared_state(platform, report, log)
    selected = select_windows_sdk()
    if selected != REQUIRED_SDK:
        raise EnvironmentError(
            f"GN recovery needs installed SDK {REQUIRED_SDK}, selected {selected}"
        )
    python = Path(sys.executable).resolve()
    if "windowsapps" in str(python).lower() or not python.is_file():
        raise EnvironmentError("Use a real installed Python interpreter, not a Store alias")
    vcvars = find_vcvarsall()
    marker = platform / "ARCIUM_GN_GENERATED.marker"
    ninja = source / "out" / "Default" / "build.ninja"
    print(f"GN-only recovery: {source}")
    print(f"GN Python interpreter: {python}")
    print(f"Verified MSVC toolchain: {vcvars}")
    if not execute:
        print("GN recovery prerequisites passed. No sources changed; rerun with --execute.")
        return 0

    # Avoid cmd.exe expansion and encoding ambiguity; the intended user paths
    # (D:\\src\\Arcium-Windows, C:\\Program Files\\Python314) are supported.
    for path in (str(source), str(python), str(vcvars)):
        if not path.isascii() or any(c in path for c in '%!^&|<>"\r\n'):
            raise ValueError("Unsupported cmd.exe special character in build tool path")

    # --script-executable explicitly selects the installed Python used by
    # Chromium GN exec_script(), bypassing WindowsApps/python3.exe.
    # This also persists in generated GN/Ninja command rules.
    lines = [
        "@echo off",
        f'call "{vcvars}" amd64 {REQUIRED_SDK} >nul',
        "if errorlevel 1 exit /b %errorlevel%",
        'set "DEPOT_TOOLS_WIN_TOOLCHAIN=0"',
        f'set "ARCIUM_WINDOWS_SDK={REQUIRED_SDK}"',
        f'cd /d "{source}"',
        "if errorlevel 1 exit /b %errorlevel%",
        f'"buildtools\\win\\gn.exe" gen out\\Default --fail-on-unused-args '
        f'--script-executable="{python}"',
        "exit /b %errorlevel%",
    ]
    command_path = ROOT / "work" / "arcium-recover-gn.cmd"
    if command_path.exists():
        raise FileExistsError(f"Refusing to replace existing command file: {command_path}")
    command_path.write_text("\r\n".join(lines) + "\r\n", encoding="ascii")
    recovery_log = ROOT / "work" / "gn-recovery.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        with recovery_log.open("w", encoding="utf-8", errors="replace") as out:
            proc = subprocess.run(
                [os.environ.get("ComSpec", "cmd.exe"), "/d", "/c", str(command_path)],
                cwd=platform, env=env, stdout=out, stderr=subprocess.STDOUT,
                check=False, timeout=1800,
            )
    finally:
        command_path.unlink(missing_ok=True)
    tail = recovery_log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
    print("\n".join(tail))
    if proc.returncode != 0 or not ninja.is_file():
        print(
            f"GN-only recovery failed ({proc.returncode}); see {recovery_log}. "
            "Source archives and applied patches have NOT been deleted.",
            file=sys.stderr,
        )
        return proc.returncode or 2
    marker.write_text(GN_MARKER, encoding="utf-8")
    report.update({
        "status": "GN_GENERATED",
        "full_patch_application_verified": True,
        "gn_generation_verified": True,
        "gn_recovered_from_python_store_alias_error": True,
        "gn_recovery_log": str(recovery_log),
        "native_compile_attempted": False,
        "exit_code": 0,
    })
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("ARCIUM_WINDOWS_GN_GENERATION_PASSED (recovered, no Ninja compilation)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run only GN, then mark success")
    parser.add_argument("--platform-dir", type=Path, default=ROOT / "work" / "windows-platform")
    parser.add_argument("--report", type=Path, default=ROOT / "work" / "gn-generation.json")
    args = parser.parse_args()
    try:
        return recover(args.platform_dir.resolve(), args.report.resolve(), execute=args.execute)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyError) as error:
        print(f"GN recovery refused: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
