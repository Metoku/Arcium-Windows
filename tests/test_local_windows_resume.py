"""Static guardrails for the opt-in local Windows incremental build script.

These checks deliberately do NOT download Chromium or compile anything.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "local_windows_resume.ps1"
GUIDE = ROOT / "docs" / "local-windows-incremental-build.md"


class LocalIncrementalBuildTests(unittest.TestCase):
    def test_script_preserves_existing_compilation_outputs(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("out\\Default\\build.ninja", source)
        self.assertIn("out\\Default\\args.gn", source)
        self.assertIn("ARCIUM_GN_GENERATED.marker", source)
        self.assertIn("PINNED_WINDOWS_GN_GENERATED", source)
        self.assertIn("windows_port.py' audit", source)
        self.assertIn("autoninja.py", source)
        self.assertIn(" -C out\\Default chrome", source)
        self.assertNotIn("windows_port.py' stage", source)
        self.assertNotIn("gn_smoke.py", source)
        self.assertNotIn("mini_installer", source)
        self.assertNotIn("Remove-Item -LiteralPath $source", source)
        self.assertNotIn("out\\Default\\setup.exe", source)

    def test_preflight_requires_full_sdk_28000(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("10.0.28000.0", source)
        self.assertIn("NTDDI_WIN11_BR", source)
        self.assertIn("provision_chromium_sdk.ps1", source)
        self.assertNotIn("provision_chromium_sdk.ps1 -Install", source)
        self.assertIn("VC\\Auxiliary\\Build\\vcvarsall.bat", source)
        self.assertIn("ValidateSet('check', 'resume')", source)

    def test_guide_separates_source_preparation_from_resume(self):
        guide = GUIDE.read_text(encoding="utf-8")
        self.assertIn("windows_port.py stage", guide)
        self.assertIn("gn_smoke.py --execute --max-minutes 160", guide)
        self.assertIn("local_windows_resume.ps1 -Mode check", guide)
        self.assertIn("local_windows_resume.ps1 -Mode resume -Jobs 5", guide)
        self.assertIn("chromium-156.0.8078.47-win-x64.tar.zst", guide)
        self.assertIn("Do not separately clone", guide)
        self.assertIn("do not", guide.lower())


if __name__ == "__main__":
    unittest.main()
