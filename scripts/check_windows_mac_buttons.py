"""Replay the opt-in caption style beside the four existing Windows catalogs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from scripts.apply_windows_arc_workflow import ROOT, integrate, patch_targets


MAC_PATCH = ROOT / "patches/windows/mac-window-buttons.patch"
MAC_API_FILES = ("ui/gfx/canvas.h", "ui/views/view.h")


def cpp_function(text: str, signature: str) -> str:
    start = text.index(signature)
    opening = text.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        if text[end] == "{": depth += 1
        if text[end] == "}": depth -= 1
        end += 1
    return text[start:end]


def verify_mac_excerpts(source: Path) -> dict:
    fixture = json.loads((ROOT / "tests/fixtures/mac_window_functions.json").read_text())
    count = 0
    for name, functions in fixture["files"].items():
        actual = (source / name).read_text(encoding="utf-8")
        for signature, expected in functions.items():
            if cpp_function(actual, signature) != expected:
                raise RuntimeError(f"Mac caption compiler fixture differs from pinned source: {signature}")
            count += 1
    declarations = json.loads((ROOT / "tests/fixtures/mac_window_api.json").read_text())
    hashes = {}
    for name, snippets in declarations.items():
        path = source / name
        actual = path.read_text(encoding="utf-8")
        for snippet in snippets:
            if actual.count(snippet) != 1:
                raise RuntimeError(f"Mac caption API fixture differs from pinned source: {snippet}")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"function_bodies_verified": count, "api_sha256": hashes}


def check_mac_buttons(source: Path, originals: dict[str, bytes], catalogs: tuple[Path, ...]) -> dict:
    """Check both overlapping catalog orders in every supported source format."""
    if not (shutil.which("g++") or shutil.which("c++")):
        raise RuntimeError("A C++ compiler is required for Mac caption contract checks")
    checks, proof, postimages = [], None, {}
    for style in ("LF", "CRLF", "mixed", "missing-final-newline"):
        baseline = {}
        for index, (name, data) in enumerate(sorted(originals.items())):
            data = data.replace(b"\r\n", b"\n")
            if style == "CRLF" or (style == "mixed" and index % 2):
                data = data.replace(b"\n", b"\r\n")
            if style == "missing-final-newline":
                data = data.removesuffix(b"\n")
            baseline[name] = data
            (source / name).write_bytes(data)
        for order in ((MAC_PATCH, *catalogs), (*catalogs, MAC_PATCH)):
            for patch in order:
                times = {p:(source / p).stat().st_mtime_ns for p in originals}
                if integrate(source, patch=patch) != "READY":
                    raise RuntimeError(f"Mac coexistence check was not ready: {patch.name}")
                if times != {p:(source / p).stat().st_mtime_ns for p in originals}:
                    raise RuntimeError("Read-only Mac caption check rewrote source")
                integrate(source, patch=patch, apply=True)
            postimage = {p:(source / p).read_bytes() for p in originals}
            if style in postimages and postimage != postimages[style]:
                raise RuntimeError("Mac caption result depends on catalog application order")
            postimages[style] = postimage
            if proof is None:
                proof = verify_mac_excerpts(source)
                # Preserve all original action callbacks and native Snap hit mapping.
                name = "chrome/browser/ui/views/frame/browser_caption_button_container_win.cc"
                before, after = originals[name].decode(), (source / name).read_text()
                for signature in ("BrowserCaptionButtonContainer::BrowserCaptionButtonContainer(",
                                  "int BrowserCaptionButtonContainer::NonClientHitTest("):
                    if cpp_function(before, signature) != cpp_function(after, signature):
                        raise RuntimeError("Mac caption style altered native action callbacks or hit mapping")
                proof["native_action_bindings_and_hit_mapping_preserved"] = True
                result = subprocess.run(
                    [sys.executable, "-m", "unittest", "tests.test_windows_mac_buttons", "-v"],
                    cwd=ROOT, text=True, encoding="utf-8", capture_output=True)
                if result.returncode or "skipped=" in result.stderr:
                    raise RuntimeError("Mac caption C++ contracts failed:\n" + result.stdout + result.stderr)
                proof["cpp_contracts_passed"] = True
            times = {p:(source / p).stat().st_mtime_ns for p in originals}
            for patch in order:
                integrate(source, patch=patch, apply=True)
            if times != {p:(source / p).stat().st_mtime_ns for p in originals}:
                raise RuntimeError("Idempotent Mac caption application rewrote source")
            for patch in reversed(order):
                integrate(source, patch=patch, revert=True)
            if baseline != {p:(source / p).read_bytes() for p in originals}:
                raise RuntimeError("Mac caption revert did not restore exact original bytes")
            checks.append({"endings":style, "order":[p.name for p in order]})
    return {"status":"MAC_CAPTION_REPLAY_AND_CONTRACTS_PASSED", "checks":checks,
            "proof":proof, "browser_compiled":False, "native_rendering_verified":False}
