import unittest
from pathlib import Path


class ReleaseDocsTests(unittest.TestCase):
    def test_readme_uses_package_index_safe_logo_url_and_version_terms(self):
        content = Path("README.md").read_text()

        self.assertIn(
            'src="https://raw.githubusercontent.com/deadjoe/tordo/main/assets/tordo_logo.png"',
            content,
        )
        self.assertNotIn('src="assets/tordo_logo.png"', content)
        self.assertIn("The Python package version and Live bridge version are intentionally separate", content)
        self.assertIn("The package version is the CLI/Skill distribution version shown by PyPI and TestPyPI", content)
        self.assertIn(
            "The bridge version is the Live-side Remote Script compatibility version checked by `tordo doctor`",
            content,
        )

    def test_release_checklist_contains_packaging_and_testpypi_gates(self):
        content = Path("docs/release.md").read_text()

        self.assertIn("uv build", content)
        self.assertIn("tools/check_package_artifacts.py", content)
        self.assertIn("uv publish --dry-run --trusted-publishing never", content)
        self.assertIn("--publish-url https://test.pypi.org/legacy/", content)
        self.assertIn("--extra-index-url https://pypi.org/simple/", content)
        self.assertIn("project name is available on both PyPI and TestPyPI", content)
        self.assertIn("Use absolute URLs for README images", content)
        self.assertIn("README renders correctly", content)
        self.assertIn("Package version and bridge version are separate", content)
        self.assertIn("Package indexes do not allow replacing an already uploaded release file", content)
        self.assertIn("clean-environment acceptance test", content)


if __name__ == "__main__":
    unittest.main()
