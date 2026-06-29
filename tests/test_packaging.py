import tomllib
import unittest
from pathlib import Path


class PackagingConfigTests(unittest.TestCase):
    def test_wheel_force_includes_remote_script_source(self):
        pyproject = tomllib.loads(Path("pyproject.toml").read_text())
        force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

        self.assertEqual(
            force_include["remote-script/TordoBridge"],
            "tordo/remote_assets/TordoBridge",
        )

    def test_sdist_public_surface_is_explicitly_scoped(self):
        pyproject = tomllib.loads(Path("pyproject.toml").read_text())
        include = set(pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])

        self.assertEqual(
            include,
            {
                "/LICENSE",
                "/README.md",
                "/pyproject.toml",
                "/remote-script/TordoBridge",
                "/tordo",
            },
        )

    def test_package_declares_apache_license(self):
        pyproject = tomllib.loads(Path("pyproject.toml").read_text())
        project = pyproject["project"]

        self.assertEqual(project["license"], "Apache-2.0")
        self.assertIn("License :: OSI Approved :: Apache Software License", project["classifiers"])


if __name__ == "__main__":
    unittest.main()
