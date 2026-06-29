---
name: tordo
description: Use Tordo to inspect, plan, dry-run, apply, and verify safe Session View MIDI edits in Ableton Live through the installed tordo CLI and JSON plan schema. Use when a user asks an agent to control Ableton Live, inspect a Live Set, create or edit MIDI clips, adjust track mixer/device parameters, discover installed Packs/User Library Browser sounds, or troubleshoot the local Tordo bridge.
---

# Tordo

Tordo lets an agent control Ableton Live through the installed `tordo` CLI. Use the CLI and JSON plan schema as the only stable contract; do not call the raw bridge socket except when debugging Tordo itself.

## Verified Envelope

Stay inside this first-version envelope unless the installed `tordo schema` and `tordo capabilities` explicitly support more:

- In scope: macOS, Ableton Live Suite `>=12.4`, Session View MIDI clips, tracks, scenes, return tracks, native devices, Browser item loading after discovery, mixer/device parameters, `track_type=return` / `track_type=master` mixer targets when supported by runtime schema, structured selectors, dry-run/apply/verify workflows, and group/foldable track presence with fresh snapshot index validation.
- Out of scope: Windows, audio clip import, automation editing, durable identity for duplicate track or scene names, direct third-party plug-in internals beyond Live-exposed parameters, and autonomous judgments about how audio sounds.
- If a track or scene name is duplicated, stop and ask the human to identify the target. Do not guess.
- Same-track duplicate clip names are usable only when scene context disambiguates the clip.
- Musical taste is human-ear-in-the-loop: ask the user to listen when decisions depend on groove, balance, timbre, density, or whether a part works.

Tordo is an independent project and is not affiliated with, authorized, sponsored, or endorsed by Ableton AG. Ableton and Live are trademarks of Ableton AG.

## Mandatory Workflow

For any non-trivial task:

1. Run `tordo doctor` before assuming the environment works. If `tordo` is not found, read `references/troubleshooting.md`, propose a CLI install command, and ask the user before installing. For a concise summary after the CLI exists, run `python scripts/doctor.py` from this skill folder.
2. Run `tordo schema` and `tordo capabilities`; treat their output as newer than this Skill.
3. Run `tordo snapshot` before planning against existing Live objects.
4. If choosing sounds, run `tordo browser-items` first across relevant roots, including installed `packs` and `user_library`, and only use returned loadable items.
5. Build an explicit JSON plan.
6. Dry-run with `tordo apply-plan PLAN --prepared-out PREPARED`.
7. Inspect the prepared plan and dry-run response.
8. Check whether preflight appended default empty-project track cleanup. Use `--no-cleanup-empty-project-tracks` if the default empty tracks must be preserved.
9. When clearing or replacing a Set, keep or create a holder regular track before deleting all existing regular tracks; Live requires at least one regular track at every step.
10. Apply only after the dry-run is acceptable: `tordo apply-plan PLAN --apply --prepared-out PREPARED`.
11. Verify through `tordo snapshot`, `tordo set-notes`, `tordo clip-notes`, `tordo export`, `tordo analyze`, or `tordo diff`.
12. Ask for human listening feedback before taste-based follow-up edits.

## Safety Rules

- Never rely on cached indices. Read a fresh snapshot before writes.
- Prefer `track_selector.name`, `scene_selector.name`, and `clip_selector.name` only when names are unique.
- Use `selector.index + selector.expected_name` only as position-context validation, not durable identity.
- Use `track_ref`, `scene_ref`, and `clip_ref` for objects created earlier in the same plan.
- Use `track_type=return` for return-track mixer/device targets and `track_type=master` for master-track mixer targets only after `tordo schema` confirms support.
- Never create a MIDI clip over an existing clip.
- Never delete tracks or scenes without `allow_destructive: true`.
- Never delete the final regular track in a Set. To clear a Set, create a holder track first, delete old tracks, create replacement tracks, then delete the holder only after another regular track exists.
- Keep plans within `capabilities` limits; split large note writes.
- Do not hard-code Browser rack names as portable assumptions. Treat installed Packs, User Library, and Current Project as user-specific resources to discover before choosing sounds.
- Do not use `tordo dev ...` unless the user is maintaining Tordo or explicitly asks for project proof/debug commands.

## References

- Read `references/contract.md` when you need exact contract boundaries, stable commands, or scope limits.
- Read `references/workflows.md` when you need a concrete inspect, edit, Browser, or human-feedback workflow.
- Read `references/plan-schema.md` when writing JSON plans or selectors.
- Read `references/troubleshooting.md` when `doctor`, preflight, dry-run, Browser search, or bridge runtime checks fail.
