import unittest
from pathlib import Path


class PublicReadmeTests(unittest.TestCase):
    def test_readme_has_public_user_developer_and_license_sections(self):
        content = Path("README.md").read_text()

        required_sections = [
            "## Features",
            "## End-User Installation",
            "## Developer Notes",
            "## License",
        ]
        for section in required_sections:
            self.assertIn(section, content)
        self.assertIn("Apache License, Version 2.0", content)
        self.assertIn("Add the Tordo skill from https://github.com/deadjoe/tordo/tree/main/skills/tordo", content)
        self.assertIn("approval, run `tordo doctor`", content)
        self.assertIn("Skill support differs by agent", content)
        self.assertIn("uv tool install tordo", content)
        self.assertIn("uv tool install git+https://github.com/deadjoe/tordo.git", content)

    def test_readme_uses_package_index_safe_logo_url_and_version_terms(self):
        content = Path("README.md").read_text()

        self.assertIn(
            'src="https://raw.githubusercontent.com/deadjoe/tordo/main/assets/tordo_logo.png"',
            content,
        )
        self.assertNotIn('src="assets/tordo_logo.png"', content)
        self.assertIn("The Python package version and Live bridge version are intentionally separate", content)
        self.assertIn("The package version is the CLI and Skill distribution version", content)
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

    def test_public_entrypoints_do_not_contain_chinese_text(self):
        public_files = [
            Path("README.md"),
            Path("index.html"),
            Path("pyproject.toml"),
            Path("LICENSE"),
        ]
        for path in public_files:
            self.assertNotRegex(path.read_text(), r"[\u4e00-\u9fff]", path)


if __name__ == "__main__":
    unittest.main()
