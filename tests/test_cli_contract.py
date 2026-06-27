import contextlib
import io
import unittest

from tordo.cli import main


class CliContractTests(unittest.TestCase):
    def test_top_level_help_lists_stable_commands_only(self):
        output = help_output(["--help"])

        self.assertIn("doctor", output)
        self.assertIn("capabilities", output)
        self.assertIn("snapshot", output)
        self.assertIn("apply-plan", output)
        self.assertIn("dev", output)
        self.assertNotIn("delete-tracks-by-name", output)
        self.assertNotIn("verify-note-metadata", output)
        self.assertNotIn("==SUPPRESS==", output)

    def test_dev_namespace_forwards_legacy_plan_help(self):
        output = help_output(["dev", "plan", "midi-file", "--help"])

        self.assertIn("usage: tordo dev plan midi-file", output)
        self.assertIn("--split-notes-dir", output)


def help_output(argv):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        with self_exit_code(0):
            main(argv)
    return stdout.getvalue()


@contextlib.contextmanager
def self_exit_code(expected):
    try:
        yield
    except SystemExit as exc:
        if exc.code != expected:
            raise


if __name__ == "__main__":
    unittest.main()
