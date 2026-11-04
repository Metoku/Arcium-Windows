#!/usr/bin/env python3
"""Apply an optional Windows Arc integration to a prepared Chromium tree.

The default is a read-only check. This never downloads source, changes GN flags,
cleans build output, launches a browser, or edits a browser profile.
"""

from __future__ import annotations

import argparse
import difflib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "windows" / "arc-workflow-settings.patch"
ONBOARDING_PATCH = ROOT / "patches/windows/onboarding-windows.patch"
PASSWORD_PATCH = ROOT / "patches/windows/arc-password-import-windows.patch"
MAC_CAPTION_SOURCE = "chrome/browser/ui/views/frame/browser_caption_button_container_win.cc"
LEGACY_MAC_LAYOUT_INVALIDATION = b"    button->PreferredSizeChanged();"
MAC_LAYOUT_INVALIDATION = b"    button->InvalidateLayout();"
EXTERNAL_EXTENSION_SOURCE = "chrome/browser/extensions/external_registry_loader_win.cc"
LEGACY_EXTERNAL_EXTENSION_REGISTRY = (
    b'const wchar_t kRegistryExtensions[] = L"Software\\\\Google\\\\Chrome\\\\Extensions";')
EXTERNAL_EXTENSION_REGISTRY = (
    b'const wchar_t kRegistryExtensions[] = L"Software\\\\Arcium\\\\Extensions";')
# These exact existing files are also part of the Windows first-run integration.
# Keep the general components tree outside the application helper's write scope.
ONBOARDING_EXTERNAL_TARGETS = frozenset({
    "components/policy/tools/generate_policy_source.py",
    "components/helium_onboarding/helium_onboarding_strings.grdp",
    "components/helium_onboarding/BUILD.gn",
    "components/helium_onboarding/src/pages/Welcome.svelte",
    "components/helium_onboarding/src/pages/DataImport.svelte",
})
SHORTCUT_SOURCE = "chrome/browser/resources/settings/system_page/browser_shortcuts_page.ts"
LEGACY_RESTORE_CHECK = b"    return !busy && !!preset?.canModify && !!preset.hasPrevious;"
RESTORE_CHECK = b"    return !busy && !!preset?.canModify && preset.hasPrevious;"
APPEARANCE_CSS_SOURCE = "chrome/browser/resources/settings/appearance_page/appearance_layout_page.css"
# Exact method names shipped before Chromium's template lint was replayed.
# These replacements are staged together and accepted only when the complete
# corrected catalog reverse-checks; unknown local edits are never patched over.
APPEARANCE_HANDLER_RENAMES = {
    "chrome/browser/resources/side_panel/customize_chrome/app": {
        "onWorkspaceAppearance_": "onWorkspaceAppearanceClick_",
        "onCloseWorkspacePanel_": "onCloseWorkspacePanelClick_",
    },
    "chrome/browser/resources/settings/appearance_page/appearance_layout_page": {
        "onWorkspacePreset_": "onWorkspacePresetClick_",
        "onResetWorkspacePalette_": "onResetWorkspacePaletteClick_",
        "onRemoveWorkspaceGlow_": "onRemoveWorkspaceGlowClick_",
        "onAddWorkspaceGlow_": "onAddWorkspaceGlowClick_",
        "onWorkspaceGlow_": "onWorkspaceGlowChange_",
    },
}
APPEARANCE_LAYOUT_SOURCE = (
    "chrome/browser/resources/settings/appearance_page/appearance_layout_page.ts")
APPEARANCE_LAYOUT_TEMPLATE = APPEARANCE_LAYOUT_SOURCE.removesuffix(".ts") + ".html.ts"
LEGACY_SURFACE_LABEL = b"value[0]!.toUpperCase() + value.slice(1)"
SURFACE_LABEL = b"value.charAt(0).toUpperCase() + value.slice(1)"
APPEARANCE_SNAPSHOT_SOURCES = tuple(
    "chrome/browser/ui/webui/settings/appearance_handler." + suffix
    for suffix in ("h", "cc"))
LEGACY_SNAPSHOT_SIGNATURE = b"ArciumAppearanceSnapshot() const"
SNAPSHOT_SIGNATURE = b"ArciumAppearanceSnapshot()"
APPEARANCE_FRAME_SOURCE = "chrome/browser/ui/views/frame/browser_frame_view_win.cc"
LEGACY_FRAME_GRADIENT = b"      const SkColor colors[] = {color, SkColorSetA(color, 0)};\n"
FRAME_GRADIENT = b"""      const SkColor4f colors[] = {SkColor4f::FromColor(color),
                                 SkColor4f::FromColor(SkColorSetA(color, 0))};
"""
APPEARANCE_CUSTOMIZE_UI_SOURCE = (
    "chrome/browser/ui/webui/side_panel/customize_chrome/customize_chrome_ui.cc")
LEGACY_SETTINGS_STRINGS_INCLUDE = b'#include "chrome/grit/settings_strings.h"\n'
GENERATED_RESOURCES_INCLUDE = b'#include "chrome/grit/generated_resources.h"\n'
LEGACY_CLOSE_WORKSPACE_STRING = b'{"closeWorkspacePanel", IDS_CLOSE}'
CLOSE_WORKSPACE_STRING = b'{"closeWorkspacePanel", IDS_NTP_CLOSE}'
APPEARANCE_CAPTURE_SOURCE = "chrome/browser/ui/helium/arcium_settings_model.cc"
LEGACY_WINDOW_TYPE_CHECK = b"      !browser->GetIsNormalType()) {"
WINDOW_TYPE_CHECK = b"      browser->GetType() != BrowserWindowInterface::Type::TYPE_NORMAL) {"
APPEARANCE_COLOR_PICKER_SOURCE = (
    "chrome/browser/ui/webui/cr_components/theme_color_picker/theme_color_picker_handler.cc")
LEGACY_DARK_COLOR_CHECK = b"        mode == 2 || (mode == 0 && native_theme->ShouldUseDarkColors());"
DARK_COLOR_CHECK = b"""        mode == 2 ||
        (mode == 0 && native_theme->preferred_color_scheme() ==
                          ui::NativeTheme::PreferredColorScheme::kDark);"""
LEGACY_DISCONNECT = b"""  override disconnectedCallback() {
    ++this.workspaceGeneration_;
    super.disconnectedCallback();
  }

"""
# Exact CSS emitted by the first appearance catalog; never rewrite unknown CSS.
LEGACY_APPEARANCE_CSS = b""".workspace-description { padding: 0 20px; color: var(--cr-secondary-text-color); }
fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
.workspace-row { display: flex; align-items: center; justify-content: space-between;
  gap: 20px; min-height: 48px; padding: 8px 20px; border-top: var(--cr-separator-line); }
.workspace-row > span { flex: 1; }
.workspace-row select { max-width: 55%; }
.workspace-row input[type=number] { width: 80px; }
.workspace-row input[type=range] { width: 160px; max-width: 45%; }
.workspace-glow { padding: 12px 20px; border-top: var(--cr-separator-line); }
.workspace-glow summary { cursor: pointer; }
button, select, input[type=number] { color: var(--cr-primary-text-color);
  background: var(--cr-card-background-color); border: 1px solid var(--cr-separator-color);
  border-radius: 6px; padding: 8px; font: inherit; }
button { cursor: pointer; }
button:focus-visible, select:focus-visible, input:focus-visible { outline: 2px solid var(--cr-focus-outline-color); }
"""



def patch_targets(text: str) -> list[str]:
    """Allow existing Chromium UI files and the exact Windows setup targets."""
    old_paths = re.findall(r"^--- a/(\S+)$", text, re.MULTILINE)
    new_paths = re.findall(r"^\+\+\+ b/(\S+)$", text, re.MULTILINE)
    if (not old_paths or old_paths != new_paths
            or len(set(old_paths)) != len(old_paths)
            or len(re.findall(r"^--- ", text, re.MULTILINE)) != len(old_paths)
            or len(re.findall(r"^\+\+\+ ", text, re.MULTILINE)) != len(new_paths)
            or "GIT binary patch" in text):
        raise ValueError("Expected one in-place edit per patch target")
    for path in new_paths:
        parts = PurePosixPath(path).parts
        if (
            (not path.startswith("chrome/") and path not in ONBOARDING_EXTERNAL_TARGETS)
            or ".." in parts
            or "\\" in path
            or ":" in path
            or PurePosixPath(path).is_absolute()
        ):
            raise ValueError(f"Unsafe patch target: {path}")
    return new_paths


def appearance_css_addition(patch_bytes: bytes) -> bytes:
    marker = ("--- a/" + APPEARANCE_CSS_SOURCE + "\n+++ b/" +
              APPEARANCE_CSS_SOURCE + "\n").encode()
    _, found, section = patch_bytes.partition(marker)
    if not found:
        raise ValueError("Appearance catalog has no CSS section")
    section = re.split(rb"(?m)^--- a/", section, maxsplit=1)[0]
    addition = b"".join(line[1:] for line in section.splitlines(keepends=True)
                        if line.startswith(b"+")).lstrip(b"\n")
    if not addition.startswith(b".workspace-description {\n"):
        raise ValueError("Appearance catalog does not contain the corrected CSS block")
    return addition


def git_apply(source: Path, patch: Path, *, reverse: bool, check: bool) -> subprocess.CompletedProcess[str]:
    # Do not inherit an outer repository's working-directory prefix (work/src
    # is normally inside Arcium-Windows), which can silently skip every hunk.
    # Absolute targets are permitted only after validating the fixed catalog.
    command = ["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf",
               "apply", "--unsafe-paths", "--whitespace=nowarn",
               f"--directory={source.as_posix()}"]
    if reverse:
        command.append("--reverse")
    if check:
        command.append("--check")
    command.append(str(patch))
    env = os.environ.copy()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="arcium-patch-") as temporary:
        return subprocess.run(command, cwd=temporary, env=env, text=True,
                              encoding="utf-8", errors="replace",
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def preserve_line_endings(original: bytes, changed_lf: bytes) -> bytes:
    """Keep unchanged lines byte-identical; insert with this file's EOL style."""
    original_lf = original.replace(b"\r\n", b"\n")
    # Git validates LF-terminated temporary lines. Keep the user's original
    # missing final newline when committing those snapshots back to source.
    if original and not original.endswith(b"\n") and changed_lf.endswith(b"\n"):
        changed_lf = changed_lf[:-1]
    if original_lf == changed_lf:
        return original
    crlf_count = original.count(b"\r\n")
    bare_lf_count = original.count(b"\n") - crlf_count
    if crlf_count == 0:
        return changed_lf
    if bare_lf_count == 0:
        return changed_lf.replace(b"\n", b"\r\n")
    newline = b"\r\n" if crlf_count > bare_lf_count else b"\n"
    normalized_lines = original_lf.splitlines(keepends=True)
    original_lines = original.splitlines(keepends=True)
    changed_lines = changed_lf.splitlines(keepends=True)
    result: list[bytes] = []
    matcher = difflib.SequenceMatcher(
        None, normalized_lines, changed_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result.extend(original_lines[i1:i2])
        elif tag in ("insert", "replace"):
            result.extend(line[:-1] + newline if line.endswith(b"\n") else line
                          for line in changed_lines[j1:j2])
    return b"".join(result)


def atomic_write(path: Path, data: bytes) -> None:
    """Replace a source file without leaving a partially written destination."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=".arcium-workflow-", delete=False) as stream:
            temporary_path = Path(stream.name)
            stream.write(data)
        os.chmod(temporary_path, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def commit_source_changes(source: Path, originals: dict[str, bytes],
                          changes: dict[str, bytes]) -> None:
    # Check every source before writing any. A concurrent edit during staging
    # must not cause the remaining original snapshot to overwrite that edit.
    for target, content in originals.items():
        if (source / target).read_bytes() != content:
            raise RuntimeError(f"Source changed during patch validation: {target}. "
                               "No changes made; retry after finishing source edits.")
    written: list[str] = []
    try:
        for target, content in changes.items():
            if (source / target).read_bytes() != originals[target]:
                raise RuntimeError(f"Source changed during patch application: {target}")
            atomic_write(source / target, content)
            written.append(target)
    except (OSError, RuntimeError) as error:
        rollback_errors: list[str] = []
        for target in reversed(written):
            try:
                if (source / target).read_bytes() != changes[target]:
                    raise RuntimeError("a concurrent edit must be preserved")
                atomic_write(source / target, originals[target])
            except (OSError, RuntimeError) as rollback_error:
                rollback_errors.append(f"{target}: {rollback_error}")
        if rollback_errors:
            raise RuntimeError("Could not finish restoring source files after "
                               f"{error}:\n" + "\n".join(rollback_errors)) from error
        raise RuntimeError("Source update failed; previously written files were "
                           f"restored. {error}") from error


def integrate(source: Path, *, apply: bool = False, revert: bool = False,
              patch: Path = PATCH) -> str:
    source = source.resolve(strict=True)
    patch = patch.resolve(strict=True)
    patch_bytes = patch.read_bytes().replace(b"\r\n", b"\n")
    targets = patch_targets(patch_bytes.decode("utf-8"))
    if not (source / "BUILD.gn").is_file():
        raise ValueError("Expected a prepared Chromium source root containing BUILD.gn")
    # Reject symlink escapes before allowing git to write absolute paths.
    for target in targets:
        resolved = (source / target).resolve(strict=True)
        if not resolved.is_relative_to(source) or not resolved.is_file():
            raise ValueError(f"Patch target escapes the source root: {target}")
    if apply and revert:
        raise ValueError("Choose apply or revert")
    originals = {target: (source / target).read_bytes() for target in targets}
    # Git auto-CRLF can convert the catalog while Chromium has mixed LF/CRLF
    # files. Compare and patch LF snapshots, never normalize the real tree.
    with tempfile.TemporaryDirectory(prefix="arcium-workflow-stage-") as temporary:
        staging = Path(temporary)
        staged_source = staging / "src"
        for target, content in originals.items():
            staged_file = staged_source / target
            staged_file.parent.mkdir(parents=True, exist_ok=True)
            normalized = content.replace(b"\r\n", b"\n")
            # These catalogs were generated from LF-terminated source. A local
            # missing EOF newline is formatting drift, not a missing hunk.
            if normalized and not normalized.endswith(b"\n") and (
                    b"\\ No newline at end of file" not in patch_bytes):
                normalized += b"\n"
            staged_file.write_bytes(normalized)
        staged_patch = staging / "workflow.patch"
        staged_patch.write_bytes(patch_bytes)
        forward = git_apply(staged_source, staged_patch, reverse=False, check=True)
        backward = git_apply(staged_source, staged_patch, reverse=True, check=True)
        needs_upgrade = False
        if (forward.returncode and backward.returncode
                and patch.name == "mac-window-buttons.patch"
                and MAC_CAPTION_SOURCE in targets):
            path = staged_source / MAC_CAPTION_SOURCE
            before = path.read_bytes()
            if before.count(LEGACY_MAC_LAYOUT_INVALIDATION) == 1:
                path.write_bytes(before.replace(
                    LEGACY_MAC_LAYOUT_INVALIDATION, MAC_LAYOUT_INVALIDATION, 1))
                corrected = git_apply(staged_source, staged_patch, reverse=True, check=True)
                # Recognize only the fully applied earlier caption catalog.
                # A matching line in an unknown/partial tree authorizes no writes.
                if corrected.returncode == 0:
                    backward = corrected
                    needs_upgrade = True
        if (forward.returncode and backward.returncode
                and patch.name == ONBOARDING_PATCH.name
                and EXTERNAL_EXTENSION_SOURCE in targets):
            path = staged_source / EXTERNAL_EXTENSION_SOURCE
            before = path.read_bytes()
            if before.count(LEGACY_EXTERNAL_EXTENSION_REGISTRY) == 1:
                path.write_bytes(before.replace(
                    LEGACY_EXTERNAL_EXTENSION_REGISTRY, EXTERNAL_EXTENSION_REGISTRY, 1))
                corrected = git_apply(staged_source, staged_patch, reverse=True, check=True)
                # Accept the earlier ten-file onboarding catalog only when the
                # complete current catalog verifies. Unknown partial edits fail.
                if corrected.returncode == 0:
                    backward = corrected
                    needs_upgrade = True
        # An earlier version was applied successfully but failed Chromium's
        # type-aware lint. Repair only that known line in the temporary copy;
        # the complete corrected patch must then reverse-check successfully.
        if (forward.returncode and backward.returncode
                and SHORTCUT_SOURCE in targets
                and b"+" + RESTORE_CHECK + b"\n" in patch_bytes):
            shortcut_file = staged_source / SHORTCUT_SOURCE
            shortcut_bytes = shortcut_file.read_bytes()
            if shortcut_bytes.count(LEGACY_RESTORE_CHECK) == 1:
                shortcut_file.write_bytes(shortcut_bytes.replace(
                    LEGACY_RESTORE_CHECK, RESTORE_CHECK, 1))
                corrected = git_apply(staged_source, staged_patch,
                                      reverse=True, check=True)
                if corrected.returncode == 0:
                    backward = corrected
                    needs_upgrade = True
        stale_resource_include = (
            patch.name == "arc-appearance-windows.patch"
            and APPEARANCE_CUSTOMIZE_UI_SOURCE in targets
            and LEGACY_SETTINGS_STRINGS_INCLUDE in
                (staged_source / APPEARANCE_CUSTOMIZE_UI_SOURCE).read_bytes())
        if ((backward.returncode or stale_resource_include)
                and patch.name == "arc-appearance-windows.patch"
                and APPEARANCE_CSS_SOURCE in targets):
            staged_upgrade = False
            css_file = staged_source / APPEARANCE_CSS_SOURCE
            css_bytes = css_file.read_bytes()
            if css_bytes.count(LEGACY_APPEARANCE_CSS) == 1:
                css_file.write_bytes(css_bytes.replace(
                    LEGACY_APPEARANCE_CSS, appearance_css_addition(patch_bytes), 1))
                staged_upgrade = True
            for stem, renames in APPEARANCE_HANDLER_RENAMES.items():
                for suffix in (".ts", ".html.ts"):
                    target = stem + suffix
                    if target not in targets:
                        continue
                    path = staged_source / target
                    before = path.read_bytes()
                    after = before
                    for old, new in renames.items():
                        after = re.sub(rb"\b" + old.encode() + rb"\b", new.encode(), after)
                    if after != before:
                        path.write_bytes(after)
                        staged_upgrade = True
            if APPEARANCE_LAYOUT_SOURCE in targets:
                path = staged_source / APPEARANCE_LAYOUT_SOURCE
                before = path.read_bytes()
                after = before
                # The old catalog placed this lifecycle method before
                # connectedCallback(), contrary to Chromium's class-order rule.
                connected = after.find(b"  override connectedCallback() {")
                if (after.count(LEGACY_DISCONNECT) == 1
                        and after.index(LEGACY_DISCONNECT) < connected):
                    anchor = b"  protected showVerticalSettings_(): boolean {"
                    if after.count(anchor) == 1:
                        after = after.replace(LEGACY_DISCONNECT, b"", 1).replace(
                            anchor, LEGACY_DISCONNECT + anchor, 1)
                after = after.replace(b"    const point = points[index]!;\n",
                                      b"    const point = points[index];\n")
                if after != before:
                    path.write_bytes(after)
                    staged_upgrade = True
            if APPEARANCE_LAYOUT_TEMPLATE in targets:
                path = staged_source / APPEARANCE_LAYOUT_TEMPLATE
                before = path.read_bytes()
                if before.count(LEGACY_SURFACE_LABEL) == 1:
                    path.write_bytes(before.replace(LEGACY_SURFACE_LABEL, SURFACE_LABEL, 1))
                    staged_upgrade = True
            for target in APPEARANCE_SNAPSHOT_SOURCES:
                if target not in targets:
                    continue
                path = staged_source / target
                before = path.read_bytes()
                if before.count(LEGACY_SNAPSHOT_SIGNATURE) == 1:
                    path.write_bytes(before.replace(
                        LEGACY_SNAPSHOT_SIGNATURE, SNAPSHOT_SIGNATURE, 1))
                    staged_upgrade = True
            if APPEARANCE_FRAME_SOURCE in targets:
                path = staged_source / APPEARANCE_FRAME_SOURCE
                before = path.read_bytes()
                if before.count(LEGACY_FRAME_GRADIENT) == 1:
                    path.write_bytes(before.replace(LEGACY_FRAME_GRADIENT, FRAME_GRADIENT, 1))
                    staged_upgrade = True
            if APPEARANCE_CUSTOMIZE_UI_SOURCE in targets:
                path = staged_source / APPEARANCE_CUSTOMIZE_UI_SOURCE
                before = path.read_bytes()
                after = before
                if after.count(LEGACY_SETTINGS_STRINGS_INCLUDE) == 1:
                    after = after.replace(LEGACY_SETTINGS_STRINGS_INCLUDE, b"", 1)
                elif after.count(LEGACY_SETTINGS_STRINGS_INCLUDE) > 1:
                    raise RuntimeError("Ambiguous legacy settings_strings.h includes. No changes made.")
                if after.count(LEGACY_CLOSE_WORKSPACE_STRING) == 1:
                    after = after.replace(LEGACY_CLOSE_WORKSPACE_STRING, CLOSE_WORKSPACE_STRING, 1)
                if after != before:
                    path.write_bytes(after)
                    staged_upgrade = True
            if APPEARANCE_CAPTURE_SOURCE in targets:
                path = staged_source / APPEARANCE_CAPTURE_SOURCE
                before = path.read_bytes()
                if before.count(LEGACY_WINDOW_TYPE_CHECK) == 1:
                    path.write_bytes(before.replace(LEGACY_WINDOW_TYPE_CHECK, WINDOW_TYPE_CHECK, 1))
                    staged_upgrade = True
            if APPEARANCE_COLOR_PICKER_SOURCE in targets:
                path = staged_source / APPEARANCE_COLOR_PICKER_SOURCE
                before = path.read_bytes()
                if before.count(LEGACY_DARK_COLOR_CHECK) == 2:
                    path.write_bytes(before.replace(LEGACY_DARK_COLOR_CHECK, DARK_COLOR_CHECK))
                    staged_upgrade = True
            if staged_upgrade:
                corrected = git_apply(staged_source, staged_patch,
                                      reverse=True, check=True)
                # The complete native/UI catalog must be present. Known old
                # snippets alone never authorize changes to an unknown tree.
                if corrected.returncode == 0:
                    backward = corrected
                    needs_upgrade = True
                else:
                    raise RuntimeError(
                        "Legacy appearance source was found, but the complete appearance "
                        "catalog could not be verified. No changes made.\n" +
                        corrected.stderr.replace(staged_source.as_posix() + "/", ""))
        if forward.returncode == 0 and backward.returncode != 0:
            status = "READY"
        elif backward.returncode == 0 and forward.returncode != 0:
            status = "UPDATE_AVAILABLE" if needs_upgrade else "APPLIED"
        else:
            def diagnostic(result: subprocess.CompletedProcess[str]) -> str:
                return result.stderr.replace(staged_source.as_posix() + "/", "").strip()

            forward_detail = diagnostic(forward)
            backward_detail = diagnostic(backward)
            forward_count = forward_detail.count("patch failed:")
            backward_count = backward_detail.count("patch failed:")
            if forward_count <= backward_count:
                details = ("Forward check:\n" + (forward_detail or "No diagnostic output") +
                           f"\nAlready-applied check also failed ({backward_count} hunk locations).")
            else:
                details = (f"Forward check failed ({forward_count} hunk locations).\n"
                           "Already-applied check:\n" + backward_detail)
            raise RuntimeError(
                f"Cannot integrate {patch.name}. No changes made.\n" + details)
        if not apply and not revert:
            return status
        desired = "READY" if revert else "APPLIED"
        if status == desired:
            return status
        if not needs_upgrade or revert:
            result = git_apply(staged_source, staged_patch, reverse=revert, check=False)
            if result.returncode:
                raise RuntimeError("Patch application failed in staging; no source "
                                   "changes made:\n" + result.stderr)
        verified = git_apply(staged_source, staged_patch, reverse=not revert, check=True)
        if verified.returncode:
            raise RuntimeError("Patch verification failed in staging; no source "
                               "changes made:\n" + verified.stderr)
        changes = {
            target: preserve_line_endings(originals[target],
                                          (staged_source / target).read_bytes()
                                          .replace(b"\r\n", b"\n"))
            for target in targets
        }
        commit_source_changes(source, originals,
                              {p: data for p, data in changes.items()
                               if data != originals[p]})
    return desired


def integrate_bundle(source: Path, *, apply: bool = False, revert: bool = False,
                     catalogs: tuple[Path, ...] | None = None) -> str:
    """Validate and commit the complete bundle as one source transaction."""
    if apply and revert:
        raise ValueError("Choose apply or revert")
    if catalogs is None:
        catalogs = (PATCH, ROOT / "patches/windows/arc-import-windows.patch",
                    PASSWORD_PATCH,
                    ROOT / "patches/windows/arc-appearance-windows.patch",
                    ONBOARDING_PATCH)
    source = source.resolve(strict=True)
    if not (source / "BUILD.gn").is_file():
        raise ValueError("Expected a prepared Chromium source root containing BUILD.gn")
    targets = sorted(set().union(*(patch_targets(p.read_text(encoding="utf-8"))
                                  for p in catalogs)))
    for target in targets:
        path = (source / target).resolve(strict=True)
        if not path.is_relative_to(source) or not path.is_file():
            raise ValueError(f"Patch target escapes the source root: {target}")
    originals = {p: (source / p).read_bytes() for p in targets}
    with tempfile.TemporaryDirectory(prefix="arcium-bundle-stage-") as temporary:
        staging = Path(temporary)
        (staging / "BUILD.gn").write_text("# Partial optional-patch fixture\n")
        for target, content in originals.items():
            path = staging / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        initial = []
        for catalog in reversed(catalogs) if revert else catalogs:
            try:
                initial.append(integrate(staging, patch=catalog))
                # Even --check rehearses the whole operation in temporary copies,
                # so a failure in the last catalog cannot partially update source.
                integrate(staging, apply=not revert, revert=revert, patch=catalog)
            except RuntimeError as error:
                raise RuntimeError(f"Bundle validation failed for {source}:\n{error}") from error
        if not apply and not revert:
            if all(status == "APPLIED" for status in initial):
                return "APPLIED"
            return "UPDATE_AVAILABLE" if "UPDATE_AVAILABLE" in initial else "READY"
        changes = {p: (staging / p).read_bytes() for p in targets
                   if (staging / p).read_bytes() != originals[p]}
        commit_source_changes(source, originals, changes)
    return "READY" if revert else "APPLIED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path,
                        default=ROOT / "work/windows-platform/build/src")
    parser.add_argument("--feature", choices=("workflow", "arc-import", "passwords", "appearance", "mac-buttons", "onboarding", "all"),
                        default="workflow", help="Optional Windows integration to apply")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Read-only applicability check (default)")
    mode.add_argument("--apply", action="store_true", help="Apply the selected integration patch")
    mode.add_argument("--revert", action="store_true", help="Undo the selected integration patch")
    args = parser.parse_args()
    try:
        catalogs = {
            "workflow": PATCH,
            "arc-import": ROOT / "patches/windows/arc-import-windows.patch",
            "passwords": PASSWORD_PATCH,
            "appearance": ROOT / "patches/windows/arc-appearance-windows.patch",
            "mac-buttons": ROOT / "patches/windows/mac-window-buttons.patch",
            "onboarding": ONBOARDING_PATCH,
        }
        if args.feature == "all":
            status = integrate_bundle(args.source_dir, apply=args.apply, revert=args.revert)
        else:
            status = integrate(args.source_dir, apply=args.apply, revert=args.revert,
                               patch=catalogs[args.feature])
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    marker = {"workflow": "ARC_WORKFLOW", "arc-import": "ARC_IMPORT",
              "passwords": "ARC_PASSWORDS", "appearance": "ARC_APPEARANCE",
              "mac-buttons": "MAC_BUTTONS",
              "onboarding": "ONBOARDING",
              "all": "ALL"}[args.feature]
    print(f"ARCIUM_WINDOWS_{marker}_{status}")
    if args.apply or args.revert:
        print("Resume the existing build to compile the changed UI. Build outputs were retained.")
    else:
        print("Read-only check. No source, build output, or profile was changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
