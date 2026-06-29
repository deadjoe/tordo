# Tordo Troubleshooting

Use this when commands fail. Prefer reporting exact failed checks and next actions.

## `tordo` Is Not Found

Tell the user that the CLI is not on `PATH`. Do not attempt Live writes.

Ask before installing or modifying the user's environment. Suggested install commands:

```bash
uv tool install tordo
```

For the current alpha source install before a PyPI release is available:

```bash
uv tool install git+https://github.com/deadjoe/tordo.git
```

If the user prefers `pipx`, use the same package target with `pipx install`.

If working from a repository checkout, use `uv run tordo ...` instead of requiring a global CLI. After installation or PATH changes, run `tordo doctor` again.

## Ableton Live Is Missing Or Too Old

Tordo first targets macOS with Ableton Live Suite `>=12.4`. If `doctor` reports an older version or missing app, stop and explain the requirement.

## Remote Script Missing Or Version Mismatch

If `TordoBridge` is missing or the bridge version differs from the package:

1. Run `tordo install-remote-script`.
2. Tell the user to restart Ableton Live.
3. Tell the user to select `TordoBridge` in Live Settings -> Link, Tempo & MIDI -> Control Surface.
4. Run `tordo doctor` again.

Do not keep retrying writes against a missing or mismatched bridge. The CLI can copy the Remote Script, but it cannot restart Live or select the Control Surface for the user.

## Bridge Not Reachable

Check:

- Ableton Live is running.
- `TordoBridge` is selected as a Control Surface.
- Live was restarted after installing or updating the Remote Script.
- No other process is blocking `127.0.0.1:8765`.

Run `tordo ping` after the user fixes the issue.

## Ambiguous Names

If preflight says a track, scene, or clip name is not unique:

- For track or scene names, stop and ask the human for the exact target.
- For clip names, add scene context when possible.
- Do not guess from order, visual position, or previous snapshots.

## Stale Snapshot Or Expected-Name Guard Failure

If a dry-run or apply fails with an expected-name mismatch, the Live Set changed after the plan was prepared. Read a fresh `tordo snapshot`, rebuild the plan, dry-run again, and only then apply.

## Existing Clip Refusal

Tordo refuses implicit clip overwrite. Choose an empty slot, ask the user whether to delete/rename the existing clip, or use supported note-edit operations on the existing clip.

## Empty Default Tracks Disappeared In Dry-Run

On a default empty Live Set, `apply-plan` may append cleanup operations for default empty tracks after a creation plan appends new tracks. This is normal and prevents generated projects from keeping unused defaults. If the user wants to keep those tracks, rerun dry-run and apply with `--no-cleanup-empty-project-tracks`.

## Cannot Delete The Last Regular Track

Live requires at least one regular track in every Set. If preflight refuses with `last regular track`, or apply reports that it could not delete a final track, rebuild the plan so it creates or keeps a holder regular track before deleting old tracks. Delete the holder only after another regular track exists.

## Browser Item Not Found

Browser content differs by user and installed packs. Search with `tordo browser-items` and select a returned loadable item. If no match exists, fall back to native devices or uninstrumented MIDI.

## Plan Too Large

Check `tordo capabilities` limits. Split large note writes into multiple plans or smaller chunks.

## Audio Clips Or Automation Requested

The first Skill version does not promise audio clip import or automation editing. Explain that the current stable contract covers Session View MIDI and supported mixer/device operations only.
