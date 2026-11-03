"""Compile actual new backdrop/capture logic with small API contract doubles.

This checks decisions and error paths, not native Chromium linkage or rendering.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.apply_windows_arc_workflow import ROOT
from scripts.check_patch_overlaps import select_patch_sections


def postimage(path):
    patch = (ROOT / 'patches/windows/arc-appearance-windows.patch').read_text()
    section = select_patch_sections(patch, {path})
    return '\n'.join(line[1:] for line in section.splitlines()
                     if line.startswith((' ', '+')) and not line.startswith('+++'))


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        if source[end] == '{': depth += 1
        if source[end] == '}': depth -= 1
        end += 1
    return source[start:end]


@unittest.skipUnless(shutil.which('g++') or shutil.which('c++'), 'C++ compiler required')
class WindowsAppearanceNativeContracts(unittest.TestCase):
    def compile_and_run(self, source):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cpp = root / 'contract.cc'
            binary = root / 'contract.exe'
            cpp.write_text(source)
            compiler = shutil.which('g++') or shutil.which('c++')
            result = subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra',
                                     str(cpp), '-o', str(binary)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_windows_availability_honors_os_and_accessibility(self):
        source = postimage('chrome/browser/ui/views/helium/glass_surface.cc')
        names = ['WindowsGlassAvailability ReadWindowsGlassAvailability()',
                 'WindowsGlassAvailability& WindowsGlassState()',
                 'void RefreshWindowsGlassAvailability()',
                 'bool GlassReduceTransparency()',
                 'GlassBackendAvailability GetNativeFrameGlassAvailability()']
        actual = '\n'.join(function(source, name) for name in names)
        prefix = r'''
#include <cassert>
using BOOL = int; using DWORD = unsigned long;
constexpr BOOL FALSE = 0;
constexpr int HKEY_CURRENT_USER = 0, KEY_QUERY_VALUE = 1, ERROR_SUCCESS = 0;
bool SUCCEEDED(int value) { return value >= 0; }
int composition_result = 0, read_result = 0, build = 22621;
BOOL composition_enabled = 1; DWORD transparency = 1;
int DwmIsCompositionEnabled(BOOL* value) { *value=composition_enabled;return composition_result; }
namespace base::win {
struct Version {int build;};
struct OSInfo {static OSInfo* GetInstance(){static OSInfo info;return &info;}
 Version version_number(){return {::build};}};
struct RegKey {RegKey(int,const wchar_t*,int){}
 int ReadValueDW(const wchar_t*,DWORD* value){*value=transparency;return read_result;}};
}
namespace ui {
struct ColorProviderKey {enum class ForcedColors {kNone,kActive};};
struct NativeTheme {
 enum class PreferredContrast {kNoPreference,kMore};
 ColorProviderKey::ForcedColors colors=ColorProviderKey::ForcedColors::kNone;
 PreferredContrast contrast=PreferredContrast::kNoPreference;
 static NativeTheme* GetInstanceForNativeUi(){static NativeTheme theme;return &theme;}
 auto forced_colors()const{return colors;} auto preferred_contrast()const{return contrast;}
};
}
struct WindowsGlassAvailability {bool supported=false;bool transparency_disabled=false;};
struct GlassBackendAvailability {bool native_liquid_glass=false,native_material=false,
 chromium=false,reduce_transparency=false;};
'''
        main = r'''
int main(){
 auto update=[](){RefreshWindowsGlassAvailability();return GetNativeFrameGlassAvailability();};
 assert(update().native_material && !update().reduce_transparency);
 build=22620; assert(!update().native_material);
 build=22621; composition_enabled=0; assert(!update().native_material);
 composition_enabled=1; composition_result=-1; assert(!update().native_material);
 composition_result=0; transparency=0; assert(update().reduce_transparency);
 transparency=1; assert(!update().reduce_transparency);
 read_result=-1; transparency=0; assert(!update().reduce_transparency);
 read_result=0; transparency=1;
 auto* theme=ui::NativeTheme::GetInstanceForNativeUi();
 theme->colors=ui::ColorProviderKey::ForcedColors::kActive; assert(update().reduce_transparency);
 theme->colors=ui::ColorProviderKey::ForcedColors::kNone;
 theme->contrast=ui::NativeTheme::PreferredContrast::kMore;assert(update().reduce_transparency);
}
'''
        self.compile_and_run(prefix + actual + main)

    def test_capture_uses_explicit_window_space_and_rejects_other_contexts(self):
        source = postimage('chrome/browser/ui/helium/arcium_settings_model.cc')
        actual = function(source, 'std::unique_ptr<ArciumSettingsModel> ArciumSettingsModel::CaptureForWebContents(')
        prefix = r'''
#include <cassert>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
namespace base {struct RepeatingClosure {};}
namespace helium {struct Service;}
struct Profile {
 bool private_=false,guest=false;helium::Service* service=nullptr;
 bool IsOffTheRecord(){return private_;}bool IsGuestSession(){return guest;}
 static Profile* FromBrowserContext(Profile* value){return value;}
};
struct Browser {Profile* profile=nullptr;bool normal=true;
 Profile* GetProfile(){return profile;}bool GetIsNormalType(){return normal;}};
namespace content {struct WebContents {Profile* profile=nullptr;Browser* browser=nullptr;
 Profile* GetBrowserContext(){return profile;}};}
namespace webui {Browser* GetBrowserWindowInterface(content::WebContents* value){return value->browser;}}
namespace helium {
struct Service {std::string id="window-space";bool exists=true;
 std::string_view GetExplicitSpaceIdForBrowser(Browser*){return id;}
 Service* GetSpaceById(std::string_view value){return exists && value==id?this:nullptr;}};
struct HeliumSpaceServiceFactory {static Service* GetForProfile(Profile* value){return value->service;}};
}
struct ArciumSettingsModel {
 std::string selected;
 ArciumSettingsModel(Profile*,base::RepeatingClosure,base::RepeatingClosure){}
 bool SetAppearanceSpace(std::string_view id){selected=id;return true;}
 static std::unique_ptr<ArciumSettingsModel> CaptureForWebContents(
 content::WebContents*,base::RepeatingClosure,base::RepeatingClosure);
};
'''
        main = r'''
int main(){
 helium::Service service;Profile profile;profile.service=&service;
 Browser browser{&profile,true};content::WebContents page{&profile,&browser};
 auto capture=[&](){return ArciumSettingsModel::CaptureForWebContents(&page,{},{});};
 assert(capture() && capture()->selected=="window-space");
 service.id="other-assigned-space";assert(capture()->selected=="other-assigned-space");
 service.id="";assert(!capture());service.id="window-space";
 service.exists=false;assert(!capture());service.exists=true;
 profile.private_=true;assert(!capture());profile.private_=false;
 profile.guest=true;assert(!capture());profile.guest=false;
 Profile other;browser.profile=&other;assert(!capture());browser.profile=&profile;
 browser.normal=false;assert(!capture());browser.normal=true;
 page.browser=nullptr;assert(!capture());page.browser=&browser;
 profile.service=nullptr;assert(!capture());
 assert(!ArciumSettingsModel::CaptureForWebContents(nullptr,{},{}));
}
'''
        self.compile_and_run(prefix + actual + main)

    def test_actual_backdrop_controller_keeps_opaque_fallback_on_failure(self):
        source = postimage('chrome/browser/ui/views/frame/browser_desktop_window_tree_host_win.cc')
        actual = function(source, 'void BrowserDesktopWindowTreeHostWin::UpdateArciumBackdrop()')
        prefix = r'''
#include <cassert>
#include <cstddef>
using BOOL=int;using HRESULT=int;
constexpr int DWMWA_SYSTEMBACKDROP_TYPE=38,DWMWA_USE_IMMERSIVE_DARK_MODE=20;
enum DWM_SYSTEMBACKDROP_TYPE {DWMSBT_NONE,DWMSBT_MAINWINDOW,DWMSBT_TRANSIENTWINDOW};
struct MARGINS {int left,right,top,bottom;};
int install_result=0,extend_result=0,backdrop=-1;MARGINS extended{};
bool SUCCEEDED(int value){return value>=0;}
constexpr int GWL_EXSTYLE=0,WS_EX_NOREDIRECTIONBITMAP=0x00200000;
long window_style=WS_EX_NOREDIRECTIONBITMAP;
long GetWindowLongPtr(int,int){return window_style;}
int DwmSetWindowAttribute(int,int attribute,const void* value,std::size_t){
 if(attribute==DWMWA_SYSTEMBACKDROP_TYPE){backdrop=*static_cast<const DWM_SYSTEMBACKDROP_TYPE*>(value);return install_result;}
 return 0;
}
int DwmExtendFrameIntoClientArea(int,const MARGINS* value){extended=*value;return extend_result;}
namespace ui {struct ColorProviderKey {enum class ColorMode {kDark,kLight};};}
struct Profile {bool private_=false,guest=false;bool IsOffTheRecord(){return private_;}
 bool IsGuestSession(){return guest;} int* GetPrefs(){return nullptr;}};
struct BrowserView {Profile profile;bool normal=true;
 Profile* GetProfile(){return &profile;}bool GetIsNormalType(){return normal;}};
struct Widget {auto GetColorMode(){return ui::ColorProviderKey::ColorMode::kDark;}};
struct ThemeService {bool managed=false;bool UsingPolicyTheme(){return managed;}} theme;
struct ThemeServiceFactory {static ThemeService* GetForProfile(Profile*){return &theme;}};
namespace helium {
enum class GlassSurfaceMaterial {kAuto,kFrosted,kSolid};
struct Availability {bool native_material=true;} availability;
struct Resolution {bool enabled=true,paints_chrome_transparent=true,uses_translucent_native_base=true;} resolution;
struct Configuration {GlassSurfaceMaterial material=GlassSurfaceMaterial::kAuto;} configuration;
bool ready=false;
auto GetNativeFrameGlassAvailability(){return availability;}
auto GetNativeFrameGlassResolution(BrowserView*){return resolution;}
auto ReadGlassSurfaceConfiguration(int*){return configuration;}
void SetWindowsFrameGlassReady(BrowserView*,bool value){ready=value;}
}
struct BrowserDesktopWindowTreeHostWin {
 bool arcium_widget_ready_=true; BrowserView view;Widget widget;
 BrowserView* browser_view_=&view;
 int GetHWND(){return 1;}Widget* GetWidget(){return &widget;}
 void UpdateArciumBackdrop();
};
'''
        main = r'''
int main(){
 BrowserDesktopWindowTreeHostWin host;
 auto update=[&](){helium::ready=false;host.UpdateArciumBackdrop();return helium::ready;};
 assert(update() && backdrop==DWMSBT_MAINWINDOW && extended.left==-1);
 helium::configuration.material=helium::GlassSurfaceMaterial::kFrosted;
 assert(update() && backdrop==DWMSBT_TRANSIENTWINDOW);
 install_result=-1;assert(!update() && extended.left==0);install_result=0;
 extend_result=-1;assert(!update());extend_result=0;
 helium::resolution.uses_translucent_native_base=false;
 assert(update() && backdrop==DWMSBT_NONE && extended.left==0);
 helium::resolution.enabled=false;assert(!update());helium::resolution.enabled=true;
 helium::resolution.paints_chrome_transparent=false;assert(!update());helium::resolution.paints_chrome_transparent=true;
 host.view.normal=false;assert(!update());host.view.normal=true;
 host.view.profile.private_=true;assert(!update());host.view.profile.private_=false;
 host.view.profile.guest=true;assert(!update());host.view.profile.guest=false;
 theme.managed=true;assert(!update());theme.managed=false;
 window_style=0;assert(!update());window_style=WS_EX_NOREDIRECTIONBITMAP;
 helium::availability.native_material=false;helium::ready=true;
 host.UpdateArciumBackdrop();assert(!helium::ready);
}
'''
        self.compile_and_run(prefix + actual + main)


if __name__ == '__main__':
    unittest.main()
