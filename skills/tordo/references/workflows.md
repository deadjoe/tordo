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

## Clear Or Replace A Set

Live requires at least one regular track to exist at every step. Do not write a plan that deletes all current regular tracks before creating a replacement.

When the user asks to clear or replace the current Set:

1. Inspect the Set and confirm destructive edits are allowed.
2. Create a temporary holder regular track or create the first replacement regular track before deleting old tracks.
3. Delete old tracks from highest index to lowest index with `allow_destructive: true` and `expected_track_name`.
4. Use `--no-cleanup-empty-project-tracks` if default empty-project cleanup would conflict with deliberate holder-track cleanup.
5. Delete the holder only after at least one non-holder regular track exists.

## Use Browser Sounds

Browser content is user-specific. Never assume a rack, preset, pack, or plug-in exists. Installed Packs are first-class user resources; inspect them when choosing instruments, orchestral libraries, drum kits, effects, or any sound that may come from purchased/free packs.

1. Query current Browser items across the roots relevant to the task:

```bash
tordo browser-items --root sounds --query "lead"
tordo browser-items --root instruments --query "piano"
tordo browser-items --root packs --include-folders --max-depth 2 --max-results 80
tordo browser-items --root packs --query "orchestral" --include-folders --max-depth 5
tordo browser-items --root user_library --include-folders --max-depth 4 --max-results 80
tordo browser-items --root user_library --query "strings"
tordo browser-items --root current_project --include-folders --max-depth 4 --max-results 80
tordo browser-items --root current_project --query "rack"
tordo browser-items --root audio_effects --query "filter"
```

2. For broad sound-selection tasks, make a short inventory of promising installed resources before choosing: installed packs, likely loadable items, missing or empty roots, and a fallback if the best library is unavailable. Packs often contain third-party or purchased libraries that are better than stock categories.
3. Choose from returned loadable items only. Folder or pack nodes are useful for discovery but are not load targets.
4. Prefer `browser_uri` from the current query result when available.
5. If no good item exists, fall back to native device insertion or uninstrumented MIDI and tell the user.

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
