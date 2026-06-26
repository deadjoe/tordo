# tordo

<p align="center">
  <img src="assets/tordo_logo.png" alt="tordo logo" width="200" height="200">
</p>

Tordo is an agent-friendly Ableton Live control experiment.

The project runs a thin MIDI Remote Script inside Ableton Live and keeps the fast-changing logic in an external Python CLI. The goal is to let an AI coding agent inspect, plan, and safely mutate a Live Set while avoiding stale index assumptions and accidental overwrites.

## Status

This is an early lab project, but the core loop is working:

- Read the current Live Set structure, tracks, scenes, clips, devices, mixer state, and MIDI notes.
- Generate explicit JSON plans outside Live.
- Dry-run plans before writing.
- Resolve human-facing names to current Live indices immediately before apply.
- Guard write operations with expected track, scene, clip, device, and parameter names.
- Create tracks, scenes, MIDI clips, and notes.
- Load Ableton Browser items such as racks and presets.
- Insert native Live devices.
- Adjust track mixer values, sends, and device parameters.
- Modify MIDI notes by `note_id`.
- Export snapshots and note archives for offline analysis and diffing.

The current bridge source version is `TordoBridge 0.8.0`.

## Requirements

- macOS
- Ableton Live 12.4 Suite
- Python 3.11+
- `uv`

## Install

Install Python dependencies:

```bash
uv sync
```

Install the Ableton Remote Script into the user library:

```bash
uv run python tools/install_remote_script.py
```

Restart Ableton Live, then select this control surface:

```text
Settings -> Link, Tempo & MIDI -> Control Surface -> TordoBridge
```

Input and Output can stay set to `None`.

## Basic Checks

Check that the bridge is reachable:

```bash
uv run tordo bridge doctor
uv run tordo bridge ping
```

Read the current Live Set:

```bash
uv run tordo bridge snapshot
```

Search Live Browser items:

```bash
uv run tordo browser-items --root sounds --query "Antenna Lead"
uv run tordo browser-items --root audio_effects --query "Auto Filter"
```

## Plans

Plans are JSON documents applied through `apply-plan`.

Dry-run first:

```bash
uv run tordo apply-plan artifacts/tmp/example-plan.json \
  --prepared-out artifacts/tmp/example-prepared-dry-run.json
```

Apply after inspection:

```bash
uv run tordo apply-plan artifacts/tmp/example-plan.json \
  --apply \
  --prepared-out artifacts/tmp/example-prepared-apply.json \
  --timeout 120
```

For existing Live objects, prefer exact names over hard-coded indices:

```json
{
  "plan_version": 1,
  "name": "shape-main-hook",
  "operations": [
    {
      "type": "set_device_parameter",
      "track_name": "Main Hook - Axel F",
      "device_index": 0,
      "device_name": "Antenna Lead",
      "parameter_index": 6,
      "parameter_name": "Echo",
      "value": 8.0
    }
  ]
}
```

The CLI resolves names to current indices from a fresh snapshot, then adds expected-name guards before the plan reaches Live.

## MIDI Import

Put local MIDI test files in `test_midi/`.

Generate a role-based import plan:

```bash
uv run tordo plan midi-file test_midi/axel_F.mid \
  --prefix "Axel F" \
  --scene-name "Axel F Full" \
  --out artifacts/tmp/axel-f-plan.json
```

Apply it:

```bash
uv run tordo apply-plan artifacts/tmp/axel-f-plan.json \
  --apply \
  --prepared-out artifacts/tmp/axel-f-prepared-apply.json \
  --timeout 180
```

For larger MIDI files, split note writes into chunk plans so each bridge request stays small:

```bash
uv run tordo plan midi-file test_midi/rasputin.mid \
  --prefix "Rasputin" \
  --scene-name "Rasputin Full" \
  --tempo 122 \
  --time-scale 1.0 \
  --out artifacts/tmp/rasputin-structure-plan.json \
  --split-notes-dir artifacts/tmp/rasputin-note-chunks \
  --note-chunk-size 900
```

Run the same flow as an end-to-end proof:

```bash
uv run tordo proof midi-import test_midi/rasputin.mid \
  --prefix "Rasputin" \
  --scene-name "Rasputin Full" \
  --tempo 122 \
  --time-scale 1.0 \
  --note-chunk-size 900 \
  --work-dir artifacts/tmp/proofs/rasputin \
  --export-out exports/rasputin-proof \
  --replace-existing \
  --overwrite \
  --timeout 180 \
  --limit-per-clip 20000
```

The proof command writes plans, prepared plans, bridge responses, a proof report, a Live export archive, and a per-clip note tuple diff.

When a Live Set contains only default empty tracks and an import plan appends new tracks, `apply-plan` appends cleanup operations for default empty tracks such as `1-MIDI`, `2-MIDI`, `3-Audio`, and `4-Audio`. Disable this with:

```bash
uv run tordo apply-plan artifacts/tmp/axel-f-plan.json \
  --no-cleanup-empty-project-tracks
```

## Export And Analyze

Export the current Live Set into an archive:

```bash
uv run tordo export --out exports/current --limit-per-clip 10000
```

Analyze notes:

```bash
uv run tordo analyze exports/current/set-notes.json \
  --json-out artifacts/tmp/current-analysis.json \
  --md-out artifacts/tmp/current-analysis.md
```

Diff two exports:

```bash
uv run tordo diff exports/before exports/after
```

## Project Layout

```text
tordo/                 External Python CLI and planning logic
remote-script/TordoBridge/
                               Thin Live-side Remote Script bridge
tools/install_remote_script.py Remote Script installer
docs/                          Design notes and handoff material
test_midi/                     Local MIDI test material
artifacts/tmp/                 Ignored runtime plans and prepared plans
exports/                       Ignored Live Set archives
```

## Design Boundaries

- Live does not hot-reload Remote Scripts. Bridge changes require a Live restart.
- Keep the Live-side bridge thin and stable.
- Put experiments, generation, analysis, preflight, and agent adapters outside Live.
- Never assume a previously observed track index is still correct.
- Resolve names from a fresh snapshot immediately before write operations.
- Dry-run destructive or large writes first.
- Do not overwrite existing clips implicitly.

## Known Limits

- Existing clip renaming is not yet exposed as a first-class operation.
- Some Ableton Browser roots are not fully mapped yet, including `All`, `Modulators`, `Grooves`, `Tunings`, and `Templates`.
- `Plug-Ins` returned no items in the latest local browser query and needs a dedicated verification pass.
- Third-party plug-in internals are limited to parameters exposed through Live's automation model.

## More Detail

- [Bridge core](docs/bridge-core.md)
- [Capability map](docs/capability-map.md)
- [Closed-loop composition plan](docs/closed-loop-composition-plan.md)
- [Handoff](docs/HANDOFF.md)
