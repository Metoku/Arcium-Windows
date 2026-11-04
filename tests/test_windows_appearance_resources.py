"""Validate actual string ownership metadata instead of inventing GRIT headers."""
from pathlib import Path
import tempfile
import unittest

from scripts.apply_windows_arc_workflow import APPEARANCE_CUSTOMIZE_UI_SOURCE
from scripts.check_windows_arc_import_patch import GENERATED_RESOURCES_GRD, verify_appearance_resources


class AppearanceResourceOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name)
        self.root = self.source / GENERATED_RESOURCES_GRD
        self.root.parent.mkdir(parents=True)
        self.root.write_text('''<grit><outputs><output filename="grit/generated_resources.h" type="rc_header"/></outputs>
          <release><messages><part file="settings_strings.grdp"/>
          <message name="IDS_NTP_CLOSE">Close</message></messages></release></grit>''')
        (self.root.parent / "settings_strings.grdp").write_text('''<grit-part>
          <message name="IDS_SETTINGS_ARCIUM_WORKSPACE_APPEARANCE">Workspace appearance</message>
          </grit-part>''')
        self.panel = self.source / APPEARANCE_CUSTOMIZE_UI_SOURCE
        self.panel.parent.mkdir(parents=True)
        self.panel.write_text('''#include "chrome/grit/generated_resources.h"
          {"closeWorkspacePanel", IDS_NTP_CLOSE},
          {"workspaceAppearance", IDS_SETTINGS_ARCIUM_WORKSPACE_APPEARANCE},
          ''')
        self.targets = {APPEARANCE_CUSTOMIZE_UI_SOURCE}

    def test_labels_resolve_to_the_declared_owning_header(self):
        before = (self.panel.read_bytes(), self.panel.stat().st_mtime_ns)
        result = verify_appearance_resources(self.source, self.targets)
        self.assertEqual(result["header"], "chrome/grit/generated_resources.h")
        self.assertEqual(result["panel_labels"]["closeWorkspacePanel"], "IDS_NTP_CLOSE")
        self.assertEqual(result["panel_labels"]["workspaceAppearance"], "IDS_SETTINGS_ARCIUM_WORKSPACE_APPEARANCE")
        self.assertEqual(before, (self.panel.read_bytes(), self.panel.stat().st_mtime_ns))
        self.assertFalse(result["grit_generation_verified"])

    def test_reported_nonexistent_header_is_rejected_read_only(self):
        self.panel.write_text('#include "chrome/grit/settings_strings.h"\n' + self.panel.read_text())
        before = (self.panel.read_bytes(), self.panel.stat().st_mtime_ns)
        with self.assertRaisesRegex(RuntimeError, "settings_strings.h is not generated"):
            verify_appearance_resources(self.source, self.targets)
        self.assertEqual(before, (self.panel.read_bytes(), self.panel.stat().st_mtime_ns))

    def test_unknown_string_ids_are_rejected(self):
        original = self.panel.read_text()
        for old, new in (("IDS_NTP_CLOSE", "IDS_MISSING_CLOSE"),
                         ("IDS_SETTINGS_ARCIUM_WORKSPACE_APPEARANCE", "IDS_SETTINGS_ARCIUM_UNKNOWN")):
            with self.subTest(id=new):
                self.panel.write_text(original.replace(old, new))
                with self.assertRaisesRegex(RuntimeError, "undefined|unresolved"):
                    verify_appearance_resources(self.source, self.targets)

    def test_wrong_producer_or_missing_owner_include_is_rejected(self):
        original = self.root.read_text()
        for before, after in (("grit/generated_resources.h", "grit/another_header.h"),
                              ("settings_strings.grdp", "another_part.grdp")):
            with self.subTest(value=after):
                self.root.write_text(original.replace(before, after))
                with self.assertRaisesRegex(RuntimeError, "header output|does not own"):
                    verify_appearance_resources(self.source, self.targets)
        self.root.write_text(original)
        self.panel.write_text(self.panel.read_text().replace('#include "chrome/grit/generated_resources.h"', ''))
        with self.assertRaisesRegex(RuntimeError, "missing owning header"):
            verify_appearance_resources(self.source, self.targets)


if __name__ == "__main__":
    unittest.main()
