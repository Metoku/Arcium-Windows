"""Replay optional Windows Arc patches against the exact pinned source files.

Only a temporary, partial source fixture is created. This does not compile
Chromium, create a browser profile, or touch an existing build workspace.
Run as: python -m scripts.check_windows_arc_import_patch --core-dir PATH
"""

from __future__ import annotations

import argparse
import hashlib
import json
from itertools import permutations
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from scripts.apply_windows_arc_workflow import (
    APPEARANCE_CSS_SOURCE, APPEARANCE_HANDLER_RENAMES, APPEARANCE_LAYOUT_SOURCE,
    APPEARANCE_LAYOUT_TEMPLATE, LEGACY_SURFACE_LABEL, SURFACE_LABEL,
    APPEARANCE_SNAPSHOT_SOURCES, LEGACY_SNAPSHOT_SIGNATURE, SNAPSHOT_SIGNATURE,
    APPEARANCE_FRAME_SOURCE, LEGACY_FRAME_GRADIENT, FRAME_GRADIENT,
    APPEARANCE_CUSTOMIZE_UI_SOURCE, LEGACY_SETTINGS_STRINGS_INCLUDE,
    GENERATED_RESOURCES_INCLUDE, LEGACY_CLOSE_WORKSPACE_STRING, CLOSE_WORKSPACE_STRING,
    APPEARANCE_CAPTURE_SOURCE, LEGACY_WINDOW_TYPE_CHECK, WINDOW_TYPE_CHECK,
    APPEARANCE_COLOR_PICKER_SOURCE, LEGACY_DARK_COLOR_CHECK, DARK_COLOR_CHECK,
    LEGACY_APPEARANCE_CSS, LEGACY_DISCONNECT, PATCH, ROOT,
    appearance_css_addition, git_apply, integrate, integrate_bundle,
    patch_targets, preserve_line_endings,
    ONBOARDING_PATCH, SERVICES_PATCH,
)
from scripts.check_patch_overlaps import discover_patch_paths, download_original, select_patch_sections
from scripts.windows_port import audit_staged, chromium_version, git, read_pin, read_series
from scripts.check_windows_mac_buttons import MAC_PATCH, MAC_API_FILES, check_mac_buttons
from scripts.check_windows_onboarding import (
    ONBOARDING_ROOT, ONBOARDING_API_FILES, BRANDING_API_FILES,
    prepare_onboarding_assets, check_onboarding,
)


IMPORT_PATCH = ROOT / "patches/windows/arc-import-windows.patch"
PASSWORD_PATCH = ROOT / "patches/windows/arc-password-import-windows.patch"
APPEARANCE_PATCH = ROOT / "patches/windows/arc-appearance-windows.patch"
GENERATED_RESOURCES_GRD = "chrome/app/generated_resources.grd"
BROWSER_WINDOW_INTERFACE_HEADER = (
    "chrome/browser/ui/browser_window/public/browser_window_interface.h")
NATIVE_THEME_HEADER = "ui/native_theme/native_theme.h"
ESLINT_ASSETS = """eslint_ts.config_base.ts inline_event_handler.ts
lit_element_bindings.ts lit_element_invalid_interface.ts lit_element_structure.ts
lit_element_template_structure.ts lit_property_accessor.ts lit_reactive_properties.ts
lit_use_fire_helper.ts no_assert_equals_boolean.ts no_mixed_type_and_value_imports.ts
polymer_property_class_member.ts polymer_property_declare.ts query_utils.ts
web_component_missing_deps.ts webui_eslint_plugin.ts""".split()


def normalize_headers(diff: str) -> str:
    diff = re.sub(r"^--- (?:src\.orig|src|a)/", "--- a/", diff, flags=re.MULTILINE)
    return re.sub(r"^\+\+\+ (?:src|b)/", "+++ b/", diff, flags=re.MULTILINE)


def browser_window_type_api(text: str) -> str:
    """Extract the declarations compiled by the capture regression host."""
    query = "  virtual Type GetType() const = 0;"
    start = text.index("  enum Type {")
    end = text.index(query, start) + len(query)
    enum = "\n".join(line for line in text[start:end].splitlines()
                     if not line.lstrip().startswith("//"))
    profiles = re.findall(r'^  virtual (?:const )?Profile\* GetProfile\(\)(?: const)? = 0;',
                          text, re.MULTILINE)
    if len(profiles) != 2:
        raise RuntimeError("Unexpected BrowserWindowInterface profile query declarations")
    return enum + "\n" + "\n".join(profiles) + "\n"


def native_theme_appearance_api(text: str) -> str:
    """Extract the real enum/accessors used by both appearance compiler hosts."""
    patterns = (
        r"  enum class PreferredColorScheme \{.*?\n  \};",
        r"  enum class PreferredContrast \{.*?\n  \};",
        r"  static NativeTheme\* GetInstanceForNativeUi\(\);",
        r"  ColorProviderKey::ForcedColors forced_colors\(\) const \{.*?\}",
        r"  PreferredColorScheme preferred_color_scheme\(\) const \{.*?\}",
        r"  PreferredContrast preferred_contrast\(\) const \{.*?\}",
    )
    declarations = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        if len(matches) != 1:
            raise RuntimeError(f"Unexpected NativeTheme appearance API: {pattern}")
        declarations.append(matches[0])
    return "\n\n".join(declarations) + "\n"


def verify_appearance_resources(source: Path, targets: set[str]) -> dict:
    """Check the string producer/header/consumer relationship without GRIT mocks."""
    root = ET.parse(source / GENERATED_RESOURCES_GRD).getroot()
    headers = [node.get("filename") for node in root.iter("output")
               if node.get("type") == "rc_header"]
    if headers != ["grit/generated_resources.h"]:
        raise RuntimeError("Unexpected generated_resources GRIT header output")
    if not any(node.get("file") == "settings_strings.grdp" for node in root.iter("part")):
        raise RuntimeError("generated_resources.grd does not own settings_strings.grdp")
    owner = "chrome/" + headers[0]
    settings = ET.parse(source / "chrome/app/settings_strings.grdp").getroot()
    ids = {node.get("name") for tree in (root, settings) for node in tree.iter("message")}
    consumers = {}
    for target in sorted(targets):
        if not target.endswith((".cc", ".h")):
            continue
        text = (source / target).read_text(encoding="utf-8")
        includes = set(re.findall(r'^#include "([^\"]+)"', text, re.MULTILINE))
        if "chrome/grit/settings_strings.h" in includes:
            raise RuntimeError(f"{target}: settings_strings.h is not generated; "
                               f"settings_strings.grdp is owned by {owner}")
        references = set(re.findall(r'\bIDS_SETTINGS_ARCIUM_[A-Z0-9_]+\b', text))
        if references:
            missing = references - ids
            if missing:
                raise RuntimeError(f"{target}: undefined Settings string IDs: {sorted(missing)}")
            if owner not in includes:
                raise RuntimeError(f"{target}: missing owning header {owner}")
            consumers[target] = sorted(references)
    panel = (source / APPEARANCE_CUSTOMIZE_UI_SOURCE).read_text(encoding="utf-8")
    labels = {}
    for key in ("workspaceAppearance", "closeWorkspacePanel"):
        matches = re.findall(r'\{\s*"' + key + r'"\s*,\s*(IDS_[A-Z0-9_]+)\s*\}', panel)
        if len(matches) != 1 or matches[0] not in ids:
            raise RuntimeError(f"{APPEARANCE_CUSTOMIZE_UI_SOURCE}: unresolved panel label {key}")
        labels[key] = matches[0]
    return {"status":"GRIT_RESOURCE_OWNERSHIP_VERIFIED", "header":owner,
            "part":"settings_strings.grdp", "panel_labels":labels,
            "settings_consumers":consumers, "grit_generation_verified":False}


def check(core: Path, platform: Path | None = None,
          typescript: Path | None = None,
          onboarding_archive: Path | None = None) -> dict:
    expected = read_pin("arcium-core.sha")
    if git("-C", core, "rev-parse", "HEAD") != expected:
        raise ValueError("The Arc import fixture requires the pinned Arcium core revision")
    patches = read_series(core / "patches/series")
    if platform is not None:
        audit_staged(platform)
        patches += read_series(platform / "patches/series")
    catalogs = (PATCH, IMPORT_PATCH, PASSWORD_PATCH, APPEARANCE_PATCH)
    targets = set().union(*(patch_targets(p.read_text(encoding="utf-8")) for p in catalogs))
    # Reconstruct the resource owner and browser API with shared/platform overlays.
    # These are read-only checks, outside the catalogs' 43 write targets.
    replay_targets = targets | {
        GENERATED_RESOURCES_GRD, BROWSER_WINDOW_INTERFACE_HEADER, NATIVE_THEME_HEADER}
    mac_targets = set(patch_targets(MAC_PATCH.read_text(encoding="utf-8")))
    replay_targets |= mac_targets | set(MAC_API_FILES)
    all_paths, created = discover_patch_paths(patches)
    onboarding_targets = (set(patch_targets(ONBOARDING_PATCH.read_text(encoding="utf-8"))) |
                          set(patch_targets(SERVICES_PATCH.read_text(encoding="utf-8")))
                          if platform is not None else set())
    if onboarding_targets:
        replay_targets |= onboarding_targets | set(ONBOARDING_API_FILES) | set(BRANDING_API_FILES)
        replay_targets |= {path for path in all_paths if path.startswith(ONBOARDING_ROOT + "/")}
    original_hashes = {}
    with tempfile.TemporaryDirectory(prefix="arcium-arc-import-replay-") as temporary:
        # Windows TEMP may use RUNNER~1 while Node resolves its modules through
        # the long account name. Vite's root and module paths must agree.
        temporary = Path(temporary).resolve()
        source = temporary / "src"
        source.mkdir()
        # This marker satisfies the helper's source-root check; the fixture
        # contains only selected files and is deliberately not a build tree.
        (source / "BUILD.gn").write_text("# Partial patch replay fixture; not buildable.\n")
        onboarding_assets = (prepare_onboarding_assets(core, source, onboarding_archive)
                             if onboarding_targets else None)
        for target in sorted(replay_targets - created):
            if target.startswith(ONBOARDING_ROOT + "/"):
                # Sources and tools came from the SHA256-verified release.
                if not (source / target).is_file():
                    raise RuntimeError(f"Missing pinned onboarding asset: {target}")
                continue
            original_hashes[target] = download_original(
                chromium_version(), target, source / target, mirror_first=True)
        replayed = []
        selected_patch = temporary / "selected.patch"
        for patch in patches:
            selected = select_patch_sections(patch.read_text(encoding="utf-8"), replay_targets)
            if not selected:
                continue
            selected_patch.write_text(normalize_headers(selected), encoding="utf-8", newline="\n")
            result = git_apply(source, selected_patch, reverse=False, check=False)
            if result.returncode:
                raise RuntimeError(f"Pinned source replay failed at {patch}:\n{result.stderr}")
            replayed.append(patch.name)
        browser_header = source / BROWSER_WINDOW_INTERFACE_HEADER
        browser_api_fixture = ROOT / "tests/fixtures/browser_window_interface_type.h"
        if browser_window_type_api(browser_header.read_text(encoding="utf-8")) != browser_window_type_api(
                browser_api_fixture.read_text(encoding="utf-8")):
            raise RuntimeError("Pinned BrowserWindowInterface API differs from the capture compiler fixture")
        browser_api_sha256 = hashlib.sha256(browser_header.read_bytes()).hexdigest()
        native_theme_header = source / NATIVE_THEME_HEADER
        native_theme_fixture = ROOT / "tests/fixtures/native_theme_appearance.h"
        if native_theme_appearance_api(native_theme_header.read_text(encoding="utf-8")) != native_theme_appearance_api(
                native_theme_fixture.read_text(encoding="utf-8")):
            raise RuntimeError("Pinned NativeTheme API differs from the appearance compiler fixture")
        native_theme_sha256 = hashlib.sha256(native_theme_header.read_bytes()).hexdigest()
        originals = {target: (source / target).read_bytes() for target in targets}
        mac_originals = {target:(source / target).read_bytes() for target in mac_targets}
        onboarding_originals = {target:(source / target).read_bytes()
                                for target in onboarding_targets}
        sentinel = source / "out/Default/retained.obj"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_bytes(b"existing compiled output")
        sentinel_time = sentinel.stat().st_mtime_ns
        checks = []
        webui_report = None
        resource_report = None
        legacy_css_upgrade_checked = False
        legacy_ui_upgrades = []
        paint_api = temporary / "paint_shader.h"
        paint_api_sha256 = download_original(chromium_version(), "cc/paint/paint_shader.h",
                                             paint_api, mirror_first=True)
        def radial_declaration(text):
            start = text.index("  static sk_sp<PaintShader> MakeRadialGradient(")
            return text[start:text.index(";", start) + 1]
        expected_api = (ROOT / "tests/fixtures/paint_shader_radial_gradient.h").read_text(encoding="utf-8")
        if radial_declaration(paint_api.read_text(encoding="utf-8")) != radial_declaration(expected_api):
            raise RuntimeError("Pinned PaintShader API differs from the compiled regression fixture")
        lint_config = temporary / "stylelint.config_base.mjs"
        eslint_dir = temporary / "eslint"
        tsconfig_base = temporary / "tsconfig_base.json"
        if typescript is not None:
            download_original(chromium_version(),
                "ui/webui/resources/tools/stylelint.config_base.mjs", lint_config,
                mirror_first=True)
            download_original(chromium_version(), "tools/typescript/tsconfig_base.json",
                              tsconfig_base, mirror_first=True)
            for asset in ESLINT_ASSETS:
                download_original(chromium_version(),
                    "ui/webui/resources/tools/eslint/" + asset,
                    eslint_dir / asset, mirror_first=True)
        for style in ("LF", "CRLF", "mixed", "missing-final-newline"):
            for index, (target, data) in enumerate(sorted(originals.items())):
                normalized = data.replace(b"\r\n", b"\n")
                if style == "CRLF" or (style == "mixed" and index % 2):
                    normalized = normalized.replace(b"\n", b"\r\n")
                if style == "missing-final-newline":
                    normalized = normalized.removesuffix(b"\n")
                (source / target).write_bytes(normalized)
            baseline = {target: (source / target).read_bytes() for target in targets}
            for order in permutations(catalogs):
                for catalog in order:
                    before = {target: (source / target).stat().st_mtime_ns for target in targets}
                    if integrate(source, patch=catalog) != "READY":
                        raise RuntimeError(f"Fresh {catalog.name} was not ready")
                    if before != {target: (source / target).stat().st_mtime_ns for target in targets}:
                        raise RuntimeError("Read-only applicability check touched source timestamps")
                    if integrate(source, apply=True, patch=catalog) != "APPLIED":
                        raise RuntimeError(f"Could not apply {catalog.name}")
                if not legacy_css_upgrade_checked:
                    css = source / APPEARANCE_CSS_SOURCE
                    corrected_css = css.read_bytes()
                    fixed_block = appearance_css_addition(APPEARANCE_PATCH.read_bytes())
                    if corrected_css.count(fixed_block) != 1:
                        raise RuntimeError("Expected exactly one corrected appearance CSS block")
                    css.write_bytes(corrected_css.replace(fixed_block, LEGACY_APPEARANCE_CSS, 1))
                    upgrade_times = {target: (source / target).stat().st_mtime_ns for target in targets}
                    if integrate(source, patch=APPEARANCE_PATCH) != "UPDATE_AVAILABLE":
                        raise RuntimeError("Legacy appearance CSS was not recognized")
                    if upgrade_times != {target: (source / target).stat().st_mtime_ns for target in targets}:
                        raise RuntimeError("CSS upgrade check rewrote source")
                    integrate(source, patch=APPEARANCE_PATCH, apply=True)
                    if css.read_bytes() != corrected_css:
                        raise RuntimeError("Legacy CSS did not upgrade to the corrected block")
                    if any((source / target).stat().st_mtime_ns != stamp
                           for target, stamp in upgrade_times.items()
                           if target != APPEARANCE_CSS_SOURCE):
                        raise RuntimeError("CSS upgrade changed unrelated source")
                    legacy_css_upgrade_checked = True
                if not any(entry["endings"] == style for entry in legacy_ui_upgrades):
                    current = {target: (source / target).read_bytes() for target in targets}
                    allowed = {stem + suffix for stem in APPEARANCE_HANDLER_RENAMES
                               for suffix in (".ts", ".html.ts")} | set(APPEARANCE_SNAPSHOT_SOURCES) | {
                                   APPEARANCE_FRAME_SOURCE, APPEARANCE_CUSTOMIZE_UI_SOURCE,
                                   APPEARANCE_CAPTURE_SOURCE, APPEARANCE_COLOR_PICKER_SOURCE}
                    for previous_version in ("original", "css-corrected", "handlers-corrected",
                                             "surface-label-corrected", "snapshot-corrected", "gradient-corrected",
                                             "resources-corrected", "window-type-corrected"):
                        compact_css = previous_version == "original"
                        old = dict(current)
                        if previous_version in ("original", "css-corrected"):
                            for stem, renames in APPEARANCE_HANDLER_RENAMES.items():
                                for suffix in (".ts", ".html.ts"):
                                    name = stem + suffix
                                    normalized = old[name].replace(b"\r\n", b"\n")
                                    for previous, corrected in renames.items():
                                        normalized = normalized.replace(corrected.encode(), previous.encode())
                                    old[name] = preserve_line_endings(old[name], normalized)
                            name = APPEARANCE_LAYOUT_SOURCE
                            normalized = old[name].replace(b"\r\n", b"\n")
                            anchor = b"  private async saveWorkspace_"
                            normalized = normalized.replace(LEGACY_DISCONNECT, b"", 1).replace(
                                anchor, LEGACY_DISCONNECT + anchor, 1).replace(
                                b"    const point = points[index];", b"    const point = points[index]!;")
                            old[name] = preserve_line_endings(old[name], normalized)
                        name = APPEARANCE_LAYOUT_TEMPLATE
                        if old[name].count(SURFACE_LABEL) != 1:
                            raise RuntimeError("Expected exactly one corrected surface label")
                        if previous_version in ("original", "css-corrected", "handlers-corrected"):
                            old[name] = old[name].replace(SURFACE_LABEL, LEGACY_SURFACE_LABEL, 1)
                        if previous_version not in ("snapshot-corrected", "gradient-corrected", "resources-corrected",
                                                    "window-type-corrected"):
                            for name in APPEARANCE_SNAPSHOT_SOURCES:
                                if name.endswith(".h"):
                                    fixed = SNAPSHOT_SIGNATURE + b";"
                                    legacy = LEGACY_SNAPSHOT_SIGNATURE + b";"
                                else:
                                    fixed = b"AppearanceHandler::" + SNAPSHOT_SIGNATURE + b" {"
                                    legacy = b"AppearanceHandler::" + LEGACY_SNAPSHOT_SIGNATURE + b" {"
                                if old[name].count(fixed) != 1:
                                    raise RuntimeError("Expected exactly one snapshot signature")
                                old[name] = old[name].replace(fixed, legacy, 1)
                        if previous_version not in ("gradient-corrected", "resources-corrected", "window-type-corrected"):
                            name = APPEARANCE_FRAME_SOURCE
                            normalized = old[name].replace(b"\r\n", b"\n")
                            if normalized.count(FRAME_GRADIENT) != 1:
                                raise RuntimeError("Expected exactly one corrected frame gradient")
                            old[name] = preserve_line_endings(old[name], normalized.replace(
                                FRAME_GRADIENT, LEGACY_FRAME_GRADIENT, 1))
                        if previous_version not in ("resources-corrected", "window-type-corrected"):
                            name = APPEARANCE_CUSTOMIZE_UI_SOURCE
                            normalized = old[name].replace(b"\r\n", b"\n")
                            if (normalized.count(GENERATED_RESOURCES_INCLUDE) != 1
                                    or normalized.count(CLOSE_WORKSPACE_STRING) != 1):
                                raise RuntimeError("Expected corrected panel resource bindings")
                            normalized = normalized.replace(GENERATED_RESOURCES_INCLUDE,
                                GENERATED_RESOURCES_INCLUDE + LEGACY_SETTINGS_STRINGS_INCLUDE, 1).replace(
                                CLOSE_WORKSPACE_STRING, LEGACY_CLOSE_WORKSPACE_STRING, 1)
                            old[name] = preserve_line_endings(old[name], normalized)
                        name = APPEARANCE_CAPTURE_SOURCE
                        if old[name].count(WINDOW_TYPE_CHECK) != 1:
                            raise RuntimeError("Expected corrected capture window-type query")
                        if previous_version != "window-type-corrected":
                            old[name] = old[name].replace(WINDOW_TYPE_CHECK, LEGACY_WINDOW_TYPE_CHECK, 1)
                        name = APPEARANCE_COLOR_PICKER_SOURCE
                        normalized = old[name].replace(b"\r\n", b"\n")
                        if normalized.count(DARK_COLOR_CHECK) != 2:
                            raise RuntimeError("Expected both corrected NativeTheme color-scheme queries")
                        old[name] = preserve_line_endings(old[name], normalized.replace(
                            DARK_COLOR_CHECK, LEGACY_DARK_COLOR_CHECK))
                        if compact_css:
                            name = APPEARANCE_CSS_SOURCE
                            normalized = old[name].replace(b"\r\n", b"\n")
                            if not normalized.endswith(b"\n"):
                                normalized += b"\n"
                            normalized = normalized.replace(
                                appearance_css_addition(APPEARANCE_PATCH.read_bytes()),
                                LEGACY_APPEARANCE_CSS, 1)
                            old[name] = preserve_line_endings(old[name], normalized)
                        for target in targets:
                            if old[target] != current[target]:
                                (source / target).write_bytes(old[target])
                        timestamps = {target: (source / target).stat().st_mtime_ns for target in targets}
                        if integrate_bundle(source, catalogs=catalogs) != "UPDATE_AVAILABLE":
                            raise RuntimeError("Previously installed WebUI catalog was not recognized")
                        if timestamps != {target: (source / target).stat().st_mtime_ns for target in targets}:
                            raise RuntimeError("WebUI upgrade check rewrote source")
                        integrate_bundle(source, apply=True, catalogs=catalogs)
                        if any((source / target).read_bytes() != current[target] for target in targets):
                            raise RuntimeError("Installed WebUI catalog did not upgrade exactly")
                        if any((source / target).stat().st_mtime_ns != stamp
                               for target, stamp in timestamps.items()
                               if target not in allowed | {APPEARANCE_CSS_SOURCE}):
                            raise RuntimeError("WebUI upgrade rewrote unrelated source")
                        legacy_ui_upgrades.append({"endings":style, "previous_version":previous_version})
                ET.parse(source / "chrome/app/settings_strings.grdp")
                if resource_report is None:
                    resource_report = verify_appearance_resources(source, targets)
                    panel = source / APPEARANCE_CUSTOMIZE_UI_SOURCE
                    corrected = panel.read_bytes()
                    panel.write_bytes(corrected.replace(GENERATED_RESOURCES_INCLUDE,
                        GENERATED_RESOURCES_INCLUDE + LEGACY_SETTINGS_STRINGS_INCLUDE, 1))
                    try:
                        try:
                            verify_appearance_resources(source, targets)
                        except RuntimeError as error:
                            if "settings_strings.h is not generated" not in str(error):
                                raise
                        else:
                            raise RuntimeError("Resource checker accepted the reported invalid include")
                    finally:
                        panel.write_bytes(corrected)
                    resource_report["reported_invalid_include_rejected"] = True
                if typescript is not None and webui_report is None:
                    result = subprocess.run(
                        ["node", str(ROOT / "scripts/check_windows_appearance_ui.cjs"),
                         "--source-dir", str(source), "--typescript", str(typescript.resolve()),
                         "--eslint-dir", str(eslint_dir), "--tsconfig-base", str(tsconfig_base)],
                        text=True, encoding="utf-8", capture_output=True)
                    if result.returncode:
                        raise RuntimeError("Appearance WebUI checks failed:\n" +
                                           result.stdout + result.stderr)
                    webui_report = json.loads(result.stdout)
                    css_result = subprocess.run(
                        ["node", str(ROOT / "scripts/check_windows_appearance_css.cjs"),
                         "--source-dir", str(source), "--config", str(lint_config),
                         "--node-modules", str(typescript.resolve().parent)],
                        text=True, encoding="utf-8", capture_output=True)
                    if css_result.returncode:
                        raise RuntimeError("Chromium appearance CSS lint failed:\n" +
                                           css_result.stdout + css_result.stderr)
                    webui_report["css_lint"] = json.loads(css_result.stdout)
                    lint_result = subprocess.run(
                        ["node", str(ROOT / "scripts/check_windows_webui_lint.cjs"),
                         "--source-dir", str(source), "--rules-dir", str(eslint_dir),
                         "--node-modules", str(typescript.resolve().parent)],
                        text=True, encoding="utf-8", capture_output=True)
                    if lint_result.returncode:
                        raise RuntimeError("Chromium WebUI lint checks failed:\n" +
                                           lint_result.stdout + lint_result.stderr)
                    webui_report["scoped_webui_lint"] = json.loads(lint_result.stdout)
                applied_times = {target: (source / target).stat().st_mtime_ns for target in targets}
                applied_hashes = {target: hashlib.sha256((source / target).read_bytes()).hexdigest()
                                  for target in targets}
                for catalog in catalogs:
                    if integrate(source, apply=True, patch=catalog) != "APPLIED":
                        raise RuntimeError("Optional patches do not coexist")
                if applied_times != {target: (source / target).stat().st_mtime_ns for target in targets}:
                    raise RuntimeError("Repeated application rewrote source files")
                for catalog in reversed(order):
                    if integrate(source, revert=True, patch=catalog) != "READY":
                        raise RuntimeError(f"Could not revert {catalog.name}")
                if any((source / target).read_bytes() != data for target, data in baseline.items()):
                    raise RuntimeError("Reversion did not restore exact source bytes")
                if (sentinel.read_bytes() != b"existing compiled output" or
                        sentinel.stat().st_mtime_ns != sentinel_time):
                    raise RuntimeError("The helper changed retained compilation output")
                checks.append({"source_endings": style,
                               "order": [p.name for p in order],
                               "applied_sha256": applied_hashes})
        mac_report = check_mac_buttons(source, originals | mac_originals, catalogs)
        onboarding_report = (check_onboarding(
            source, originals | mac_originals | onboarding_originals,
            catalogs, onboarding_assets, core) if onboarding_targets else None)
        if (sentinel.read_bytes() != b"existing compiled output" or
                sentinel.stat().st_mtime_ns != sentinel_time):
            raise RuntimeError("The Mac caption helper changed retained compilation output")
        return {"status": "PATCH_REPLAY_VERIFIED_NOT_COMPILED",
                "arcium_core": expected, "chromium_version": chromium_version(),
                "windows_platform_replayed": platform is not None,
                "targets": sorted(targets), "original_sha256": original_hashes,
                "upstream_patch_sections": len(replayed), "checks": checks,
                "paint_shader_api_sha256": paint_api_sha256, "paint_shader_radial_signature_verified": True,
                "browser_window_api_sha256": browser_api_sha256,
                "browser_window_type_api_verified": True,
                "native_theme_api_sha256": native_theme_sha256,
                "native_theme_appearance_api_verified": True,
                "build_output_preserved": True, "legacy_css_upgrade_verified": legacy_css_upgrade_checked,
                "legacy_webui_upgrades": legacy_ui_upgrades,
                "resource_bindings":resource_report, "browser_compiled": False,
                "mac_window_buttons":mac_report,
                "windows_onboarding":onboarding_report,
                "browser_launch_verified": False, "appearance_webui": webui_report}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-dir", type=Path, required=True)
    parser.add_argument("--platform-dir", type=Path)
    parser.add_argument("--typescript", type=Path,
                        help="TypeScript module for optional isolated appearance WebUI checks")
    parser.add_argument("--onboarding-archive", type=Path,
                        help="Optional cached onboarding release; its pinned SHA256 is always checked")
    parser.add_argument("--report", type=Path, default=ROOT / "work/windows-arc-import-replay.json")
    args = parser.parse_args()
    report = check(args.core_dir.resolve(),
                   args.platform_dir.resolve() if args.platform_dir else None,
                   args.typescript, args.onboarding_archive)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"ARCIUM_WINDOWS_ARC_IMPORT_PATCH_REPLAY_PASSED: {len(report['targets'])} targets; "
          f"{len(report['checks'])} apply/revert combinations. C++ compilation and UI testing pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
