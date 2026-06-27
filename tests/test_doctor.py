import tempfile
import unittest
from pathlib import Path

from tordo.doctor import bridge_version_from_source, version_at_least, version_tuple


class DoctorTests(unittest.TestCase):
    def test_version_tuple_parses_live_version_suffix(self):
        self.assertEqual(version_tuple("12.4 (2026-04-24_d85a94ab5e)"), (12, 4))

    def test_version_at_least_compares_numeric_parts(self):
        self.assertTrue(version_at_least("12.4 (build)", "12.4"))
        self.assertTrue(version_at_least("12.4.1", "12.4"))
        self.assertFalse(version_at_least("12.3.9", "12.4"))

    def test_bridge_version_from_source_reads_ast_constant(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bridge.py"
            path.write_text('BRIDGE_VERSION = "9.8.7"\n')
            self.assertEqual(bridge_version_from_source(path), "9.8.7")


if __name__ == "__main__":
    unittest.main()
