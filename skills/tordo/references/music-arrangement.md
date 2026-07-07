# Tordo Music Arrangement Guide

Read this before any quality-sensitive music generation, MIDI import, or arrangement task. Tordo proves that notes were written correctly; this guide is about whether the result is worth listening to. Technical success and musical success are different checks.

## Understand The Musical Context First

Before writing any notes:

1. Read the `song` section of `tordo snapshot`: tempo, `signature_numerator`/`signature_denominator`, and, when the bridge exposes them, `root_note` (0 = C ... 11 = B) and `scale_name`. Prefer the user's configured key over your own guess.
2. If the Set already has material, run `tordo export` plus `tordo analyze` and respect the existing key, chord movement, and density instead of writing against them.
3. Ask the user for genre, mood, and reference tracks if the request does not state them. "Make it sound good" is not enough context to act on.

## Source MIDI Import Discipline

When importing or reconstructing an existing piece:

- Analyze every source track's role before assigning instruments: drums, bass, chords/comping, lead/melody, counter-melody, pads. Use pitch range, note density, and channel/program metadata.
- Reconcile counts: source track count versus created tracks, and source note count versus written notes. Report any dropped tracks or notes to the user instead of silently omitting them.
- Keep percussion lanes separate. Do not collapse different drum pitches into one sound; kick, snare, and hats must remain distinct pitches on a drum instrument.
- Preserve the source tempo and key unless the user asks for a change.

## Role Layout And Register Separation

- Give every role its own track and register: bass roughly below MIDI 48, chords in the middle, leads above the chords. Two busy parts in the same octave range will mask each other.
- One clear low-end voice. If two tracks fight below MIDI 40, cut or raise one.
- Limit simultaneous busy parts: drums plus bass plus one or two active melodic parts is a solid default; pads and sustained chords can coexist because they move slowly.

## Instrument Selection

- Discover sounds with `tordo browser-items` before choosing; never hard-code rack or preset names.
- Match sound names to roles and style: a result containing "Bass" for the bass role, "Kit" or "Drum" for drums, pad-like names for pads. A grand piano playing a synth-bass line is a technically valid, musically wrong choice.
- After loading, verify each MIDI track has a sound-producing instrument device. A MIDI track with no instrument is silent and counts as a missing-track failure.

## Velocity And Feel

Flat, fully quantized notes at one velocity are the most common cause of a lifeless result:

- Vary velocity with musical intent: accent beat 1 (and the backbeat for drums), keep off-beat hats and inner chord notes softer. A usable default range is roughly 70-115, not a constant 100.
- Use the extended note fields where texture matters: `velocity_deviation` for natural variation between repeats, `probability` below 1.0 for hi-hat and percussion fills.
- Keep durations musical: legato for bass and pads, shorter detached notes for funk comping and arps. Notes that all last exactly one grid step sound mechanical.

## Mixer Starting Points

Set a rough static mix before asking the user to listen:

- Leave headroom: keep the master well below maximum and track volumes moderate; drums and bass usually sit loudest, pads and textures lower.
- Pan for width: keep kick, snare, bass, and lead vocal-role parts near center; spread chords, hats, and counter-melodies moderately left/right.
- Use return sends sparingly: a little shared reverb/delay for leads, chords, and pads; keep bass and kick nearly dry. Too much send is the fastest way to a washed-out result.

## Structure And Sections

- Align clips to bar boundaries and phrase in 4- or 8-bar units in 4/4; check the Set signature first.
- Use scenes as song sections (intro, verse, hook, break) instead of one giant clip per track, unless the user asked for a single full-length import.
- Vary sections: drop or thin parts in intros and breaks, and change at least one element every 8 bars (fill, octave shift, added layer). Verbatim repetition reads as unfinished.

## Post-Write Musical Sanity Checklist

Run this after apply and verification, before declaring the task done:

1. Every created MIDI track has an instrument device and at least one clip with notes.
2. Note counts and per-clip diffs match the plan or source MIDI; report gaps.
3. Tempo, signature, and key match the user's intent.
4. Clip lengths and loop points sit on bar boundaries.
5. Registers are separated: one low-end voice, no two busy parts stacked in the same octave.
6. Velocities are not uniform; percussion has accents.
7. A rough mix exists: levels staged, pans set, sends modest.
8. Fire the relevant scene or clips so the user can listen immediately.

## Human-Ear Rule

Never claim the result sounds good; you cannot hear it. After the checklist passes, ask the user to listen and request concrete feedback: too sparse or too busy, late or early against drums, too much reverb, wrong sound for the role, section too repetitive. Turn each answer into an explicit follow-up plan.
