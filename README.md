# tordo

<p align="center">
  <img src="https://raw.githubusercontent.com/deadjoe/tordo/main/assets/tordo_logo.png" alt="tordo logo" width="200" height="200">
</p>

Tordo is an agent-facing Ableton Live control toolkit.

It runs a small MIDI Remote Script bridge inside Ableton Live and keeps planning,
validation, packaging, and agent workflow in an external Python CLI. The goal is
to let an AI agent inspect, plan, dry-run, apply, and verify safe changes to a
Live Set through an explicit command-line and JSON-plan contract.

Tordo is in developer alpha.

## What It Can Do

- Inspect tracks, scenes, clips, devices, mixer state, Browser items, and MIDI notes.
- Generate explicit JSON plans outside Live.
- Dry-run plans before writing.
- Resolve names against a fresh snapshot immediately before apply.
- Guard write operations with expected track, scene, clip, device, and parameter names.
- Create tracks, scenes, MIDI clips, and notes.
- Load discovered Ableton Browser items such as racks and presets.
- Insert native Live devices.
- Adjust track, return, and master mixer values where supported by the runtime schema.
- Modify MIDI notes by `note_id`.
- Export snapshots and note archives for offline analysis and diffing.

## Requirements

- macOS
- Ableton Live 12.4 Suite or newer
- Python 3.11+
- `uv`, `pipx`, or another Python CLI installer

## Install

Published package install:

```bash
uv tool install tordo
```

Current alpha source install:

```bash
uv tool install git+https://github.com/deadjoe/tordo.git
```

After the `tordo` CLI is available on `PATH`, install the Ableton Remote Script
into your Ableton User Library:

```bash
tordo install-remote-script
```

Restart Ableton Live, then select this control surface:

```text
Settings -> Link, Tempo & MIDI -> Control Surface -> TordoBridge
```

Input and Output can stay set to `None`.

## Check The Setup

Run the full local environment diagnosis:

```bash
tordo doctor
```

Check the bridge socket:

```bash
tordo ping
```

Read the current Live Set:

```bash
tordo snapshot
```

Ask what the installed runtime supports:

```bash
tordo schema
tordo capabilities
```

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

For existing Live objects, prefer exact names over hard-coded indices:

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

## Agent Skill

The first agent-facing Skill lives in `skills/tordo/`. It teaches an AI agent to
use the installed `tordo` CLI, inspect runtime capabilities, dry-run before
apply, discover user-installed Browser resources before choosing sounds, and ask
for human listening feedback when a decision depends on musical taste.

## Versioning

The Python package version and Live bridge version are intentionally separate:

- The package version is the CLI/Skill distribution version shown by PyPI and
  TestPyPI.
- The bridge version is the Live-side Remote Script compatibility version checked
  by `tordo doctor`.

The current bridge source version is `TordoBridge 0.8.1`.

## Safety Boundaries

- Never assume a previously observed track index is still correct.
- Resolve names from a fresh snapshot immediately before write operations.
- Dry-run destructive or large writes first.
- Do not overwrite existing clips implicitly.
- Do not delete tracks or scenes without explicit destructive permission.
- Do not delete the final regular track in a Live Set.
- Treat installed Packs, User Library, and Current Project Browser contents as
  user-specific resources that must be discovered before use.
- Tordo is human-ear-in-the-loop: it can inspect and edit project state, but it
  cannot hear or judge audio quality by itself.

## Trademark Notice

Tordo is an independent project and is not affiliated with, authorized,
sponsored, or endorsed by Ableton AG. Ableton and Live are trademarks of Ableton
AG.
