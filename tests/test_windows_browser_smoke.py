"""Offline acceptance tests for the isolated Windows headless browser launch."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import windows_browser_smoke as smoke


class BrowserLaunchSmokeTests(unittest.TestCase):
    def test_command_uses_only_disposable_profile_and_about_blank(self):
        browser = Path("C:/temp/chrome.exe")
        profile = Path("C:/temp/arcium-test-profile")
        cmd = smoke.smoke_command(browser, profile)
        self.assertEqual(cmd[0], str(browser))
        self.assertEqual(cmd[-1], "about:blank")
        self.assertIn("--headless=new", cmd)
        self.assertIn("--disable-background-networking", cmd)
        self.assertIn("--user-data-dir=" + str(profile), cmd)
        self.assertNotIn("--no-sandbox", cmd)
        self.assertFalse(any("installer" in x for x in cmd))

    def test_passed_launch_records_success_and_deletes_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            browser = root / "chrome.exe"
            browser.write_bytes(b"placeholder")
            report = root / "results" / "launch.json"
            observed = {}

            def fake_run(command, **kwargs):
                self.assertIn("--dump-dom", command)
                self.assertEqual(command[-1], "about:blank")
                profile_arg = next(
                    x for x in command if x.startswith("--user-data-dir=")
                )
                observed["profile"] = Path(profile_arg.split("=", 1)[1])
                self.assertTrue(observed["profile"].is_dir())
                self.assertEqual(kwargs["timeout"], 25)
                return subprocess.CompletedProcess(command, 0, "<html></html>", "")

            with patch.object(smoke.sys, "platform", "win32"), \
                 patch.object(smoke.subprocess, "run", side_effect=fake_run):
                exit_code = smoke.run_smoke(browser, report, timeout=25)

            data = json.loads(report.read_text())
            self.assertEqual(exit_code, 0)
            self.assertEqual(data["status"], "HEADLESS_LAUNCH_PASSED")
            self.assertTrue(data["browser_launched"])
            self.assertTrue(data["isolated_profile_deleted"])
            self.assertFalse(observed["profile"].exists())

    def test_nonzero_exit_does_not_claim_browser_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            browser = root / "chrome.exe"
            browser.write_bytes(b"placeholder")
            report = root / "launch.json"
            with patch.object(smoke.sys, "platform", "win32"), \
                 patch.object(
                     smoke.subprocess, "run",
                     return_value=subprocess.CompletedProcess(
                         [str(browser)], 1, "", "load failed"
                     ),
                 ):
                exit_code = smoke.run_smoke(browser, report)
            self.assertEqual(exit_code, 2)
            data = json.loads(report.read_text())
            self.assertFalse(data["browser_launched"])
            self.assertEqual(data["status"], "FAILED")

    def test_refuses_non_windows_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(smoke.sys, "platform", "linux"):
                exit_code = smoke.run_smoke(
                    root / "chrome.exe", root / "report.json"
                )
            self.assertEqual(exit_code, 1)
            self.assertEqual(
                json.loads((root / "report.json").read_text())["status"], "ERROR"
            )

    def test_no_executable_fails_without_subprocess(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(smoke.sys, "platform", "win32"), \
                 patch.object(smoke.subprocess, "run") as run:
                result = smoke.run_smoke(
                    root / "chrome.exe", root / "report.json"
                )
            self.assertEqual(result, 1)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
