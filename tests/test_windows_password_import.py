"""Exercise the actual password-policy handler shipped in the Windows patch.

The tiny C++ host models the handler's PrefValueMap contract, not Chromium's
password store or Windows encryption. No passwords or profile data are read.
"""

from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from scripts.apply_windows_arc_workflow import ROOT
from scripts.check_patch_overlaps import select_patch_sections


COMPILER = shutil.which("g++") or shutil.which("c++")


class WindowsPasswordPolicyTests(unittest.TestCase):
    @unittest.skipUnless(COMPILER, "A C++ compiler is needed for the isolated policy test")
    def test_windows_preserves_native_policy_while_other_platforms_stay_disabled(self):
        catalog = ROOT / "patches/windows/arc-password-import-windows.patch"
        selected = select_patch_sections(catalog.read_text(encoding="utf-8"), {
            "chrome/browser/policy/configuration_policy_handler_list_factory.cc"})
        # Reconstruct the real post-image from added and unchanged hunk lines.
        # The catalog includes the complete handler as reviewable context.
        postimage = "\n".join(line[1:] for line in selected.splitlines()
                              if line.startswith(" ") or
                              (line.startswith("+") and not line.startswith("+++")))
        handlers = re.findall(
            r"class DisabledPasswordManagerPolicyHandler[^\n]*[\s\S]*?\n};", postimage)
        self.assertEqual(len(handlers), 1, "Expected the complete actual policy handler")
        source = r'''
#include <cassert>
#include <map>
#include <string>
#define BUILDFLAG(name) TEST_IS_WIN
namespace password_manager::prefs {
constexpr char kCredentialsEnableService[] = "credentials_enable_service";
constexpr char kCredentialsEnablePasskeys[] = "credentials_enable_passkeys";
}
namespace policy {
struct PolicyMap {};
struct PolicyErrorMap {};
struct PrefValueMap {
  std::map<std::string, bool> values;
  void SetBoolean(const char* key, bool value) { values[key] = value; }
};
class ConfigurationPolicyHandler {
 public:
  virtual ~ConfigurationPolicyHandler() = default;
  virtual bool CheckPolicySettings(const PolicyMap&, PolicyErrorMap*) = 0;
  virtual void ApplyPolicySettings(const PolicyMap&, PrefValueMap*) = 0;
};
''' + handlers[0] + r'''
}
int main() {
  policy::DisabledPasswordManagerPolicyHandler handler;
  policy::PolicyMap policies;
  policy::PolicyErrorMap errors;
  assert(handler.CheckPolicySettings(policies, &errors));
  for (int setting : {-1, 0, 1}) {
    policy::PrefValueMap prefs;
    if (setting >= 0)
      prefs.SetBoolean(password_manager::prefs::kCredentialsEnableService, setting == 1);
    handler.ApplyPolicySettings(policies, &prefs);
    auto saved = prefs.values.find(password_manager::prefs::kCredentialsEnableService);
#if TEST_IS_WIN
    if (setting < 0) assert(saved == prefs.values.end());
    else assert(saved != prefs.values.end() && saved->second == (setting == 1));
#else
    assert(saved != prefs.values.end() && !saved->second);
#endif
    assert(!prefs.values.at(password_manager::prefs::kCredentialsEnablePasskeys));
  }
}
'''
        with tempfile.TemporaryDirectory(prefix="arcium-password-policy-") as temporary:
            root = Path(temporary)
            cpp = root / "policy.cc"
            cpp.write_text(source, encoding="utf-8")
            for windows in (0, 1):
                with self.subTest(windows=windows):
                    executable = root / (f"policy-{windows}" + (".exe" if os.name == "nt" else ""))
                    compiled = subprocess.run(
                        [COMPILER, "-std=c++17", "-static-libgcc", "-static-libstdc++",
                         f"-DTEST_IS_WIN={windows}", str(cpp), "-o", str(executable)],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=90)
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    result = subprocess.run([str(executable)], capture_output=True,
                                            text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
