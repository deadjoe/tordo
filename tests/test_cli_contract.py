import contextlib
import io
import re
import unittest
from pathlib import Path

from tordo.cli import STABLE_COMMANDS, main


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

    def test_agent_contract_lists_stable_agent_commands(self):
        contract = Path("docs/agent-contract.md").read_text()
        commands = set(agent_usable_commands(contract))
        expected = set(STABLE_COMMANDS) - {"dev"}

        self.assertEqual(commands, expected)


def help_output(argv):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        with self_exit_code(0):
            main(argv)
    return stdout.getvalue()


def agent_usable_commands(contract):
    marker = "Current agent-usable commands:"
    start = contract.index(marker) + len(marker)
    end = contract.index("Repository examples", start)
    section = contract[start:end]
    commands = []
    for match in re.finditer(r"`uv run tordo ([^`\s]+)", section):
        commands.append(match.group(1))
    return commands


@contextlib.contextmanager
def self_exit_code(expected):
    try:
        yield
    except SystemExit as exc:
        if exc.code != expected:
            raise


if __name__ == "__main__":
    unittest.main()
