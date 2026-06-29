import unittest
from pathlib import Path


class PublicReadmeTests(unittest.TestCase):
    def test_readme_uses_package_index_safe_logo_url_and_version_terms(self):
        content = Path("README.md").read_text()

        self.assertIn(
            'src="https://raw.githubusercontent.com/deadjoe/tordo/main/assets/tordo_logo.png"',
            content,
        )
        self.assertNotIn('src="assets/tordo_logo.png"', content)
        self.assertIn("The Python package version and Live bridge version are intentionally separate", content)
        self.assertIn("The package version is the CLI/Skill distribution version", content)
        self.assertIn("The bridge version is the Live-side Remote Script compatibility version checked", content)
        self.assertIn("by `tordo doctor`", content)

    def test_readme_does_not_link_internal_development_material(self):
        content = Path("README.md").read_text()

        forbidden = [
            "docs/",
            "test_midi",
            "HANDOFF",
            "contract-validation",
            "roadmap",
            "uv run tordo dev",
            "Release and TestPyPI preparation",
        ]
        for term in forbidden:
            self.assertNotIn(term, content)


if __name__ == "__main__":
    unittest.main()
