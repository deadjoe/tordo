# tordo

<p align="center">
  <img src="https://raw.githubusercontent.com/deadjoe/tordo/main/assets/tordo_logo.png" alt="tordo logo" width="200" height="200">
</p>

Tordo is an agent-facing Ableton Live control toolkit. It gives an AI agent a
stable CLI and JSON-plan contract for inspecting, planning, dry-running,
applying, and verifying safe changes inside a Live Set.

Tordo is in developer alpha.

## Features

- Inspect tracks, scenes, clips, devices, mixer state, Browser items, and MIDI notes.
- Create tracks, scenes, MIDI clips, and notes through explicit JSON plans.
- Dry-run plans before writing to Ableton Live.
- Resolve names against a fresh snapshot before apply to reduce stale-index mistakes.
- Guard writes with expected track, scene, clip, device, and parameter names.
- Load discovered Browser items such as racks and presets.
- Insert native Live devices and adjust supported mixer and device parameters.
- Export snapshots and note archives for offline analysis and diffing.
- Keep musical judgment human-ear-in-the-loop: Tordo can edit state, but it does not hear audio quality.

## Requirements

- macOS
- Ableton Live 12.4 Suite or newer
- Python 3.11+
- `uv`, `pipx`, or another Python CLI installer

## End-User Installation

Recommended setup is agent-led:

1. Open a skill-capable AI agent, such as Claude, Claude Code, Codex, or another
   assistant that can install or read agent skills from a public GitHub repo.
2. Paste this request:

   ```text
   Add the Tordo skill from https://github.com/deadjoe/tordo/tree/main/skills/tordo,
   then set it up for Ableton Live on this Mac and check everything works.
   ```

3. Let the agent inspect the Skill, install or expose the `tordo` CLI with your
   approval, run `tordo doctor`, install the Ableton Remote Script, and guide you
   through the required Ableton Live restart and Control Surface selection.

After setup, open a Live Set and ask the agent for the musical change you want.
Tordo previews changes before applying them.

Skill support differs by agent. If your agent cannot install a Skill directly
from GitHub, clone this repository and point the agent at `skills/tordo/`.

Manual CLI setup is also available. For normal use, install the released CLI
from PyPI:

```bash
uv tool install tordo
```

Install the Ableton Remote Script into your Ableton User Library:

```bash
tordo install-remote-script
```

Restart Ableton Live, then select this control surface:

```text
Settings -> Link, Tempo & MIDI -> Control Surface -> TordoBridge
```

Input and Output can stay set to `None`.

Check the setup:

```bash
tordo doctor
tordo ping
tordo snapshot
tordo schema
tordo capabilities
```

## Agent Skill

The first agent-facing Skill lives in `skills/tordo/`.

Give a compatible AI agent this Skill path:

```text
https://github.com/deadjoe/tordo/tree/main/skills/tordo
```

The Skill teaches the agent to:

- check whether the local `tordo` CLI is installed
- propose a `tordo` CLI install command and ask before running it
- run `tordo doctor`, `tordo schema`, and `tordo capabilities`
- install the `TordoBridge` Remote Script into Ableton Live
- discover installed Packs, User Library, and Current Project Browser resources
- dry-run every plan before apply
- verify changes after apply
- ask for human listening feedback when a decision depends on musical taste

## Basic Plan Flow

Plans are JSON documents applied through `apply-plan`.

Dry-run first:

```bash
tordo apply-plan plan.json --prepared-out prepared-dry-run.json
```

Apply only after inspection:

```bash
tordo apply-plan plan.json --apply --prepared-out prepared-apply.json --timeout 120
```

Example operation:

```json
{
  "plan_version": 1,
  "name": "shape-main-hook",
  "operations": [
    {
      "type": "set_device_parameter",
      "track_name": "Main Hook",
      "device_index": 0,
      "device_name": "Antenna Lead",
      "parameter_index": 6,
      "parameter_name": "Echo",
      "value": 8.0
    }
  ]
}
```

The CLI resolves names to current indices from a fresh snapshot, then adds
expected-name guards before the plan reaches Live.

## Safety Boundaries

- Never assume a previously observed track index is still correct.
- Resolve names from a fresh snapshot immediately before write operations.
- Dry-run destructive or large writes first.
- Do not overwrite existing clips implicitly.
- Do not delete tracks or scenes without explicit destructive permission.
- Do not delete the final regular track in a Live Set.
- Treat installed Packs, User Library, and Current Project Browser contents as
  user-specific resources that must be discovered before use.

## Developer Notes

Set up a local checkout:

```bash
uv sync --dev --frozen
```

Run the local quality gates:

```bash
uv run ruff check .
uv run python tools/check_operation_registry.py
uv run python -m unittest discover -s tests -p 'test*.py'
uv run python -m py_compile tordo/*.py remote-script/TordoBridge/bridge.py tools/*.py tests/*.py skills/tordo/scripts/*.py
```

Build and validate package artifacts:

```bash
rm -rf dist
uv build
uv run python tools/check_package_artifacts.py
uv publish --dry-run --trusted-publishing never dist/*
```

The wheel contains the Python CLI plus the packaged `TordoBridge` Remote Script
source. The sdist is intentionally scoped to public release files and excludes
non-release development materials, local test material, and runtime artifacts.

## Versioning

The Python package version and Live bridge version are intentionally separate:

- The package version is the CLI and Skill distribution version shown by PyPI.
- The bridge version is the Live-side Remote Script compatibility version checked
  by `tordo doctor`.

The current bridge source version is `TordoBridge 0.8.1`.

## License

Tordo is licensed under the Apache License, Version 2.0. See `LICENSE`.

## Trademark Notice

Tordo is an independent project and is not affiliated with, authorized,
sponsored, or endorsed by Ableton AG. Ableton and Live are trademarks of Ableton
AG.
