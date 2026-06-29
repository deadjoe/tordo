import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "tordo"


class SkillPackageTest(unittest.TestCase):
    def test_skill_frontmatter_is_agent_usable(self):
        content = (SKILL_DIR / "SKILL.md").read_text()
        match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = match.group(1)
        self.assertIn("name: tordo", frontmatter)
        description_line = next(line for line in frontmatter.splitlines() if line.startswith("description: "))
        description = description_line.removeprefix("description: ")
        self.assertIn("Ableton Live", description)
        self.assertIn("tordo CLI", description)
        self.assertLessEqual(len(description), 1024)
        self.assertNotIn("<", description)
        self.assertNotIn(">", description)

    def test_skill_references_exist(self):
        expected = {
            "references/contract.md",
            "references/workflows.md",
            "references/plan-schema.md",
            "references/troubleshooting.md",
            "scripts/doctor.py",
            "agents/openai.yaml",
        }
        for relative_path in expected:
            self.assertTrue((SKILL_DIR / relative_path).exists(), relative_path)

    def test_verified_envelope_and_brand_boundaries_are_explicit(self):
        content = (SKILL_DIR / "SKILL.md").read_text()
        self.assertIn("## Verified Envelope", content)
        self.assertIn("In scope: macOS, Ableton Live Suite `>=12.4`, Session View MIDI", content)
        self.assertIn("Out of scope: Windows, audio clip import, automation editing", content)
        self.assertIn("If `tordo` is not found", content)
        self.assertIn("ask the user before installing", content)
        self.assertIn("If a track or scene name is duplicated, stop and ask the human", content)
        self.assertIn("--no-cleanup-empty-project-tracks", content)
        self.assertIn("Live requires at least one regular track", content)
        self.assertIn("create a holder track first", content)
        self.assertIn("installed `packs` and `user_library`", content)
        self.assertIn("not affiliated with, authorized, sponsored, or endorsed by Ableton AG", content)

    def test_browser_workflow_surfaces_user_installed_resources(self):
        workflows = (SKILL_DIR / "references" / "workflows.md").read_text()
        schema = (SKILL_DIR / "references" / "plan-schema.md").read_text()
        contract = (SKILL_DIR / "references" / "contract.md").read_text()

        for content in (workflows, schema, contract):
            self.assertIn("packs", content)
            self.assertIn("user_library", content)
        self.assertIn("--root packs", workflows)
        self.assertIn("--include-folders", workflows)
        self.assertIn("Folder or pack nodes are useful for discovery but are not load targets", workflows)

    def test_first_time_acceptance_workflow_is_documented(self):
        skill = (SKILL_DIR / "SKILL.md").read_text()
        workflows = (SKILL_DIR / "references" / "workflows.md").read_text()

        self.assertIn("first-time setup, acceptance test", skill)
        self.assertIn("## First-Time Setup And Acceptance Test", workflows)
        self.assertIn("uv tool install tordo", workflows)
        self.assertIn("pipx install tordo", workflows)
        self.assertIn("tordo install-remote-script", workflows)
        self.assertIn("Tordo Acceptance", workflows)
        self.assertIn("First Write Check", workflows)
        self.assertIn("tordo apply-plan PLAN.json --prepared-out PREPARED.json", workflows)
        self.assertIn("tordo apply-plan PLAN.json --apply --prepared-out PREPARED-apply.json", workflows)
        self.assertIn("tordo set-notes --limit-per-clip 20", workflows)

    def test_skill_documents_return_and_master_mixer_targets(self):
        skill = (SKILL_DIR / "SKILL.md").read_text()
        schema = (SKILL_DIR / "references" / "plan-schema.md").read_text()
        contract = (SKILL_DIR / "references" / "contract.md").read_text()

        for content in (skill, schema, contract):
            self.assertIn("track_type=return", content)
            self.assertIn("track_type=master", content)
        self.assertIn("master track has no sends", schema)

    def test_troubleshooting_gives_cli_install_commands(self):
        troubleshooting = (SKILL_DIR / "references" / "troubleshooting.md").read_text()

        self.assertIn("Ask before installing or modifying the user's environment", troubleshooting)
        self.assertIn("uv tool install tordo", troubleshooting)
        self.assertIn("uv tool install git+https://github.com/deadjoe/tordo.git", troubleshooting)
        self.assertIn("pipx install", troubleshooting)
        self.assertIn("run `tordo doctor` again", troubleshooting)

    def test_openai_metadata_mentions_skill_token(self):
        content = (SKILL_DIR / "agents" / "openai.yaml").read_text()
        self.assertIn('display_name: "Tordo"', content)
        self.assertIn('default_prompt: "Use $tordo', content)

    def test_no_placeholder_or_removed_integration_terms(self):
        text_suffixes = {".md", ".py", ".yaml", ".yml"}
        combined = "\n".join(
            path.read_text() for path in SKILL_DIR.rglob("*") if path.is_file() and path.suffix in text_suffixes
        )
        self.assertNotIn("TODO", combined)
        self.assertNotIn("tordo-ableton", combined)
        self.assertNotIn("M" + "CP", combined)
        self.assertNotIn("m" + "cp", combined)


if __name__ == "__main__":
    unittest.main()
