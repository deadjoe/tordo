# tordo

<p align="center">
  <img src="assets/tordo_logo.png" alt="tordo logo" width="200" height="200">
</p>

Tordo is an agent-facing Ableton Live control toolkit.

The project runs a MIDI Remote Script bridge inside Ableton Live and keeps agent workflow, planning, validation, and packaging in an external Python CLI. The product goal is to let an AI agent inspect, plan, and safely mutate a Live Set through a stable command-line and JSON-plan contract while avoiding stale index assumptions and accidental overwrites.

## Status

Tordo is in developer alpha. The core local control loop is working:

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

The current bridge source version is `TordoBridge 0.8.1`.

The intended stable contract is:

- `tordo` CLI commands plus explicit JSON plan documents.
- Runtime self-description through `tordo schema` and `tordo capabilities`.
- A packaged agent Skill, centered on `SKILL.md`, that teaches agents to use the same CLI/schema contract.

The current product path is Skill plus CLI. Other integration surfaces are intentionally out of scope until the core contract is clean and validated.

## Requirements

- macOS
- Ableton Live 12.4 Suite or newer
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

Run the full local environment diagnosis:

```bash
uv run tordo doctor
```

Check the bridge socket:

```bash
uv run tordo ping
```

Read the current Live Set:

```bash
uv run tordo snapshot
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
uv run tordo dev plan midi-file test_midi/axel_F.mid \
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
uv run tordo dev plan midi-file test_midi/rasputin.mid \
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
uv run tordo dev proof midi-import test_midi/rasputin.mid \
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

Ableton Live requires at least one regular track in a Set. If you are clearing or replacing a non-empty Set, create or keep a holder track before deleting all existing regular tracks; external preflight refuses plans that would delete the final regular track.

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
skills/tordo/                  Packaged agent Skill contract and resources
test_midi/                     Local MIDI test material
artifacts/tmp/                 Ignored runtime plans and prepared plans
exports/                       Ignored Live Set archives
```

## Design Boundaries

- Live does not hot-reload Remote Scripts. Bridge changes require a Live restart.
- Keep AI workflow, generation, analysis, preflight, packaging, and Skill logic outside Live.
- Keep the Live-side bridge stable and conservative. It currently owns the safe plan executor and Live API write semantics, so new write operations should be batched and justified.
- Never assume a previously observed track index is still correct.
- Resolve names from a fresh snapshot immediately before write operations.
- Dry-run destructive or large writes first.
- Do not overwrite existing clips implicitly.

## Known Limits

- Existing clip renaming is not yet exposed as a first-class operation.
- Existing object selectors still prefer unique names through `*_selector.name`. Duplicate track and scene names are refused by name; selector index plus `expected_name` can validate position but is not durable object identity. Same-track duplicate clip names require scene context.
- The current system is human-ear-in-the-loop. Tordo can inspect structure, notes, parameters, and diffs, but it does not hear audio quality by itself.
- Browser-backed sound selection is user-library dependent. Agent workflows must search available Browser items before using racks or presets in portable plans.
- Some Ableton Browser roots are not fully mapped yet, including `All`, `Modulators`, `Grooves`, `Tunings`, and `Templates`.
- `Plug-Ins` returned no items in the latest local browser query and needs a dedicated verification pass.
- Third-party plug-in internals are limited to parameters exposed through Live's automation model.

## More Detail

- [Bridge core](docs/bridge-core.md)
- [Capability map](docs/capability-map.md)
- [Agent contract](docs/agent-contract.md)
- [Contract validation](docs/contract-validation.md)
- [Bridge architecture](docs/bridge-architecture.md)
- [Human-ear-in-the-loop composition plan](docs/human-ear-in-the-loop-composition.md)
- [Handoff](docs/HANDOFF.md)
