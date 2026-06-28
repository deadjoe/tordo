# Tordo Contract Reference

Use this reference for the exact first-version Skill contract. Runtime truth still comes from `tordo schema`, `tordo capabilities`, and `tordo doctor`.

## Stable Surface

The stable agent contract is:

```text
tordo CLI + explicit JSON plan schema
```

Use top-level stable CLI commands:

- `tordo doctor`
- `tordo schema`
- `tordo capabilities`
- `tordo ping`
- `tordo selected`
- `tordo selected-notes`
- `tordo snapshot`
- `tordo set-notes`
- `tordo clip-notes`
- `tordo browser-items`
- `tordo apply-plan`
- `tordo export`
- `tordo analyze`
- `tordo diff`

Treat `tordo dev ...`, hidden legacy proof aliases, and the raw bridge socket as outside the agent-stable contract.

## Runtime Detection

Run `tordo doctor` first. It reports whether:

- the `tordo` CLI is installed and on `PATH`
- Python and the package are importable
- Ableton Live is installed
- Ableton Live version is `>=12.4`
- the `TordoBridge` Remote Script is installed
- Ableton Live is running when runtime control is needed
- the bridge is reachable on `127.0.0.1:8765`
- bridge version and plan operations are compatible

If `tordo doctor` fails, explain the failed checks and stop before writing.

## Scope

In scope for the first Skill:

- Session View MIDI clips
- creating MIDI tracks, scenes, MIDI clips, and MIDI notes
- modifying, removing, quantizing, cropping, and duplicating MIDI clips/notes when supported by `capabilities`
- track state, mixer volume/pan/sends, return tracks, and native device parameters
- native Live device insertion and Browser item loading after Browser discovery, including installed Packs (`packs`), User Library (`user_library`), and Current Project (`current_project`) resources exposed by Live
- group/foldable track presence with fresh snapshot index validation
- human-ear-in-the-loop editing

Out of scope for the first Skill:

- Windows support
- audio clip import
- automation editing
- durable object identity for duplicate track or scene names
- direct third-party plug-in internals beyond parameters exposed by Live
- claiming to hear or judge audio quality without human feedback

## Selector Limits

Unique names are preferred. Duplicate track and scene names are refused by name. `index + expected_name` validates current position but does not prove durable identity. If same-named tracks or scenes could have been reordered, ask the human before editing.

Duplicate clip names on one track require scene context through `scene_selector`, `scene_name`, or `scene_index`.

## Trademark Notice

Tordo is an independent project and is not affiliated with, authorized, sponsored, or endorsed by Ableton AG. Ableton and Live are trademarks of Ableton AG.
