import tempfile
import unittest
from pathlib import Path

from tordo.remote_install import install_remote_script, source_bridge_version


class RemoteInstallTests(unittest.TestCase):
    def test_source_bridge_version_is_available(self):
        self.assertEqual(source_bridge_version(), "0.8.1")

    def test_install_remote_script_copies_bridge_into_user_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = install_remote_script(tmp)

            target = Path(tmp) / "Remote Scripts" / "TordoBridge" / "bridge.py"
            self.assertTrue(report["ok"])
            self.assertEqual(report["installed_version_after"], "0.8.1")
            self.assertTrue(target.exists())
            self.assertIn("BRIDGE_VERSION = \"0.8.1\"", target.read_text())

    def test_install_remote_script_dry_run_does_not_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = install_remote_script(tmp, dry_run=True)

            target = Path(tmp) / "Remote Scripts" / "TordoBridge"
            self.assertTrue(report["ok"])
            self.assertTrue(report["dry_run"])
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
