// Isolated host for the ACTUAL cleanup functions copied from the effective
// Chromium source by check_windows_tab_tools.py. Adapters simulate browser
// lifecycle events; this is not a native Chromium or UI build.
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace base {
struct TimeDelta {
  int64_t seconds;
  int64_t InSeconds() const { return seconds; }
  bool operator<(TimeDelta other) const { return seconds < other.seconds; }
};
struct Time {
  int64_t seconds;
  static Time Now() { return {10000000}; }
  bool is_null() const { return seconds == 0; }
  TimeDelta operator-(Time other) const { return {seconds - other.seconds}; }
};
TimeDelta Hours(int value) { return {int64_t{value} * 3600}; }
template <class T> struct WeakPtr {
  T* value = nullptr;
  operator bool() const { return value && value->alive; }
  T* get() const { return value; }
  T* operator->() const { return value; }
};
template <class T> struct WeakFactory {
  T* value;
  WeakPtr<T> GetWeakPtr() { return {value}; }
};
}  // namespace base

namespace prefs {
const char* kSavingBrowserHistoryDisabled = "history.saving_disabled";
}
namespace arcium_settings {
const char* kTabCleanupHoursPref = "arcium.tabs.cleanup_hours";
}
struct Prefs {
  int hours = 0;
  bool history_disabled = false;
  int GetInteger(const char*) const { return hours; }
  bool GetBoolean(const char*) const { return history_disabled; }
};
struct Browser;
struct Profile;
struct Model;
namespace tabs { struct TabInterface; }

namespace helium {
struct HeliumSpaceService {
  std::string space = "first";
  bool IsPersistentItemTab(const tabs::TabInterface*) const;
  std::string GetSpaceIdForBrowser(Browser*) const { return space; }
};
struct HeliumSpaceServiceFactory {
  static HeliumSpaceService* GetForProfile(Profile*);
};
}
struct Profile {
  Prefs prefs;
  helium::HeliumSpaceService* spaces = nullptr;
  bool off_the_record = false;
  Prefs* GetPrefs() { return &prefs; }
  bool IsOffTheRecord() const { return off_the_record; }
};
struct Browser {
  Profile profile_value;
  Model* model = nullptr;
  Profile* profile() { return &profile_value; }
  Model* tab_strip_model() { return model; }
};

struct LiveData {
  bool auto_discardable = true;
  bool capturing_audio = false, capturing_video = false, mirrored = false;
  bool capturing_window = false, capturing_display = false, dev_tools = false;
  bool usb = false, bluetooth = false, hid = false, serial = false, withheld = false;
  bool IsAutoDiscardable() const { return auto_discardable; }
  bool IsCapturingAudio() const { return capturing_audio; }
  bool IsCapturingVideo() const { return capturing_video; }
  bool IsBeingMirrored() const { return mirrored; }
  bool IsCapturingWindow() const { return capturing_window; }
  bool IsCapturingDisplay() const { return capturing_display; }
  bool IsDevToolsOpen() const { return dev_tools; }
  bool IsConnectedToUSBDevice() const { return usb; }
  bool IsConnectedToBluetoothDevice() const { return bluetooth; }
  bool IsConnectedToHidDevice() const { return hid; }
  bool IsConnectedToSerialPort() const { return serial; }
  bool IsWithheldFromView() const { return withheld; }
};
struct Page {
  bool alive = true, live_available = true;
  bool visible = false, off_the_record = false, form = false, edits = false;
  bool audible = false, pip = false, rtc = false, web_lock = false, database_lock = false;
  base::TimeDelta navigation_age{1000000};
  LiveData live;
  bool IsVisible() const { return visible; }
  bool IsOffTheRecord() const { return off_the_record; }
  bool HadFormInteraction() const { return form; }
  bool HadUserEdits() const { return edits; }
  bool IsAudible() const { return audible; }
  bool HasPictureInPicture() const { return pip; }
  bool UsesWebRTC() const { return rtc; }
  bool IsHoldingWebLock() const { return web_lock; }
  bool IsHoldingBlockingIndexedDBLock() const { return database_lock; }
  base::TimeDelta GetTimeSinceLastNavigation() const { return navigation_age; }
};
namespace content {
struct WebContents {
  Page* page = nullptr;
  bool loading = false, captured = false, before_unload = false;
  int playing_videos = 0;
  bool IsLoading() { return loading; }
  bool IsBeingCaptured() { return captured; }
  bool NeedToFireBeforeUnloadOrUnloadEvents() { return before_unload; }
  int GetCurrentlyPlayingVideoCount() const { return playing_videos; }
};
}
struct URL {
  bool http = true;
  bool SchemeIsHTTPOrHTTPS() const { return http; }
};
namespace tabs {
struct TabInterface {
  int id = 0;
  bool alive = true, pinned = false, persistent = false;
  bool activated = false, visible = false, selected = false, split = false;
  Browser* browser = nullptr;
  content::WebContents* contents = nullptr;
  URL url;
  base::Time last_active{1};
  Browser* GetBrowserWindowInterface() { return browser; }
  content::WebContents* GetContents() { return contents; }
  URL GetURL() const { return url; }
  bool IsPinned() const { return pinned; }
  bool IsActivated() const { return activated; }
  bool IsVisible() const { return visible; }
  bool IsSelected() const { return selected; }
  bool IsSplit() const { return split; }
  base::Time GetLastActiveTime() const { return last_active; }
  base::WeakPtr<TabInterface> GetWeakPtr() { return {this}; }
};
}
namespace helium {
bool HeliumSpaceService::IsPersistentItemTab(const tabs::TabInterface* tab) const {
  return tab->persistent;
}
HeliumSpaceService* HeliumSpaceServiceFactory::GetForProfile(Profile* profile) {
  return profile->spaces;
}
}
namespace performance_manager {
struct PerformanceManager {
  inline static bool available = true;
  static bool IsAvailable() { return available; }
  static base::WeakPtr<Page> GetPrimaryPageNodeForWebContents(content::WebContents* contents) {
    return {contents->page};
  }
};
struct PageLiveStateDecorator {
  struct Data {
    static const LiveData* FromPageNode(const Page* page) {
      return page->live_available ? &page->live : nullptr;
    }
  };
}
;
}
namespace TabCloseTypes { constexpr int CLOSE_CREATE_HISTORICAL_TAB = 8; }
struct Model {
  static constexpr int kNoTab = -1;
  std::vector<tabs::TabInterface*> tabs;
  std::vector<int> restored_ids;
  std::function<void()> after_close;
  auto begin() { return tabs.begin(); }
  auto end() { return tabs.end(); }
  int count() const { return static_cast<int>(tabs.size()); }
  int GetIndexOfTab(const tabs::TabInterface* tab) const {
    auto it = std::find(tabs.begin(), tabs.end(), tab);
    return it == tabs.end() ? kNoTab : static_cast<int>(it - tabs.begin());
  }
  void CloseWebContentsAt(int index, int close_flags) {
    assert(close_flags == TabCloseTypes::CLOSE_CREATE_HISTORICAL_TAB);
    assert(index >= 0 && index < count());
    restored_ids.push_back(tabs[index]->id);
    tabs[index]->alive = false;
    tabs[index]->browser = nullptr;
    tabs.erase(tabs.begin() + index);
    if (after_close) after_close();
  }
};
using TabStripModel = Model;

// INJECT_POLICY

struct Harness {
  bool alive = true;
  Browser* current = nullptr;
  base::WeakFactory<Harness> weak_factory_{this};
  using WeakTab = base::WeakPtr<tabs::TabInterface>;
  Browser* GetBrowser() const { return alive ? current : nullptr; }
  // INJECT_CLEANUP_FUNCTIONS
};

struct World {
  helium::HeliumSpaceService spaces;
  Browser browser;
  Model model;
  Page pages[12];
  content::WebContents contents[12];
  tabs::TabInterface tabs[12];
  Harness harness;
  explicit World(int count = 4) {
    performance_manager::PerformanceManager::available = true;
    browser.model = &model;
    browser.profile_value.spaces = &spaces;
    browser.profile_value.prefs.hours = 12;
    harness.current = &browser;
    for (int i = 0; i < count; ++i) {
      contents[i].page = &pages[i];
      tabs[i].id = i;
      tabs[i].contents = &contents[i];
      tabs[i].browser = &browser;
      model.tabs.push_back(&tabs[i]);
    }
    tabs[0].activated = true;
  }
};

int main() {
  for (int hours : {12, 24, 72, 168}) {
    assert(ArciumCleanupHours(hours) == hours);
    assert(!ArciumShouldAutoClean(hours, int64_t{hours} * 3600 - 1, false, false, false));
    assert(ArciumShouldAutoClean(hours, int64_t{hours} * 3600, false, false, false));
    for (int mask = 1; mask < 8; ++mask)
      assert(!ArciumShouldAutoClean(hours, 10000000, mask & 1, mask & 2, mask & 4));
  }
  for (int hours : {-1, 0, 1, 13, 169, 2147483647}) {
    assert(ArciumCleanupHours(hours) == 0);
    assert(!ArciumShouldAutoClean(hours, 10000000, false, false, false));
  }
  assert(!ArciumShouldAutoClean(12, -1, false, false, false));
  assert(ArciumTidyBuckets({"a.test", "", "b.test", "a.test", "b.test", "c.test"}) ==
         (std::vector<std::vector<int>>{{0, 3}, {2, 4}}));
  assert(ArciumTidyBuckets({"", "single.test"}).empty());

  { World w; w.harness.Cleanup(); assert((w.model.restored_ids == std::vector<int>{1,2,3})); assert(w.model.count() == 1); }
  { World w; w.browser.profile_value.prefs.hours = 0; w.harness.Cleanup(); assert(w.model.restored_ids.empty()); }
  { World w; w.browser.profile_value.off_the_record = true; w.harness.Cleanup(); assert(w.model.restored_ids.empty()); }
  { World w; w.browser.profile_value.prefs.history_disabled = true; w.harness.Cleanup(); assert(w.model.restored_ids.empty()); }
  { World w(12); w.harness.Cleanup(); assert(w.model.restored_ids.size() == 8); }

  // Every protected state is exercised in the actual CanAutoClean function.
  for (int flag = 0; flag < 36; ++flag) {
    World w;
    auto& t = w.tabs[1]; auto& p = w.pages[1]; auto& c = w.contents[1];
    switch (flag) {
      case 0: t.pinned = true; break;
      case 1: t.persistent = true; break;
      case 2: t.activated = true; break;
      case 3: t.visible = true; break;
      case 4: t.selected = true; break;
      case 5: t.split = true; break;
      case 6: p.visible = true; break;
      case 7: p.off_the_record = true; break;
      case 8: p.live.auto_discardable = false; break;
      case 9: p.form = true; break;
      case 10: p.edits = true; break;
      case 11: c.before_unload = true; break;
      case 12: c.loading = true; break;
      case 13: c.captured = true; break;
      case 14: c.playing_videos = 1; break;
      case 15: p.audible = true; break;
      case 16: p.pip = true; break;
      case 17: p.rtc = true; break;
      case 18: p.web_lock = true; break;
      case 19: p.database_lock = true; break;
      case 20: p.live.capturing_audio = true; break;
      case 21: p.live.capturing_video = true; break;
      case 22: p.live.mirrored = true; break;
      case 23: p.live.capturing_window = true; break;
      case 24: p.live.capturing_display = true; break;
      case 25: p.live.dev_tools = true; break;
      case 26: p.live.usb = true; break;
      case 27: p.live.bluetooth = true; break;
      case 28: p.live.hid = true; break;
      case 29: p.live.serial = true; break;
      case 30: p.live.withheld = true; break;
      case 31: p.navigation_age = base::Hours(1); break;
      case 32: t.last_active = base::Time::Now(); break;
      case 33: t.last_active = {0}; break;
      case 34: p.live_available = false; break;
      case 35: c.page = nullptr; break;
    }
    assert(!Harness::CanAutoClean(&t, &w.browser, 12));
  }
  { World w; performance_manager::PerformanceManager::available = false; w.harness.Cleanup(); assert(w.model.restored_ids.empty()); }
  { World w; w.browser.profile_value.spaces = nullptr; w.harness.Cleanup(); assert(w.model.restored_ids.empty()); }
  { World w; w.tabs[1].url.http = false; assert(!Harness::CanAutoClean(&w.tabs[1], &w.browser, 12)); }
  { World w; w.tabs[1].contents = nullptr; assert(!Harness::CanAutoClean(&w.tabs[1], &w.browser, 12)); }

  // Re-entrant events change the remaining candidates during the first close.
  { World w; w.model.after_close = [&]{w.tabs[2].activated = true;}; w.harness.Cleanup(); assert((w.model.restored_ids == std::vector<int>{1,3})); }
  { World w; Browser moved; w.model.after_close = [&]{w.tabs[2].browser = &moved;}; w.harness.Cleanup(); assert((w.model.restored_ids == std::vector<int>{1,3})); }
  { World w; w.model.after_close = [&]{w.pages[2].edits = true;}; w.harness.Cleanup(); assert((w.model.restored_ids == std::vector<int>{1,3})); }
  { World w; w.model.after_close = [&]{w.spaces.space = "other";}; w.harness.Cleanup(); assert((w.model.restored_ids == std::vector<int>{1})); }
  { World w; w.model.after_close = [&]{w.browser.profile_value.prefs.hours = 0;}; w.harness.Cleanup(); assert((w.model.restored_ids == std::vector<int>{1})); }
  { World w; w.model.after_close = [&]{w.browser.profile_value.prefs.history_disabled = true;}; w.harness.Cleanup(); assert((w.model.restored_ids == std::vector<int>{1})); }
  { World w; w.model.after_close = [&]{w.harness.alive = false;}; w.harness.Cleanup(); assert((w.model.restored_ids == std::vector<int>{1})); }
  std::cout << "SIDEBAR_TAB_TOOLS_CPP_HOST_PASSED\n";
}
