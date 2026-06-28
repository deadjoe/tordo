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


if __name__ == "__main__":
    unittest.main()
