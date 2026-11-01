"""Offline unit tests for upstream metadata validation."""

import tempfile
import unittest
from pathlib import Path

from scripts.validate_upstream import parse_revision, read_revision


VALID_SHA = "4e8f8e2bd3cdcab014ae9663907db93e915cb850"


class ValidateUpstreamTests(unittest.TestCase):
    def test_valid_revision(self):
        self.assertEqual(parse_revision(VALID_SHA + "\n"), VALID_SHA)

    def test_reject_short_revision(self):
        with self.assertRaises(ValueError):
            parse_revision(VALID_SHA[:8])

    def test_reject_uppercase_revision(self):
        with self.assertRaises(ValueError):
            parse_revision(VALID_SHA.upper())

    def test_reject_invalid_characters(self):
        with self.assertRaises(ValueError):
            parse_revision("z" * 40)

    def test_read_revision_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pin"
            path.write_text(VALID_SHA + "\n", encoding="utf-8")
            self.assertEqual(read_revision(path), VALID_SHA)


if __name__ == "__main__":
    unittest.main()
