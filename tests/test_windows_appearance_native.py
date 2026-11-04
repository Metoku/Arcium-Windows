"""Compile actual new backdrop/capture logic with small API contract doubles.

This checks decisions and error paths, not native Chromium linkage or rendering.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from scripts.apply_windows_arc_workflow import FRAME_GRADIENT, LEGACY_FRAME_GRADIENT, ROOT
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
    def compile_and_run(self, source, rejected_source=None, rejected_diagnostic='web_ui'):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cpp = root / 'contract.cc'
            binary = root / 'contract.exe'
            cpp.write_text(source)
            compiler = shutil.which('g++') or shutil.which('c++')
            if rejected_source is not None:
                cpp.write_text(rejected_source)
                rejected = subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra',
                                           str(cpp), '-o', str(binary)],
                                          capture_output=True, text=True)
                self.assertNotEqual(rejected.returncode, 0,
                                    'The previously reported source must fail compilation')
                self.assertIn(rejected_diagnostic, rejected.stderr)
                cpp.write_text(source)
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

    def test_snapshot_declaration_and_body_use_nonconst_webui_accessor(self):
        source = postimage('chrome/browser/ui/webui/settings/appearance_handler.cc')
        header = postimage('chrome/browser/ui/webui/settings/appearance_handler.h')
        declaration = re.search(
            r'base::DictValue ArciumAppearanceSnapshot\(\)(?: const)?;', header).group()
        actual = function(source, 'base::DictValue AppearanceHandler::ArciumAppearanceSnapshot()')
        # Compile the actual preference table as well as the snapshot method.
        table_start = source.index('struct WorkspacePreference {')
        table_end = source.index('};', source.index('kWorkspacePreferences[]', table_start)) + 2
        table = source[table_start:table_end]
        prefix = r'''
#include <cassert>
#include <map>
#include <memory>
#include <string>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>
namespace base {
using Scalar = std::variant<bool, int, std::string>;
struct Value {
 Scalar scalar;
 Value(bool value):scalar(value){} Value(int value):scalar(value){}
};
struct DictValue {
 std::map<std::string, Scalar> values;
 template<typename T> DictValue& Set(const char* key, T value) {
  using U = std::decay_t<T>;
  if constexpr (std::is_same_v<U, Value>) values.insert_or_assign(key,value.scalar);
  else if constexpr (std::is_same_v<U, bool> || std::is_same_v<U, int> || std::is_same_v<U, std::string>)
   values.insert_or_assign(key,value);
  return *this;
 }
 bool boolean(const char* key) const {return std::get<bool>(values.at(key));}
 std::string text(const char* key) const {return std::get<std::string>(values.at(key));}
};
struct ListValue {template<typename T> void Append(T){}};
std::string UTF16ToUTF8(const std::u16string& value) {return {value.begin(),value.end()};}
}
namespace arcium {
constexpr char kChromeFrameBorderWidthPref[]="frameWidth",kChromeUIScalePref[]="scale",
 kCollapsedSidebarStylePref[]="collapseStyle",kArcSidebarNavigationEnabledPref[]="sidebarNavigation";
}
namespace prefs {constexpr char kHeliumRoundedFrame[]="roundedFrame";}
struct Space {
 std::string id()const{return "assigned-space";}
 std::u16string name()const{return u"Assigned Space";}
};
struct SpaceInfo {std::string id;std::u16string name;};
struct Model {
 bool enabled=true,exists=true,managed=false;Space space;
 bool available()const{return enabled;}
 Space* GetAppearanceSpace(){return exists?&space:nullptr;}
 std::vector<SpaceInfo> GetSpaces(){return {{"assigned-space",u"Assigned Space"}};}
 bool GetBoolean(const char*){return true;} int GetInteger(const char*){return 100;}
 bool HasPreference(const char*){return true;} bool IsManaged(const char*){return false;}
 int GetSidebarWidth(){return 220;}bool HasSidebarWidth(){return true;}
 bool IsSidebarWidthManaged(){return false;}bool IsAppearanceManaged(){return managed;}
 base::DictValue GetChromeAppearance(){return {};}
 base::DictValue GetSpacePalette(){return {};}
 int GetAppearanceMode(){return 0;}int GetWebAppearanceMode(){return 0;}
 std::string GetSurfaceSet(){return "glass";}
 base::DictValue GetSurfaceTuning(){return {};}base::DictValue GetContentFrame(){return {};}
};
struct BrowserView;
struct Browser {BrowserView* view=nullptr;};
struct BrowserView {
 bool use_native=true,native_base=true;
 static BrowserView* GetBrowserViewForBrowser(Browser* browser){return browser->view;}
};
namespace content {
struct WebContents {Browser* browser=nullptr;};
struct WebUI {WebContents contents;WebContents* GetWebContents(){return &contents;}};
// Matches content/public/browser/web_ui_message_handler.h: web_ui() has
// no const overload. Do not make this double more permissive than Chromium.
struct WebUIMessageHandler {
 WebUI ui;int accessor_calls=0;
 WebUI* web_ui(){++accessor_calls;return &ui;}
};
}
namespace webui {
Browser* GetBrowserWindowInterface(content::WebContents* contents){return contents->browser;}
}
namespace helium {
struct Availability {bool native_material=true,reduce_transparency=false;} availability;
struct Resolution {bool uses_translucent_native_base;};
auto GetNativeFrameGlassAvailability(){return availability;}
bool ShouldUseNativeFrameGlass(BrowserView* view){return view->use_native;}
Resolution GetNativeFrameGlassResolution(BrowserView* view){return {view->native_base};}
}
namespace settings {
struct AppearanceHandler : content::WebUIMessageHandler {
 std::unique_ptr<Model> arcium_appearance_;
'''
        class_end = '\n};\n'
        suffix = r'''
}
int main(){
 settings::AppearanceHandler handler;
 assert(!handler.ArciumAppearanceSnapshot().boolean("available"));
 assert(handler.accessor_calls==0);
 handler.arcium_appearance_=std::make_unique<Model>();
 BrowserView view;Browser browser{&view};handler.ui.contents.browser=&browser;
 auto snapshot=handler.ArciumAppearanceSnapshot();
 assert(handler.accessor_calls==1 && snapshot.boolean("available"));
 assert(snapshot.text("spaceId")=="assigned-space" && snapshot.text("name")=="Assigned Space");
 assert(snapshot.boolean("windowGlassActive") && snapshot.boolean("windowGlassSupported"));
 handler.ui.contents.browser=nullptr;
 assert(!handler.ArciumAppearanceSnapshot().boolean("windowGlassActive"));
 handler.ui.contents.browser=&browser;view.native_base=false;
 assert(!handler.ArciumAppearanceSnapshot().boolean("windowGlassActive"));
 view.native_base=true;helium::availability.reduce_transparency=true;
 assert(!handler.ArciumAppearanceSnapshot().boolean("windowGlassSupported"));
 handler.arcium_appearance_->managed=true;
 assert(!handler.ArciumAppearanceSnapshot().boolean("available"));
 handler.arcium_appearance_->enabled=false;
 int calls=handler.accessor_calls;
 assert(!handler.ArciumAppearanceSnapshot().boolean("available"));
 assert(handler.accessor_calls==calls);
}
'''
        current = prefix + declaration + class_end + table + actual + suffix
        old_declaration = declaration.replace('ArciumAppearanceSnapshot();',
                                              'ArciumAppearanceSnapshot() const;')
        old_body = actual.replace('AppearanceHandler::ArciumAppearanceSnapshot() {',
                                  'AppearanceHandler::ArciumAppearanceSnapshot() const {')
        rejected = prefix + old_declaration + class_end + table + old_body + suffix
        self.compile_and_run(current, rejected_source=rejected)

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

    def test_frame_paint_uses_pinned_float_color_api_and_preserves_readability(self):
        source = postimage('chrome/browser/ui/views/frame/browser_frame_view_win.cc')
        actual = function(source, 'void BrowserFrameViewWin::OnPaint(gfx::Canvas* canvas)')
        self.assertIn(FRAME_GRADIENT.decode(), actual)
        declaration = (ROOT / 'tests/fixtures/paint_shader_radial_gradient.h').read_text()
        start = declaration.index('  static sk_sp<PaintShader> MakeRadialGradient(')
        declaration = declaration[start:declaration.index(';', start) + 1]
        prefix = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
using SkColor=uint32_t;using U8CPU=unsigned;using SkScalar=float;
unsigned SkColorGetA(SkColor color){return color>>24;}
SkColor SkColorSetA(SkColor color,unsigned alpha){return (color&0xffffff)|(alpha<<24);}
struct SkColor4f {
 float fR=0,fG=0,fB=0,fA=0;
 static SkColor4f FromColor(SkColor color){return {
  ((color>>16)&255)/255.f,((color>>8)&255)/255.f,(color&255)/255.f,(color>>24)/255.f};}
 SkColor toSkColor()const{return (uint32_t(std::lround(fA*255))<<24)|
  (uint32_t(std::lround(fR*255))<<16)|(uint32_t(std::lround(fG*255))<<8)|uint32_t(std::lround(fB*255));}
};
namespace SkColors {constexpr SkColor4f kTransparent{};}
struct SkPoint {float fX,fY;static SkPoint Make(float x,float y){return {x,y};}};
enum class SkTileMode {kClamp};struct SkMatrix{};
namespace SkGradient {struct Interpolation{};}
template<typename T> using sk_sp=std::shared_ptr<T>;
namespace cc {
SkPoint last_center{};SkScalar last_radius=0;std::array<SkColor4f,2> last_colors{};
std::array<SkScalar,2> last_positions{};int gradient_count=0;
struct PaintShader {
 static SkGradient::Interpolation DefaultInterpolation(){return {};}
'''
        shader = r'''
};
sk_sp<PaintShader> PaintShader::MakeRadialGradient(
 const SkPoint& center,SkScalar radius,const SkColor4f colors[],const SkScalar pos[],
 int color_count,SkTileMode mode,SkGradient::Interpolation,uint32_t,const SkMatrix*,SkColor4f) {
 assert(color_count==2 && mode==SkTileMode::kClamp);
 last_center=center;last_radius=radius;last_colors={colors[0],colors[1]};
 last_positions={pos[0],pos[1]};++gradient_count;
 return std::make_shared<PaintShader>();
}
struct PaintFlags {void setShader(sk_sp<PaintShader> shader){assert(shader);}};
}
namespace gfx {
struct Rect {int width=200,height=100;};
struct RectF {Rect rect;explicit RectF(Rect value):rect(value){}
 float width()const{return rect.width;}float height()const{return rect.height;}};
struct Canvas {
 std::string events;SkColor floor=0;
 void DrawRect(const RectF&,const cc::PaintFlags&){events+='G';}
 void FillRect(Rect,SkColor color){events+='F';floor=color;}
};
}
struct BrowserView {bool glass=true,native_base=true;};
namespace helium {
struct Point {SkColor4f color=SkColor4f::FromColor(0xff336699);
 float x=.25f,y=.75f;double radius=.5,opacity=.5;};
struct Configuration {
 std::optional<SkColor> chrome_contrast_floor=0x80303030;
 double material_opacity=.2,tint_strength=.8;
 size_t point_count=1;std::array<Point,1> points;
} configuration;
struct Resolution {bool uses_translucent_native_base;};
bool ShouldUseNativeFrameGlass(BrowserView* view){return view->glass;}
auto GetNativeFrameGlassConfiguration(BrowserView*){return configuration;}
Resolution GetNativeFrameGlassResolution(BrowserView* view){return {view->native_base};}
Configuration GlassSurfaceConfigurationForPainting(Configuration value){return value;}
}
constexpr int kColorToolbar=0;
struct ColorProvider {SkColor GetColor(int){return 0xff101010;}};
struct BrowserFrameViewWin {
 BrowserView view;ColorProvider colors;int titlebar_paints=0;
 BrowserView* GetBrowserView(){return &view;}ColorProvider* GetColorProvider(){return &colors;}
 gfx::Rect GetLocalBounds(){return {};}
 void PaintTitlebar(gfx::Canvas*){++titlebar_paints;}
 void OnPaint(gfx::Canvas*);
};
#define TRACE_EVENT0(...) ((void)0)
'''
        main = r'''
bool near(float actual,float expected){return std::abs(actual-expected)<.00001f;}
int main(){
 BrowserFrameViewWin frame;gfx::Canvas canvas;frame.OnPaint(&canvas);
 assert(canvas.events=="GF" && frame.titlebar_paints==0);
 assert(cc::gradient_count==1 && near(cc::last_radius,60));
 assert(near(cc::last_center.fX,50) && near(cc::last_center.fY,75));
 assert(near(cc::last_colors[0].fR,.2f) && near(cc::last_colors[0].fG,.4f));
 assert(near(cc::last_colors[0].fB,.6f) && near(cc::last_colors[0].fA,.4f));
 assert(near(cc::last_colors[1].fA,0) && near(cc::last_colors[1].fR,.2f));
 assert(cc::last_positions[0]==0 && cc::last_positions[1]==1);
 assert(SkColorGetA(canvas.floor)==128);
 frame.view.native_base=false;canvas.events.clear();frame.OnPaint(&canvas);
 assert(SkColorGetA(canvas.floor)==255 && canvas.events=="GF");
 frame.view.glass=false;canvas.events.clear();frame.OnPaint(&canvas);
 assert(canvas.events.empty() && frame.titlebar_paints==1);
 frame.view.glass=true;helium::configuration.point_count=0;
 canvas.events.clear();frame.OnPaint(&canvas);assert(canvas.events=="F");
 helium::configuration.chrome_contrast_floor.reset();frame.view.native_base=true;
 canvas.events.clear();frame.OnPaint(&canvas);
 assert(canvas.floor==0xff101010 && canvas.events=="F");
}
'''
        old_body = actual.replace(FRAME_GRADIENT.decode(), LEGACY_FRAME_GRADIENT.decode())
        self.assertNotEqual(actual, old_body)
        self.compile_and_run(prefix + declaration + shader + actual + main,
                             rejected_source=prefix + declaration + shader + old_body + main,
                             rejected_diagnostic='MakeRadialGradient')


if __name__ == '__main__':
    unittest.main()
