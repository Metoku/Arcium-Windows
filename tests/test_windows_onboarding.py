"""Isolated compiler contracts verified against the pinned effective source.

These execute the real install constants/path and Helium-discovery functions.
They do not emulate a native Chromium link, registry integration or GUI launch.
"""
import ast
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.apply_windows_arc_workflow import ROOT, ONBOARDING_PATCH, patch_targets


FIXTURE = json.loads((ROOT / 'tests/fixtures/windows_onboarding_native.json').read_text())


def function(file, signature):
    return FIXTURE['functions'][file][signature]


PATHS = r'''
#include <cassert>
#include <string>
#include <vector>
#include <cstdint>
namespace base {
enum {DIR_LOCAL_APP_DATA, DIR_ROAMING_APP_DATA};
class FilePath {
 public:
  std::wstring path;
  FilePath() = default;
  explicit FilePath(std::wstring p) : path(p) {}
  bool empty() const {return path.empty();}
  FilePath Append(const std::wstring& part) const {
    return FilePath(path.empty() ? part : path + L"\\" + part);
  }
  FilePath AppendASCII(const std::string& part) const {
    return Append(std::wstring(part.begin(),part.end()));
  }
};
bool lookup_succeeds = true;
struct PathService {
 static bool Get(int key, FilePath* path) {
   if (!lookup_succeeds) return false;
   *path = FilePath(key == DIR_LOCAL_APP_DATA ?
       LR"(C:\Users\Test\AppData\Local)" : LR"(C:\Users\Test\AppData\Roaming)");
   return true;
 }
};
}
'''


@unittest.skipUnless(shutil.which('g++') or shutil.which('c++'), 'C++ compiler required')
class OnboardingNativeContracts(unittest.TestCase):
    def compile_run(self, body, headers=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in (headers or {}).items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            cpp = root / 'contract.cc'
            cpp.write_text(body)
            binary = root / 'contract.exe'
            result = subprocess.run(
                [shutil.which('g++') or shutil.which('c++'), '-std=c++20', '-Wall',
                 '-Wextra', '-Werror', '-I', str(root), str(cpp), '-o', str(binary)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_actual_constants_and_default_paths_are_separate(self):
        headers = dict(FIXTURE['headers'])
        headers.update({
            'guiddef.h': '#pragma once\n#include <cstdint>\nstruct GUID {uint32_t a; uint16_t b,c; uint8_t d[8];};\nusing IID=GUID; using CLSID=GUID;\n',
            'base/containers/span.h': '#pragma once\n#include <span>\nnamespace base {template<class T> using span=std::span<T>;}\n',
            'chrome/install_static/buildflags.h': '#pragma once\n#define BUILDFLAG(x) (x)\n#define USE_GOOGLE_UPDATE_INTEGRATION 0\n',
            'chrome/app/chrome_dll_resource.h': '#pragma once\n#define IDR_MAINFRAME 1\n',
            'chrome/common/chrome_icon_resources_win.h': '#pragma once\nnamespace icon_resources {constexpr int kApplicationIndex=0,kHtmlDocIndex=1,kPDFDocIndex=2;}\n',
        })
        install = 'chrome/install_static/install_util.cc'
        paths = 'chrome/common/chrome_paths_win.cc'
        self.compile_run(PATHS + r'''
#include "chrome/install_static/chromium_install_modes.h"
#include <string_view>
namespace install_static {
constexpr size_t kProductPathNameLength = std::size(kProductPathName)-1;
struct InstallDetails {
 static InstallDetails Get() {return {};}
 const InstallConstants& mode() const {return kInstallModes[0];}
};
''' + function(install, 'std::wstring& AppendChromeInstallSubDirectory(')
             + function(install, 'std::wstring GetChromeInstallSubDirectory()')
             + function(install, 'std::wstring GetRegistryPath()') + r'''
}
namespace chrome {constexpr wchar_t kUserDataDirname[]=L"User Data";}
''' + function(paths, 'bool GetDefaultUserDataDirectory(')
             + function(paths, 'bool GetDefaultRoamingUserDataDirectory(') + r'''
int main() {
 using namespace install_static;
 using namespace std::literals;
 const auto& mode=kInstallModes[0];
 assert(L""sv==kCompanyPathName && L"Arcium"sv==kProductPathName);
 assert(L"Arcium"sv==mode.base_app_name && L"Arcium"sv==mode.base_app_id);
 assert(L"ArciumHTM"sv==mode.browser_prog_id_prefix);
 assert(L"ArciumPDF"sv==mode.pdf_prog_id_prefix);
 assert("arcium"sv==mode.direct_launch_url_scheme);
 assert(std::wstring_view(mode.browser_prog_id_prefix).size()<=11);
 assert(L"{FB68A146-637A-48C2-A0C4-1565DE45FEBD}"sv!=mode.app_guid);
 assert(mode.toast_activator_clsid.a!=0xE9852F6C);
 assert(mode.elevator_clsid.a!=0x140DE20F);
 assert(mode.tracing_service_clsid.a!=0x83f69367);
 // Keep the existing COM interface contracts; only class identities change.
 assert(mode.elevator_iid.a==0xC89A04FF && mode.tracing_service_iid.a==0xe0b03e2d);
 assert(GetChromeInstallSubDirectory()==L"Arcium");
 assert(GetRegistryPath()==LR"(Software\Arcium)");
 base::FilePath local, roaming;
 assert(GetDefaultUserDataDirectory(&local));
 assert(local.path==LR"(C:\Users\Test\AppData\Local\Arcium\User Data)");
 assert(GetDefaultRoamingUserDataDirectory(&roaming));
 assert(roaming.path==LR"(C:\Users\Test\AppData\Roaming\Arcium\User Data)");
 base::lookup_succeeds=false;
 assert(!GetDefaultUserDataDirectory(&local));
 assert(!GetDefaultRoamingUserDataDirectory(&roaming));
}
''', headers)

    def test_helium_source_requires_detection_and_excludes_extensions_passwords(self):
        self.compile_run(PATHS + function(
            'chrome/common/importer/chrome_importer_utils_win.cc',
            'base::FilePath GetHeliumUserDataFolder()') + r'''
namespace user_data_importer {
enum {NONE=0,HISTORY=1,FAVORITES=2,PASSWORDS=4,EXTENSIONS=8,TYPE_CHROME=9};
struct SourceProfile {int services_supported;};
}
std::vector<user_data_importer::SourceProfile> candidates;
int detections=0;
std::vector<int> GetChromeSourceProfiles(const base::FilePath& path) {
 assert(path.path==LR"(C:\Users\Test\AppData\Local\imput\Helium\User Data\Local State)");
 ++detections;
 return {};
}
void AddChromeToProfiles(std::vector<user_data_importer::SourceProfile>* profiles,
                        const std::vector<int>&, const base::FilePath& folder,
                        const std::string& brand, int type) {
 assert(folder.path==LR"(C:\Users\Test\AppData\Local\imput\Helium\User Data)");
 assert(brand=="Helium" && type==user_data_importer::TYPE_CHROME);
 *profiles=candidates;
}
''' + function('chrome/browser/importer/chrome_importer_list.cc',
              'void DetectHeliumProfiles(') + r'''
int main() {
 using namespace user_data_importer;
 std::vector<SourceProfile> profiles{{16}};
 assert(detections==0);
 base::lookup_succeeds=false;
 assert(GetHeliumUserDataFolder().empty());
 DetectHeliumProfiles(&profiles);
 assert(detections==0 && profiles.size()==1);
 base::lookup_succeeds=true;
 candidates={{HISTORY|FAVORITES|PASSWORDS|EXTENSIONS},{PASSWORDS|EXTENSIONS}};
 DetectHeliumProfiles(&profiles);
 assert(detections==1 && profiles.size()==2);
 assert(profiles[0].services_supported==16);
 assert(profiles[1].services_supported==(HISTORY|FAVORITES));
}
''')


class OnboardingCatalogContracts(unittest.TestCase):
    def test_target_scope_and_windows_policy_separation(self):
        text = ONBOARDING_PATCH.read_text()
        self.assertEqual(len(patch_targets(text)), 10)
        line = next(line[1:] for line in text.splitlines()
                    if line.startswith('+CHROMIUM_POLICY_KEY ='))
        value = ast.literal_eval(line.split('=', 1)[1].strip())
        self.assertEqual(value, r'SOFTWARE\\Policies\\Arcium')
        self.assertIn('+      L"SOFTWARE\\\\Policies\\\\Arcium";', text)


if __name__ == '__main__':
    unittest.main()
