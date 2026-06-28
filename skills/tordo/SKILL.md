---
name: tordo
description: Use Tordo to inspect, plan, dry-run, apply, and verify safe Session View MIDI edits in Ableton Live through the installed tordo CLI and JSON plan schema. Use when a user asks an agent to control Ableton Live, inspect a Live Set, create or edit MIDI clips, adjust track mixer/device parameters, search Ableton Browser items, or troubleshoot the local Tordo bridge.
---

# Tordo

Tordo lets an agent control Ableton Live through the installed `tordo` CLI. Use the CLI and JSON plan schema as the only stable contract; do not call the raw bridge socket except when debugging Tordo itself.

## Verified Envelope

Stay inside this first-version envelope unless the installed `tordo schema` and `tordo capabilities` explicitly support more:

- In scope: macOS, Ableton Live Suite `>=12.4`, Session View MIDI clips, tracks, scenes, return tracks, native devices, Browser item loading after discovery, mixer/device parameters, structured selectors, dry-run/apply/verify workflows, and group/foldable track presence with fresh snapshot index validation.
- Out of scope: Windows, audio clip import, automation editing, durable identity for duplicate track or scene names, direct third-party plug-in internals beyond Live-exposed parameters, and autonomous judgments about how audio sounds.
- If a track or scene name is duplicated, stop and ask the human to identify the target. Do not guess.
- Same-track duplicate clip names are usable only when scene context disambiguates the clip.
- Musical taste is human-ear-in-the-loop: ask the user to listen when decisions depend on groove, balance, timbre, density, or whether a part works.

Tordo is an independent project and is not affiliated with, authorized, sponsored, or endorsed by Ableton AG. Ableton and Live are trademarks of Ableton AG.

## Mandatory Workflow

For any non-trivial task:

1. Run `tordo doctor` before assuming the environment works. For a concise summary, run `python scripts/doctor.py` from this skill folder.
2. Run `tordo schema` and `tordo capabilities`; treat their output as newer than this Skill.
3. Run `tordo snapshot` before planning against existing Live objects.
4. If choosing sounds, run `tordo browser-items` first and only use returned loadable items.
5. Build an explicit JSON plan.
6. Dry-run with `tordo apply-plan PLAN --prepared-out PREPARED`.
7. Inspect the prepared plan and dry-run response.
8. Apply only after the dry-run is acceptable: `tordo apply-plan PLAN --apply --prepared-out PREPARED`.
9. Verify through `tordo snapshot`, `tordo set-notes`, `tordo clip-notes`, `tordo export`, `tordo analyze`, or `tordo diff`.
10. Ask for human listening feedback before taste-based follow-up edits.

## Safety Rules

- Never rely on cached indices. Read a fresh snapshot before writes.
- Prefer `track_selector.name`, `scene_selector.name`, and `clip_selector.name` only when names are unique.
- Use `selector.index + selector.expected_name` only as position-context validation, not durable identity.
- Use `track_ref`, `scene_ref`, and `clip_ref` for objects created earlier in the same plan.
- Never create a MIDI clip over an existing clip.
- Never delete tracks or scenes without `allow_destructive: true`.
- Keep plans within `capabilities` limits; split large note writes.
- Do not hard-code Browser rack names as portable assumptions.
- Do not use `tordo dev ...` unless the user is maintaining Tordo or explicitly asks for project proof/debug commands.

## References

- Read `references/contract.md` when you need exact contract boundaries, stable commands, or scope limits.
- Read `references/workflows.md` when you need a concrete inspect, edit, Browser, or human-feedback workflow.
- Read `references/plan-schema.md` when writing JSON plans or selectors.
- Read `references/troubleshooting.md` when `doctor`, preflight, dry-run, Browser search, or bridge runtime checks fail.
