# Tordo Workflows

Use these workflows as procedures. Keep using current runtime output from `tordo schema`, `tordo capabilities`, and `tordo snapshot`.

## Environment Check

```bash
tordo doctor
```

If the output is long or you need a concise summary from this Skill folder:

```bash
python scripts/doctor.py
```

Proceed only when the required checks for the requested task pass. For read-only local planning without Live writes, a missing running Live process can be explained. For runtime control, bridge reachability must pass.

## Inspect A Set

1. Run `tordo doctor`.
2. Run `tordo schema`.
3. Run `tordo capabilities`.
4. Run `tordo snapshot`.
5. For note-heavy tasks, run `tordo set-notes --limit-per-clip N`.
6. Summarize tracks, scenes, clips, duplicate names, and relevant devices before proposing edits.

Do not write during inspection.

## Make A Safe Edit

1. Run the inspect workflow.
2. Build a JSON plan using structured selectors or plan-local refs.
3. Save the plan in a temporary file.
4. Dry-run:

```bash
tordo apply-plan PLAN.json --prepared-out PREPARED.json --timeout 120
```

5. Inspect the prepared plan. Confirm expected names were added for existing targets.
6. If the current Set is a default empty project, inspect whether preflight appended deletion of the default empty tracks (`1-MIDI`, `2-MIDI`, `3-Audio`, `4-Audio`). This cleanup keeps generated projects tidy, but use `--no-cleanup-empty-project-tracks` when the task needs to preserve those tracks.
7. Apply:

```bash
tordo apply-plan PLAN.json --apply --prepared-out PREPARED-apply.json --timeout 120
```

8. Verify with snapshot, set-notes, clip-notes, export, analyze, or diff.

## Use Browser Sounds

Browser content is user-specific. Never assume a rack, preset, pack, or plug-in exists.

1. Query current Browser items:

```bash
tordo browser-items --root sounds --query "lead"
tordo browser-items --root instruments --query "piano"
tordo browser-items --root audio_effects --query "filter"
```

2. Choose from returned loadable items only.
3. Prefer `browser_uri` from the current query result when available.
4. If no good item exists, fall back to native device insertion or uninstrumented MIDI and tell the user.

## Handle Duplicate Names

- Duplicate track name: stop and ask the human to identify the target, unless they explicitly provide current index plus expected name.
- Duplicate scene name: stop and ask the human to identify the target, unless they explicitly provide current index plus expected name.
- Duplicate clip name on one track: add scene context if the scene is unique.
- Same-named tracks or scenes can still be confused by human reordering; do not present `index + expected_name` as identity.

## Human Listening Loop

Use Tordo for mechanical inspection and edits. Ask the human to listen when deciding:

- whether timing feels early or late
- whether a section is too sparse or too dense
- whether a sound is too dull, harsh, dry, or wet
- whether a hook, groove, or transition works

Translate feedback into explicit plan edits, then dry-run, apply, and verify.
