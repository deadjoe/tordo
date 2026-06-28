# Tordo Plan Schema Reference

Run `tordo schema` before writing plans. This file gives patterns, not the final source of truth.

## Plan Shape

```json
{
  "plan_version": 1,
  "name": "short-plan-name",
  "operations": []
}
```

Use concise plan names. Keep operation count below `tordo capabilities` limits.

## Selectors

Prefer structured selectors:

```json
{"track_selector": {"name": "Lead"}}
{"track_selector": {"index": 4, "expected_name": "Bass"}}
{"scene_selector": {"name": "Hook"}}
{"scene_selector": {"index": 8, "expected_name": "Hook"}}
{"clip_selector": {"name": "Loop"}}
```

Rules:

- Use `selector.name` only when the name is unique.
- Use `selector.index + selector.expected_name` only to validate current position.
- Use scene context for same-track duplicate clip names.
- Use `track_ref`, `scene_ref`, and `clip_ref` for objects created earlier in the same plan.
- Do not mix conflicting top-level selector fields and structured selector fields.

## Create A MIDI Clip With Notes

```json
{
  "plan_version": 1,
  "name": "create-short-midi-clip",
  "operations": [
    {
      "id": "track.lead",
      "type": "create_midi_track",
      "index": -1,
      "name": "Lead"
    },
    {
      "id": "scene.main",
      "type": "create_scene",
      "index": -1,
      "name": "Main"
    },
    {
      "id": "clip.lead",
      "type": "create_midi_clip",
      "track_ref": "track.lead",
      "scene_ref": "scene.main",
      "length": 4.0,
      "name": "Lead Motif"
    },
    {
      "type": "add_notes",
      "clip_ref": "clip.lead",
      "notes": [
        {"pitch": 60, "start_time": 0.0, "duration": 0.5, "velocity": 96},
        {"pitch": 64, "start_time": 0.5, "duration": 0.5, "velocity": 92},
        {"pitch": 67, "start_time": 1.0, "duration": 1.0, "velocity": 98}
      ]
    }
  ]
}
```

## Edit An Existing Target

```json
{
  "plan_version": 1,
  "name": "lower-lead-volume",
  "operations": [
    {
      "type": "set_track_mixer",
      "track_selector": {"name": "Lead"},
      "volume": 0.72
    }
  ]
}
```

The CLI preflight resolves the current index from a fresh snapshot and adds expected-name guards before the bridge sees the plan.

## Use Scene Context For A Clip

```json
{
  "plan_version": 1,
  "name": "quantize-loop-in-hook",
  "operations": [
    {
      "type": "quantize_clip",
      "track_selector": {"name": "Bass"},
      "scene_selector": {"name": "Hook"},
      "clip_selector": {"name": "Loop"},
      "quantization_grid": 5
    }
  ]
}
```

If `Bass` or `Hook` is duplicated, stop and ask for target confirmation.

## Load A Browser Item

Search first:

```bash
tordo browser-items --root instruments --query "piano"
```

Use a returned loadable item:

```json
{
  "plan_version": 1,
  "name": "load-discovered-sound",
  "operations": [
    {
      "type": "load_browser_item",
      "track_selector": {"name": "Keys"},
      "browser_uri": "RETURNED_URI_FROM_THIS_USER_LIBRARY"
    }
  ]
}
```

Do not invent Browser URIs or assume pack names are portable.

## Destructive Operations

Deleting tracks or scenes must be explicit:

```json
{
  "plan_version": 1,
  "name": "delete-confirmed-track",
  "operations": [
    {
      "type": "delete_track",
      "track_selector": {"index": 3, "expected_name": "Scratch"},
      "allow_destructive": true
    }
  ]
}
```

Ask the human before destructive edits unless the current request is already an explicit delete request.
Live also requires at least one regular track at every step; create or keep a holder regular track before deleting all existing regular tracks.
