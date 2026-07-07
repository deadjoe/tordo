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

Mixer targets can be regular tracks, return tracks, or the master track when `tordo schema` reports support:

```json
{
  "plan_version": 1,
  "name": "shape-shared-space",
  "operations": [
    {
      "type": "set_track_mixer",
      "track_type": "return",
      "track_selector": {"name": "A-Reverb"},
      "volume": 0.65
    },
    {
      "type": "set_track_mixer",
      "track_type": "master",
      "track_selector": {"name": "Main"},
      "volume": 0.82
    }
  ]
}
```

Use `track_type=return` for return-track sends, volume, and panning. Use `track_type=master` for master volume and panning only; the master track has no sends.

Return-track behaviors verified in Live 12.4: `create_return_track` always appends (an `index` other than the append position is refused), and Live prefixes return-track names with a positional letter — a track created as `Tordo Return` reads back as `C-Tordo Return`, and the letter shifts when return tracks are added, removed, or reordered. Always select return tracks by the name shown in a fresh `tordo snapshot`.

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
tordo browser-items --root packs --include-folders --max-depth 2 --max-results 80
tordo browser-items --root packs --query "orchestral" --include-folders --max-depth 5
tordo browser-items --root user_library --include-folders --max-depth 4 --max-results 80
tordo browser-items --root current_project --include-folders --max-depth 4 --max-results 80
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

Do not invent Browser URIs or assume pack names are portable. `packs`, `user_library`, and `current_project` are user-specific discovery roots; inspect them before choosing sounds when the task depends on the user's installed resources.

## Global Song Properties

`set_signature` and `set_scale` are available when `tordo schema` lists them (bridge `0.9.0+`):

```json
{
  "plan_version": 1,
  "name": "set-song-context",
  "operations": [
    {"type": "set_signature", "numerator": 6, "denominator": 8},
    {"type": "set_scale", "root_note": 2, "scale_name": "Minor", "scale_mode": true}
  ]
}
```

`root_note` is a pitch class from 0 (C) to 11 (B). Read the current key back from the `song` section of `tordo snapshot` before generating notes; prefer the user's configured key over guessing.

## Edit Clip Loop, Name, And Color

`set_clip_loop` writes loop and marker positions in beats; `set_clip_properties` renames and recolors:

```json
{
  "plan_version": 1,
  "name": "tighten-loop",
  "operations": [
    {
      "type": "set_clip_loop",
      "track_selector": {"name": "Bass"},
      "clip_selector": {"name": "Loop"},
      "looping": true,
      "loop_start": 0.0,
      "loop_end": 8.0
    },
    {
      "type": "set_clip_properties",
      "track_selector": {"name": "Bass"},
      "clip_selector": {"name": "Loop"},
      "name": "Bass Loop 8bar",
      "color": 13016944
    }
  ]
}
```

Renaming a clip, scene, or track invalidates name selectors later in the same plan; rename last, or re-run `tordo snapshot` and use a follow-up plan. `set_scene_properties` and the `color` field on `set_track_state` follow the same pattern. Colors are integer RGB values; Live snaps them to its palette.

## Undo And Redo

`undo` and `redo` operate on Live's own history and need no selectors:

```json
{
  "plan_version": 1,
  "name": "undo-last-write",
  "operations": [{"type": "undo"}]
}
```

Use `undo` as a recovery tool after a verified-wrong apply, then re-check state with `tordo snapshot`. Two verified Live behaviors make undo a blunt instrument:

- Live can coalesce consecutive bridge writes into a single undo step. One `undo` may revert every plan applied since the last human interaction, not just the last operation. `redo` restores the coalesced step the same way.
- Live's history also contains the human's manual edits.

Always take a fresh `tordo snapshot` after `undo` or `redo` and verify the actual state before planning anything else.

## Destructive Operations

Deleting tracks, scenes, or devices must be explicit:

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

`delete_device` also requires `allow_destructive: true` plus a `device_index` and an optional `device_name` assertion:

```json
{
  "plan_version": 1,
  "name": "remove-wrong-device",
  "operations": [
    {
      "type": "delete_device",
      "track_selector": {"name": "Lead"},
      "device_index": 1,
      "device_name": "Auto Filter",
      "allow_destructive": true
    }
  ]
}
```

Ask the human before destructive edits unless the current request is already an explicit delete request.
Live also requires at least one regular track at every step; create or keep a holder regular track before deleting all existing regular tracks.
