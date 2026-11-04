"""Compile verified function excerpts from the opt-in Windows caption patch.

Pinned-source replay verifies these bodies and the graphics/View declarations.
These are isolated compiler/behavior contracts, not Chromium linkage or UI tests.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.apply_windows_arc_workflow import (
    ROOT, LEGACY_MAC_LAYOUT_INVALIDATION, MAC_LAYOUT_INVALIDATION,
)
from scripts.check_windows_mac_buttons import class_member_access

FIXTURE = json.loads((ROOT / 'tests/fixtures/mac_window_functions.json').read_text())['files']
API = json.loads((ROOT / 'tests/fixtures/mac_window_api.json').read_text())
VIEW_ACCESS = json.loads((ROOT / 'tests/fixtures/mac_window_access.json').read_text())['ui/views/view.h']['View']
FRAME = 'chrome/browser/ui/views/frame/browser_frame_view_win.cc'
BUTTON = 'chrome/browser/ui/views/frame/windows_caption_button.cc'
GROUP = 'chrome/browser/ui/views/frame/browser_caption_button_container_win.cc'


def actual(path, *signatures):
    return '\n'.join(FIXTURE[path][name] for name in signatures)


COMMON = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <utility>
#include <vector>
using SkColor=uint32_t;
constexpr SkColor SkColorSetARGB(int a,int r,int g,int b){return (unsigned(a)<<24)|(r<<16)|(g<<8)|b;}
constexpr SkColor SkColorSetRGB(int r,int g,int b){return SkColorSetARGB(255,r,g,b);}
namespace cc {
struct PaintFlags {enum Style{kFill_Style,kStroke_Style};SkColor color=0;float stroke=0;Style style=kFill_Style;
 void setAntiAlias(bool){} void setColor(SkColor v){color=v;}
 void setStyle(Style v){style=v;}void setStrokeWidth(float v){stroke=v;}};
}
namespace gfx {
struct Point {int x_=0,y_=0;Point()=default;Point(int x,int y):x_(x),y_(y){}
 int x()const{return x_;}int y()const{return y_;}};
struct PointF {float x_,y_;PointF(float x,float y):x_(x),y_(y){}
 float x()const{return x_;}float y()const{return y_;}};
struct Size {int w=0,h=0;Size()=default;Size(int x,int y):w(x),h(y){}
 int width()const{return w;}int height()const{return h;}bool IsEmpty()const{return !w||!h;}};
struct SizeF {float w=0,h=0;SizeF()=default;SizeF(float x,float y):w(x),h(y){}};
struct Insets {int t,l,b,r;static Insets TLBR(int t,int l,int b,int r){return{t,l,b,r};}};
struct Rect {int x_=0,y_=0,w=0,h=0;Rect()=default;Rect(int x,int y,int w,int h):x_(x),y_(y),w(w),h(h){}
 template<typename T>explicit Rect(const T& r):Rect(r.left,r.top,r.right-r.left,r.bottom-r.top){}
 int x()const{return x_;}int y()const{return y_;}int width()const{return w;}int height()const{return h;}
 int right()const{return x_+w;}int bottom()const{return y_+h;}
 Point CenterPoint()const{return{x_+w/2,y_+h/2};}
 bool Contains(const Point& p)const{return p.x()>=x_&&p.x()<right()&&p.y()>=y_&&p.y()<bottom();}
 void Inset(Insets i){x_+=i.l;y_+=i.t;w-=i.l+i.r;h-=i.t+i.b;}};
struct RectF {float x,y,w,h;RectF(float x,float y,float w,float h):x(x),y(y),w(w),h(h){}
 explicit RectF(Rect r):RectF(r.x(),r.y(),r.width(),r.height()){} };
}
namespace ui {struct TouchUiController {bool touch=false;static auto* Get(){static TouchUiController c;return &c;}
 bool touch_ui()const{return touch;}};}
constexpr int VIEW_ID_CLOSE_BUTTON=1,VIEW_ID_MINIMIZE_BUTTON=2,VIEW_ID_MAXIMIZE_BUTTON=3,VIEW_ID_RESTORE_BUTTON=4;
constexpr int HTNOWHERE=0,HTCLIENT=1,HTCAPTION=2,HTSYSMENU=3,HTMINBUTTON=8,HTMAXBUTTON=9,
 HTLEFT=10,HTTOP=12,HTTOPLEFT=13,HTTOPRIGHT=14,HTBOTTOMRIGHT=17,HTCLOSE=20;
#define NOTREACHED() std::abort()
'''


class ViewAccessContracts(unittest.TestCase):
    def test_nested_public_labels_and_documentation_do_not_expose_protected_members(self):
        source = '''
class View;
class VIEWS_EXPORT View : public Parent {
 public:
  class Child { public: void Nested(); };
  void Public();
 protected:
  // public: a documentation example
  struct Details { public: void NestedAgain(); };
  static constexpr char note[] = "public: { }";
  void Protected();
};
class Other { public: void Outside(); };
'''
        self.assertEqual(class_member_access(source, 'View', '  void Public();'), 'public')
        self.assertEqual(class_member_access(source, 'View', '  void Protected();'), 'protected')
        with self.assertRaisesRegex(RuntimeError, 'outside View'):
            class_member_access(source, 'View', 'void Outside();')


@unittest.skipUnless(shutil.which('g++') or shutil.which('c++'), 'C++ compiler required')
class MacCaptionContracts(unittest.TestCase):
    def compile_run(self, body, expected_compile_error=None):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cpp=root/'contract.cc';binary=root/'contract.exe'
            cpp.write_text(COMMON+body)
            result=subprocess.run([shutil.which('g++') or shutil.which('c++'),
                                   '-std=c++20','-Wall','-Wextra',str(cpp),'-o',str(binary)],
                                  capture_output=True,text=True)
            if expected_compile_error is not None:
                self.assertNotEqual(result.returncode,0,'Reported compiler error unexpectedly compiled')
                self.assertIn(expected_compile_error,result.stderr)
                return
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_opt_in_falls_back_for_native_titlebar_apps_rtl_touch_and_forced_colors(self):
        native_api=(ROOT/'tests/fixtures/native_theme_appearance.h').read_text()
        prefix=r'''
namespace base {
struct CommandLine {bool flag=false;static auto* ForCurrentProcess(){static CommandLine c;return &c;}
 bool HasSwitch(const char* name)const{assert(std::string(name)=="arcium-mac-window-buttons");return flag;}};
namespace i18n {bool rtl=false;bool IsRTL(){return rtl;}}
}
namespace ui {struct ColorProviderKey{enum class ForcedColors{kNone,kActive};};struct NativeTheme {
''' + native_api + r'''
 ColorProviderKey::ForcedColors forced_colors_=ColorProviderKey::ForcedColors::kNone;
 PreferredColorScheme preferred_color_scheme_=PreferredColorScheme::kLight;
 PreferredContrast preferred_contrast_=PreferredContrast::kNoPreference;
};NativeTheme* NativeTheme::GetInstanceForNativeUi(){static NativeTheme t;return &t;}}
struct BrowserView {bool normal=true,custom=true;bool GetIsNormalType()const{return normal;}};
bool ShouldBrowserCustomDrawTitlebar(BrowserView* view){return view->custom;}
struct BrowserFrameViewWin {mutable BrowserView view;BrowserView* GetBrowserView()const{return &view;}
 bool CaptionButtonsOnLeadingEdge()const;};
'''
        main=r'''
int main(){BrowserFrameViewWin frame;
 assert(!frame.CaptionButtonsOnLeadingEdge());base::CommandLine::ForCurrentProcess()->flag=true;
 assert(frame.CaptionButtonsOnLeadingEdge());
 frame.view.normal=false;assert(!frame.CaptionButtonsOnLeadingEdge());frame.view.normal=true;
 frame.view.custom=false;assert(!frame.CaptionButtonsOnLeadingEdge());frame.view.custom=true;
 base::i18n::rtl=true;assert(!frame.CaptionButtonsOnLeadingEdge());base::i18n::rtl=false;
 ui::TouchUiController::Get()->touch=true;assert(!frame.CaptionButtonsOnLeadingEdge());
 ui::TouchUiController::Get()->touch=false;
 auto* native=ui::NativeTheme::GetInstanceForNativeUi();
 native->forced_colors_=ui::ColorProviderKey::ForcedColors::kActive;
 assert(!frame.CaptionButtonsOnLeadingEdge());
 native->forced_colors_=ui::ColorProviderKey::ForcedColors::kNone;
 assert(frame.CaptionButtonsOnLeadingEdge());}
'''
        self.compile_run(prefix+actual(FRAME,'bool BrowserFrameViewWin::CaptionButtonsOnLeadingEdge() const')+main)

    def test_actual_painter_colors_symbols_inactive_disabled_and_native_fallback(self):
        prefix=r'''
namespace color_utils {SkColor GetResultingPaintColor(SkColor,SkColor base){return base-1;}}
namespace gfx {struct Canvas {struct Circle{float radius;SkColor color;};
 std::vector<Circle> circles;int lines=0,rectangles=0;
'''+'\n'.join(API['ui/gfx/canvas.h'])+r'''
};
void Canvas::DrawCircle(const PointF&,float radius,const cc::PaintFlags& flags){circles.push_back({radius,flags.color});}
void Canvas::DrawLine(const PointF&,const PointF&,const cc::PaintFlags&){++lines;}
void Canvas::DrawRect(const RectF&,const cc::PaintFlags&){++rectangles;}}
namespace views {struct SizeBounds{};}
struct WindowFrameUtil {static constexpr int kWindowsCaptionButtonWidth=46,
 kWindowsCaptionButtonHeightRestored=30,kWindowsCaptionButtonVisualSpacing=2;};
struct BrowserView {struct Info{int tabstrip_preferred_height=0;};Info GetFrameElementInfo(){return{};}};
struct Frame {bool mac=true,maximized=false;BrowserView view;
 bool CaptionButtonsOnLeadingEdge()const{return mac;}bool IsMaximized()const{return maximized;}
 BrowserView* GetBrowserView(){return &view;}int TitlebarMaximizedVisualHeight(){return 32;}};
struct Widget {bool active=true;bool ShouldPaintAsActive(){return active;}};
struct WindowsCaptionButton {enum State{STATE_NORMAL,STATE_HOVERED,STATE_PRESSED};
 Frame* frame_view_;int button_type_=VIEW_ID_CLOSE_BUTTON;Widget widget;bool enabled=true;
 State state=STATE_NORMAL;int native_paints=0;
 bool GetEnabled(){return enabled;}Widget* GetWidget(){return &widget;}auto GetState(){return state;}
 gfx::Rect GetContentsBounds(){return{0,0,22,30};}
 void PaintSymbol(gfx::Canvas*){++native_paints;}
 int GetButtonDisplayOrderIndex()const{return button_type_==VIEW_ID_MINIMIZE_BUTTON?0:1;}
 void PaintMacSymbol(gfx::Canvas*);void PaintButtonContents(gfx::Canvas*);
 gfx::Size CalculatePreferredSize(const views::SizeBounds&)const;int GetBetweenButtonSpacing()const;
};
'''
        main=r'''
int main(){Frame frame;WindowsCaptionButton button{&frame};
 for(auto pair:std::array<std::pair<int,SkColor>,4>{{{VIEW_ID_CLOSE_BUTTON,0xffff5f57u},
  {VIEW_ID_MINIMIZE_BUTTON,0xfffebc2eu},{VIEW_ID_MAXIMIZE_BUTTON,0xff28c840u},
  {VIEW_ID_RESTORE_BUTTON,0xff28c840u}}}){
  button.button_type_=pair.first;gfx::Canvas canvas;button.state=WindowsCaptionButton::STATE_NORMAL;
  button.PaintButtonContents(&canvas);assert(canvas.circles.size()==2);
  assert(canvas.circles[0].color==pair.second&&canvas.circles[0].radius==6.f);
  assert(canvas.lines==0&&canvas.rectangles==0);
  gfx::Canvas hovered;button.state=WindowsCaptionButton::STATE_HOVERED;button.PaintButtonContents(&hovered);
  assert(hovered.lines+hovered.rectangles>0);
 }
 button.enabled=false;gfx::Canvas disabled;button.PaintButtonContents(&disabled);
 assert(disabled.circles[0].color==0xff969696u&&disabled.lines==0&&disabled.rectangles==0);
 button.enabled=true;button.widget.active=false;gfx::Canvas inactive;button.PaintButtonContents(&inactive);
 assert(inactive.circles[0].color==0xff969696u);
 button.widget.active=true;button.state=WindowsCaptionButton::STATE_PRESSED;
 gfx::Canvas pressed;button.PaintButtonContents(&pressed);assert(pressed.circles[0].color!=0xff28c840u);
 assert(button.CalculatePreferredSize({}).width()==22);
 frame.maximized=true;assert(button.CalculatePreferredSize({}).height()==30);
 frame.mac=false;gfx::Canvas native;button.PaintButtonContents(&native);
 assert(button.native_paints==1&&native.circles.empty());
 button.button_type_=VIEW_ID_MINIMIZE_BUTTON;assert(button.CalculatePreferredSize({}).width()==46);
}
'''
        prefix=prefix.replace('void PaintMacSymbol(gfx::Canvas*);',
            API['chrome/browser/ui/views/frame/windows_caption_button.h'][0])
        self.compile_run(prefix+actual(BUTTON,'void WindowsCaptionButton::PaintMacSymbol(gfx::Canvas* canvas)',
            'void WindowsCaptionButton::PaintButtonContents(gfx::Canvas* canvas)',
            'gfx::Size WindowsCaptionButton::CalculatePreferredSize(',
            'int WindowsCaptionButton::GetBetweenButtonSpacing() const')+main)

    def test_group_reorders_existing_controls_and_restores_native_order(self):
        public = '\n'.join(declaration for declaration, access in VIEW_ACCESS.items() if access == 'public')
        protected = '\n'.join(declaration for declaration, access in VIEW_ACCESS.items() if access == 'protected')
        prefix=r'''
namespace views {
class View {
 public:
 int invalidations=0;
''' + public + '\n protected:\n' + protected + r'''
};
void View::InvalidateLayout(bool) {++invalidations;}
void View::PreferredSizeChanged() {InvalidateLayout();}
}
struct Button : views::View {
 explicit Button(int value):id(value){}
 int id;bool visible=true,enabled=true;
 void SetVisible(bool v){visible=v;}void SetEnabled(bool v){enabled=v;}
};
template<typename T>struct Ptr {T* p;T* get()const{return p;}T* operator->()const{return p;}
 operator T*()const{return p;}};
struct BrowserView {bool min=true,max=true;bool CanMinimize(){return min;}bool CanMaximize(){return max;}};
struct Frame {bool mac=false,maximized=false;BrowserView view;
 bool CaptionButtonsOnLeadingEdge(){return mac;}bool IsMaximized(){return maximized;}
 BrowserView* GetBrowserView(){return &view;}};
struct BrowserCaptionButtonContainer : views::View {
 Frame* frame_view_;Ptr<Button> minimize_button_,maximize_button_,restore_button_,close_button_;
 bool mac_style_=false;std::vector<Button*> order;
 void ReorderChildView(Button* b,size_t index){auto it=std::find(order.begin(),order.end(),b);
  assert(it!=order.end());order.erase(it);order.insert(order.begin()+index,b);}
 void UpdateMacButtonStyle();void UpdateButtons();
};
'''
        main=r'''
int main(){Frame frame;Button min{2},max{3},restore{4},close{1};
 BrowserCaptionButtonContainer c;
 c.frame_view_=&frame;c.minimize_button_={&min};c.maximize_button_={&max};
 c.restore_button_={&restore};c.close_button_={&close};c.order={&min,&max,&restore,&close};
 c.UpdateButtons();assert(c.order[0]==&min&&max.visible&&!restore.visible);
 frame.mac=true;c.UpdateButtons();assert(c.order[0]==&close&&c.order[1]==&min&&c.order[2]==&max);
 assert(close.invalidations==1);c.UpdateButtons();assert(close.invalidations==1);
 frame.maximized=true;c.UpdateButtons();assert(!max.visible&&restore.visible);
 ui::TouchUiController::Get()->touch=true;c.UpdateButtons();assert(!max.enabled&&!restore.enabled);
 ui::TouchUiController::Get()->touch=false;frame.view.min=false;frame.view.max=false;c.UpdateButtons();
 assert(!min.visible&&!max.visible&&!restore.visible&&close.visible);
 frame.mac=false;c.UpdateButtons();assert(c.order[0]==&min&&c.order[1]==&max&&c.order[3]==&close);
 assert(close.invalidations==2);
}
'''
        declarations=API['chrome/browser/ui/views/frame/browser_caption_button_container_win.h']
        prefix=prefix.replace('void UpdateMacButtonStyle();',declarations[0]).replace(
            'bool mac_style_=false;',declarations[1])
        functions=actual(GROUP,'void BrowserCaptionButtonContainer::UpdateMacButtonStyle()',
                          'void BrowserCaptionButtonContainer::UpdateButtons()')
        self.compile_run(prefix+functions+main)
        # Reproduce the actual clang-cl failure with the pinned access labels.
        self.assertEqual(functions.count(MAC_LAYOUT_INVALIDATION.decode()), 1)
        legacy=functions.replace(MAC_LAYOUT_INVALIDATION.decode(),
                                 LEGACY_MAC_LAYOUT_INVALIDATION.decode(), 1)
        self.compile_run(prefix+legacy+main, expected_compile_error='protected')

    def test_real_frame_layout_exclusions_hit_testing_reveal_and_resize(self):
        prefix=r'''
#define TRACE_EVENT0(a,b)
struct RECT{int left=0,top=0,right=0,bottom=0;};
constexpr int DWMWA_CAPTION_BUTTON_BOUNDS=5,SM_CYSIZEFRAME=1,SM_CXSMICON=2,SM_CYSMICON=3,
 kIconTitleSpacing=5;
int native_queries=0,test_resize=HTNOWHERE;
bool SUCCEEDED(int v){return v>=0;}
int DwmGetWindowAttribute(int,int,RECT*,size_t){++native_queries;return -1;}
namespace display::win {float GetDPIScale(){return 1.f;}
struct Screen {int GetSystemMetricsInDIP(int){return 16;}};
struct GetScreenWinProxy{};Screen* GetScreenWin(){static Screen s;return &s;}}
namespace gfx {
RectF ConvertRectToDips(Rect r,float){return RectF(r);}
Rect ToFlooredRectDeprecated(RectF r){return{int(r.x),int(r.y),int(r.w),int(r.h)};}
}
enum class LayoutConstant{kTabStripPadding};int GetLayoutConstant(LayoutConstant){return 8;}
int GetHTComponentForFrame(const gfx::Point&,gfx::Insets,int,int,bool){return test_resize;}
namespace base {struct CommandLine {bool hide=false;
 static auto* ForCurrentProcess(){static CommandLine c;return &c;}
 bool HasSwitch(const char* key){assert(std::string(key)=="hide-window-buttons");return hide;}};}
struct BrowserView {bool app=false,overlay=false;gfx::Size app_toolbar;
 bool GetIsWebAppType(){return app;}bool IsWindowControlsOverlayEnabled(){return overlay;}
 gfx::Size GetWebAppFrameToolbarPreferredSize(){return app_toolbar;}};
struct Client {int hit=HTCLIENT;int NonClientHitTest(const gfx::Point&){return hit;}};
struct Widget {bool fullscreen=false;Client client;
 bool IsFullscreen(){return fullscreen;}Client* client_view(){return &client;}
 Widget* widget_delegate(){return this;}bool CanResize(){return true;}};
namespace views {int HWNDForWidget(Widget*){return 0;}}
struct Container {gfx::Rect rect;gfx::Size preferred{66,30};bool visible=true,process=true;
 const gfx::Rect& bounds(){return rect;}void SetVisible(bool v){visible=v;}
 bool GetVisible(){return visible;}gfx::Size GetPreferredSize(){return preferred;}
 void SetBounds(int x,int y,int w,int h){rect={x,y,w,h};}
 bool HitTestPoint(const gfx::Point& p){return gfx::Rect(0,0,rect.w,rect.h).Contains(p);}
 int NonClientHitTest(const gfx::Point& p){
  if(!process)return HTCAPTION;
  return p.x()<22?HTCLOSE:p.x()<44?HTMINBUTTON:HTMAXBUTTON;
 }
 void SetCaptionButtonsCanProcessEvents(bool v){process=v;}};
struct Icon{gfx::Rect bounds(){return{0,0,16,16};}};
struct BrowserLayoutParams {gfx::Rect visual_client_area;
 struct Exclusion {gfx::SizeF content;int horizontal_padding=0,vertical_padding=0;};
 Exclusion leading_exclusion,trailing_exclusion;};
struct BrowserFrameView {int NonClientHitTest(const gfx::Point&){return HTNOWHERE;}};
struct BrowserFrameViewWin:BrowserFrameView {
 enum class TitlebarType{kAny};bool mac=true,maximized=false;int w=800,h=600,top=1;
 Container* caption_button_container_;BrowserView view;Widget widget;Icon* window_icon_=nullptr;
 gfx::Rect client_view_bounds_{0,0,800,600};
 bool CaptionButtonsOnLeadingEdge()const{return mac;}bool IsMaximized()const{return maximized;}
 bool IsFrameCondensed()const{return maximized;}bool ShouldShowWindowIcon(TitlebarType)const{return false;}
 Widget* browser_widget(){return &widget;}BrowserView* GetBrowserView(){return &view;}
 const BrowserView* GetBrowserView()const{return &view;}
 int width()const{return w;}gfx::Rect bounds()const{return{0,0,w,h};}
 int WindowTopY()const{return top;}int GetFrameHeight(){return 30;}
 int TitlebarHeight(bool){return 38;}int FrameBorderThickness(){return 8;}
 int FrameTopBorderThickness(bool){return 1;}void* parent(){return nullptr;}
 gfx::Rect GetMirroredRect(gfx::Rect r){return r;}
 static gfx::Point ConvertPointToTarget(void*,Container* c,const gfx::Point& p){
  return{p.x()-c->rect.x(),p.y()-c->rect.y()};}
 BrowserLayoutParams GetBrowserLayoutParams()const;
 void LayoutCaptionButtons();int NonClientHitTest(const gfx::Point&);
 void SetCaptionButtonsOpacity(float);
};
'''
        # The real accessor is callable on a const frame; mirror that here.
        prefix=prefix.replace('bool IsWindowControlsOverlayEnabled(){',
                              'bool IsWindowControlsOverlayEnabled()const{')
        main=r'''
int main(){Container controls;BrowserFrameViewWin frame;frame.caption_button_container_=&controls;
 for(float dpi:{1.f,1.25f,1.5f,2.f}){
  frame.LayoutCaptionButtons();assert(controls.rect.x()==8&&controls.rect.width()==66);
  auto layout=frame.GetBrowserLayoutParams();assert(layout.leading_exclusion.content.w==74);
  assert(layout.trailing_exclusion.content.w==0);
  assert(controls.rect.x()*dpi+controls.rect.width()*dpi<=layout.leading_exclusion.content.w*dpi);
 }
 // A toolbar/sidebar HTCLIENT must not steal the three real button hit codes.
 assert(frame.NonClientHitTest({19,16})==HTCLOSE);
 assert(frame.NonClientHitTest({41,16})==HTMINBUTTON);
 assert(frame.NonClientHitTest({63,16})==HTMAXBUTTON);
 frame.SetCaptionButtonsOpacity(0);assert(!controls.process);
 assert(frame.NonClientHitTest({19,16})!=HTCLOSE);
 frame.SetCaptionButtonsOpacity(0.5f);assert(controls.process);
 test_resize=HTTOPLEFT;assert(frame.NonClientHitTest({9,2})==HTTOPLEFT);
 frame.maximized=true;assert(frame.NonClientHitTest({9,2})==HTCLOSE);
 frame.maximized=false;test_resize=HTNOWHERE;
 frame.widget.client.hit=HTNOWHERE;native_queries=0;
 assert(frame.NonClientHitTest({799,3})==HTCAPTION&&native_queries==0);
 frame.mac=false;controls.preferred={138,30};frame.LayoutCaptionButtons();
 assert(controls.rect.x()==662);auto native=frame.GetBrowserLayoutParams();
 assert(native.trailing_exclusion.content.w==138&&native.leading_exclusion.content.w==0);
 frame.NonClientHitTest({500,3});assert(native_queries==1);
 frame.mac=true;frame.widget.fullscreen=true;frame.LayoutCaptionButtons();assert(!controls.visible);
 frame.widget.fullscreen=false;base::CommandLine::ForCurrentProcess()->hide=true;
 frame.LayoutCaptionButtons();assert(!controls.visible&&controls.rect.width()==0&&controls.rect.x()==0);
}
'''
        self.compile_run(prefix+actual(FRAME,
            'BrowserLayoutParams BrowserFrameViewWin::GetBrowserLayoutParams() const',
            'void BrowserFrameViewWin::LayoutCaptionButtons()',
            'int BrowserFrameViewWin::NonClientHitTest(',
            'void BrowserFrameViewWin::SetCaptionButtonsOpacity(float opacity)')+main)


if __name__=='__main__':
    unittest.main()
