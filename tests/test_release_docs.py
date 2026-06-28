import unittest
from pathlib import Path


class ReleaseDocsTests(unittest.TestCase):
    def test_release_checklist_contains_packaging_and_testpypi_gates(self):
        content = Path("docs/release.md").read_text()

        self.assertIn("uv build", content)
        self.assertIn("tools/check_package_artifacts.py", content)
        self.assertIn("uv publish --dry-run --trusted-publishing never", content)
        self.assertIn("--publish-url https://test.pypi.org/legacy/", content)
        self.assertIn("--extra-index-url https://pypi.org/simple/", content)
        self.assertIn("clean-environment acceptance test", content)


if __name__ == "__main__":
    unittest.main()
