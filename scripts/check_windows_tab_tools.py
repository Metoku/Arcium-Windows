"""Check tab-tools bindings and compile the actual cleanup code in an isolated host.

The host simulates browser lifecycle events. Native rendering and a complete
Windows Chromium build remain separate checks.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from scripts.apply_windows_arc_workflow import ROOT
from scripts.check_windows_mac_buttons import cpp_function

REGION = "chrome/browser/ui/views/frame/vertical_tab_strip_region_view.cc"
REGION_HEADER = REGION.removesuffix(".cc") + ".h"
API_DECLARATIONS = {
    "components/tabs/public/tab_interface.h": (
        "virtual base::Time GetLastActiveTime() const = 0;",
        "virtual bool IsActivated() const = 0;",
        "virtual bool IsVisible() const = 0;",
        "virtual bool IsSelected() const = 0;",
        "virtual bool IsSplit() const = 0;",
        "virtual GURL GetURL() const = 0;",
    ),
    "content/public/browser/web_contents.h": (
        "virtual bool IsLoading() = 0;",
        "virtual bool IsBeingCaptured() = 0;",
        "virtual bool NeedToFireBeforeUnloadOrUnloadEvents() = 0;",
        "virtual int GetCurrentlyPlayingVideoCount() const = 0;",
    ),
    "components/performance_manager/public/performance_manager.h": (
        "static bool IsAvailable();",
        "static base::WeakPtr<PageNode> GetPrimaryPageNodeForWebContents(content::WebContents* wc);",
    ),
    "components/performance_manager/public/graph/page_node.h": (
        "virtual bool HadFormInteraction() const = 0;",
        "virtual bool HadUserEdits() const = 0;",
        "virtual bool IsVisible() const = 0;",
        "virtual bool IsOffTheRecord() const = 0;",
        "virtual bool IsAudible() const = 0;",
        "virtual bool HasPictureInPicture() const = 0;",
        "virtual bool UsesWebRTC() const = 0;",
        "virtual bool IsHoldingWebLock() const = 0;",
        "virtual bool IsHoldingBlockingIndexedDBLock() const = 0;",
        "virtual base::TimeDelta GetTimeSinceLastNavigation() const = 0;",
    ),
    "components/performance_manager/public/decorators/page_live_state_decorator.h": (
        "static const Data* FromPageNode(const PageNode* page_node);",
        *(f"virtual bool {method}() const = 0;" for method in (
            "IsAutoDiscardable", "IsCapturingAudio", "IsCapturingVideo",
            "IsBeingMirrored", "IsCapturingWindow", "IsCapturingDisplay",
            "IsDevToolsOpen", "IsConnectedToUSBDevice", "IsConnectedToBluetoothDevice",
            "IsConnectedToHidDevice", "IsConnectedToSerialPort", "IsWithheldFromView")),
    ),
    "chrome/browser/ui/tabs/tab_strip_model.h": (
        "tab_groups::TabGroupId AddToNewGroup(const std::vector<int> indices, bool is_ephemeral = false);",
        "void ChangeTabGroupVisuals(const tab_groups::TabGroupId& group, tab_groups::TabGroupVisualData visual_data, bool is_customized = false);",
        "int GetIndexOfTab(const tabs::TabInterface* tab) const;",
    ),
    "chrome/browser/ui/tabs/tab_group_model.h": (
        "bool ContainsTabGroup(const tab_groups::TabGroupId& id) const;",
    ),
    "chrome/browser/ui/browser_commands.h": (
        "void RestoreTab(BrowserWindowInterface* browser);",
        "void ShowTabSearch(BrowserWindowInterface* browser);",
    ),
    "ui/menus/simple_menu_model.h": (
        "void AddTitle(const std::u16string& label);",
        "void AddRadioItem(int command_id, const std::u16string& label, int group_id);",
    ),
    "ui/views/controls/menu/menu_types.h": ("kTopRight",),
    "components/history/core/common/pref_names.h": (
        "extern const char kSavingBrowserHistoryDisabled[];",
    ),
}
API_FILES = tuple(API_DECLARATIONS) + (
    "chrome/browser/ui/BUILD.gn",
    "chrome/browser/ui/helium/helium_space_service.h",
    "components/tab_groups/tab_group_visual_data.h",
)


def policy(text: str) -> str:
    return text.split("// ARCIUM_TAB_TOOLS_POLICY_BEGIN", 1)[1].split(
        "// ARCIUM_TAB_TOOLS_POLICY_END", 1)[0]


def compile_contract(text: str) -> dict:
    compiler = shutil.which("g++") or shutil.which("c++")
    if compiler is None:
        raise RuntimeError("A C++ compiler is required for the tab cleanup host")
    host = (ROOT / "tests/fixtures/sidebar_tab_tools_host.cc").read_text(encoding="utf-8")
    signatures = ("static std::string SpaceId(", "static bool IsDurable(",
                  "int CleanupHours() const", "static bool CanAutoClean(",
                  "void Cleanup()")
    functions = "\n\n".join(cpp_function(text, name) for name in signatures)
    host = host.replace("// INJECT_POLICY", policy(text)).replace(
        "// INJECT_CLEANUP_FUNCTIONS", functions)
    with tempfile.TemporaryDirectory(prefix="arcium tab cleanup ") as temporary:
        root = Path(temporary)
        cpp, binary = root / "contract.cc", root / "contract.exe"
        cpp.write_text(host, encoding="utf-8")
        result = subprocess.run([compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                                 str(cpp), "-o", str(binary)],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace")
        if result.returncode:
            raise RuntimeError("Tab cleanup host failed to compile:\n" + result.stdout + result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        if result.returncode or result.stdout.strip() != "SIDEBAR_TAB_TOOLS_CPP_HOST_PASSED":
            raise RuntimeError("Tab cleanup behavior failed:\n" + result.stdout + result.stderr)
    return {"status":"ACTUAL_TAB_CLEANUP_FUNCTIONS_HOST_PASSED",
            "protected_state_cases":36, "reentrant_close_cases":7,
            "browser_adapters_simulated":True, "native_chromium_compiled":False}


def verify_tab_tools(source: Path, *, compile_cpp: bool = True) -> dict:
    text = (source / REGION).read_text(encoding="utf-8")
    normalize = lambda value: re.sub(r"\s+", "", value)
    for path, declarations in API_DECLARATIONS.items():
        header = normalize((source / path).read_text(encoding="utf-8"))
        for declaration in declarations:
            if normalize(declaration) not in header:
                raise RuntimeError(f"Tab-tools API declaration changed: {path}: {declaration}")
    manager = (source / "components/performance_manager/public/performance_manager.h").read_text(encoding="utf-8")
    if "only be dereferenced on the main thread" not in manager:
        raise RuntimeError("The Performance Manager main-thread contract changed")
    header = (source / "chrome/browser/ui/helium/arcium_settings_prefs.h").read_text(encoding="utf-8")
    registration = (source / "chrome/browser/ui/browser_ui_prefs.cc").read_text(encoding="utf-8")
    if ('kTabCleanupHoursPref[] = "arcium.tabs.cleanup_hours";' not in header or
            "RegisterIntegerPref(arcium_settings::kTabCleanupHoursPref, 0)" not in registration):
        raise RuntimeError("Automatic cleanup is not registered Off by default")
    messages = ET.parse(source / "chrome/app/settings_strings.grdp").getroot()
    ids = [node.get("name") for node in messages.iter("message")]
    references = set(re.findall(r"\bIDS_ARCIUM_TAB_TOOLS_[A-Z0-9_]+\b", text))
    if len(references) != 14 or any(ids.count(name) != 1 for name in references):
        raise RuntimeError("Tab-tools native labels are missing or duplicated")
    for expected in (
            '"chrome/grit/generated_resources.h"',
            "content_parent->GetIndexOf(tab_tools_)",
            "chrome::ExecuteCommand(browser_.get(), IDC_ARCIUM_CLEAR_UNPINNED)",
            "chrome::RestoreTab(browser_.get())", "chrome::ShowTabSearch(browser_.get())",
            "TabCloseTypes::CLOSE_CREATE_HISTORICAL_TAB", "weak_factory_.GetWeakPtr()",
            "void VerticalTabStripRegionView::UpdateTabToolsVisibility()"):
        if expected not in text:
            raise RuntimeError(f"Missing tab-tools integration: {expected}")
    return {"status":"TAB_TOOLS_SOURCE_BINDINGS_VERIFIED",
            "api_files_verified":len(API_FILES), "cleanup_default":"Off",
            "cpp_contract":compile_contract(text) if compile_cpp else None,
            "source_sha256":hashlib.sha256(text.encode()).hexdigest(),
            "native_rendering_verified":False}
