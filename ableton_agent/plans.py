import json
from pathlib import Path

from ableton_agent.paths import ensure_parent


def demo_melody_plan(track_name="AI Test - Melody", clip_name="AI Test - 8 Bar Motif", scene_index=0):
    notes = []
    motif = [
        (67, 0.0, 0.5),
        (70, 0.5, 0.5),
        (74, 1.0, 0.5),
        (77, 1.5, 0.5),
        (75, 2.0, 0.5),
        (74, 2.5, 0.5),
        (70, 3.0, 0.75),
    ]
    for bar in range(8):
        offset = bar * 4.0
        transpose = 0 if bar < 4 else 2
        for pitch, start, duration in motif:
            notes.append(
                {
                    "pitch": pitch + transpose,
                    "start_time": offset + start,
                    "duration": duration,
                    "velocity": 96,
                }
            )

    return {
        "plan_version": 1,
        "name": "demo-melody",
        "description": "Create a new MIDI track with a simple generated test melody.",
        "operations": [
            {
                "id": "track.demo",
                "type": "create_midi_track",
                "index": -1,
                "name": track_name,
            },
            {
                "id": "clip.demo",
                "type": "create_midi_clip",
                "track_ref": "track.demo",
                "scene_index": scene_index,
                "length": 32.0,
                "name": clip_name,
            },
            {
                "type": "add_notes",
                "clip_ref": "clip.demo",
                "notes": notes,
            },
        ],
    }


def mini_arrangement_plan(scene_index=0, tempo=124.0, prefix="AI Jam"):
    length = 64.0
    return {
        "plan_version": 1,
        "name": "mini-arrangement",
        "description": "Create a four-track MIDI sketch with drums, bass, chords, and lead.",
        "operations": [
            {"type": "set_tempo", "tempo": tempo},
            {"id": "track.drums", "type": "create_midi_track", "index": -1, "name": "%s - Drums" % prefix},
            {"id": "track.bass", "type": "create_midi_track", "index": -1, "name": "%s - Bass" % prefix},
            {"id": "track.chords", "type": "create_midi_track", "index": -1, "name": "%s - Chords" % prefix},
            {"id": "track.lead", "type": "create_midi_track", "index": -1, "name": "%s - Lead" % prefix},
            {
                "id": "clip.drums",
                "type": "create_midi_clip",
                "track_ref": "track.drums",
                "scene_index": scene_index,
                "length": length,
                "name": "%s Drums" % prefix,
            },
            {
                "id": "clip.bass",
                "type": "create_midi_clip",
                "track_ref": "track.bass",
                "scene_index": scene_index,
                "length": length,
                "name": "%s Bass" % prefix,
            },
            {
                "id": "clip.chords",
                "type": "create_midi_clip",
                "track_ref": "track.chords",
                "scene_index": scene_index,
                "length": length,
                "name": "%s Chords" % prefix,
            },
            {
                "id": "clip.lead",
                "type": "create_midi_clip",
                "track_ref": "track.lead",
                "scene_index": scene_index,
                "length": length,
                "name": "%s Lead" % prefix,
            },
            {"type": "add_notes", "clip_ref": "clip.drums", "notes": drum_notes(length)},
            {"type": "add_notes", "clip_ref": "clip.bass", "notes": bass_notes()},
            {"type": "add_notes", "clip_ref": "clip.chords", "notes": chord_notes()},
            {"type": "add_notes", "clip_ref": "clip.lead", "notes": lead_notes()},
        ],
    }


def eurodance_sketch_plan(
    prefix="Euro Lab",
    scene_name="Euro Lab Hook Groove",
    tempo=138.0,
    bars=8,
    drum_rack="Foundation Dance Kit.adg",
    bass_rack="Retromancer Bass.adg",
    chord_rack="Star Eyes Keys.adg",
    lead_rack="Bouncy Castle Mallets.adg",
):
    length = bars * 4.0
    return {
        "plan_version": 1,
        "name": "eurodance-sketch",
        "description": (
            "Create an original high-energy eurodance/ringtone style sketch "
            "with real Live Browser racks where available."
        ),
        "operations": [
            {"type": "set_tempo", "tempo": tempo},
            {"id": "scene.main", "type": "create_scene", "index": -1, "name": scene_name},
            {"id": "track.drums", "type": "create_midi_track", "index": -1, "name": "%s - Dance Drums" % prefix},
            {"id": "track.bass", "type": "create_midi_track", "index": -1, "name": "%s - Offbeat Bass" % prefix},
            {"id": "track.chords", "type": "create_midi_track", "index": -1, "name": "%s - Stab Chords" % prefix},
            {"id": "track.lead", "type": "create_midi_track", "index": -1, "name": "%s - Bright Hook" % prefix},
            load_browser_rack_op("track.drums", drum_rack, ["drums"]),
            load_browser_rack_op("track.bass", bass_rack, ["sounds"]),
            load_browser_rack_op("track.chords", chord_rack, ["sounds"]),
            load_browser_rack_op("track.lead", lead_rack, ["sounds"]),
            {"type": "insert_device", "track_ref": "track.drums", "device_name": "Compressor"},
            {"type": "insert_device", "track_ref": "track.lead", "device_name": "Auto Filter"},
            {
                "id": "clip.drums",
                "type": "create_midi_clip",
                "track_ref": "track.drums",
                "scene_ref": "scene.main",
                "length": length,
                "name": "%s Drums" % prefix,
            },
            {
                "id": "clip.bass",
                "type": "create_midi_clip",
                "track_ref": "track.bass",
                "scene_ref": "scene.main",
                "length": length,
                "name": "%s Bass" % prefix,
            },
            {
                "id": "clip.chords",
                "type": "create_midi_clip",
                "track_ref": "track.chords",
                "scene_ref": "scene.main",
                "length": length,
                "name": "%s Chords" % prefix,
            },
            {
                "id": "clip.lead",
                "type": "create_midi_clip",
                "track_ref": "track.lead",
                "scene_ref": "scene.main",
                "length": length,
                "name": "%s Hook" % prefix,
            },
            {"type": "add_notes", "clip_ref": "clip.drums", "notes": eurodance_drum_notes(bars)},
            {"type": "add_notes", "clip_ref": "clip.bass", "notes": eurodance_bass_notes(bars)},
            {"type": "add_notes", "clip_ref": "clip.chords", "notes": eurodance_chord_notes(bars)},
            {"type": "add_notes", "clip_ref": "clip.lead", "notes": eurodance_hook_notes(bars)},
            {"type": "set_track_mixer", "track_ref": "track.drums", "volume": 0.72, "panning": 0.0},
            {"type": "set_track_mixer", "track_ref": "track.bass", "volume": 0.66, "panning": 0.0},
            {"type": "set_track_mixer", "track_ref": "track.chords", "volume": 0.48, "panning": -0.12},
            {"type": "set_track_mixer", "track_ref": "track.lead", "volume": 0.74, "panning": 0.08},
            {"type": "fire_scene", "scene_ref": "scene.main"},
        ],
    }


def load_browser_rack_op(track_ref, browser_name, roots):
    return {
        "type": "load_browser_item",
        "track_ref": track_ref,
        "browser_name": browser_name,
        "browser_exact": True,
        "browser_roots": roots,
        "browser_max_depth": 10,
    }


def eurodance_drum_notes(bars):
    notes = []
    for bar in range(bars):
        offset = bar * 4.0
        for beat in range(4):
            notes.append(note(36, offset + beat, 0.12, 112))
            notes.append(note(42, offset + beat + 0.5, 0.08, 72))
        notes.append(note(39, offset + 1.0, 0.12, 100))
        notes.append(note(39, offset + 3.0, 0.12, 106))
        notes.append(note(46, offset + 1.5, 0.18, 78))
        notes.append(note(46, offset + 3.5, 0.18, 82))
        if bar % 4 == 0:
            notes.append(note(49, offset, 0.2, 88))
        if bar % 4 == 3:
            notes.extend(
                [
                    note(38, offset + 3.25, 0.1, 86),
                    note(38, offset + 3.5, 0.1, 94),
                    note(38, offset + 3.75, 0.1, 102),
                ]
            )
    return notes


def eurodance_bass_notes(bars):
    roots = [41, 37, 44, 39]
    notes = []
    for bar in range(bars):
        root = roots[bar % len(roots)]
        offset = bar * 4.0
        pattern = [
            (0.5, root, 104),
            (1.0, root + 12, 86),
            (1.5, root, 100),
            (2.5, root, 104),
            (3.0, root + 7, 88),
            (3.5, root, 106),
        ]
        for start, pitch, velocity in pattern:
            notes.append(note(pitch, offset + start, 0.32, velocity))
    return notes


def eurodance_chord_notes(bars):
    chords = [
        [53, 56, 60],
        [49, 53, 56],
        [56, 60, 63],
        [51, 55, 58],
    ]
    notes = []
    for bar in range(bars):
        offset = bar * 4.0
        chord = chords[bar % len(chords)]
        for start in [0.0, 1.5, 2.5]:
            for pitch in chord:
                notes.append(note(pitch, offset + start, 0.72, 72 if start else 82))
    return notes


def eurodance_hook_notes(bars):
    motif_a = [
        (77, 0.0, 0.18),
        (80, 0.25, 0.18),
        (84, 0.5, 0.18),
        (87, 0.75, 0.18),
        (84, 1.0, 0.18),
        (80, 1.25, 0.18),
        (82, 1.5, 0.18),
        (84, 1.75, 0.18),
        (80, 2.25, 0.2),
        (77, 2.5, 0.2),
        (75, 2.75, 0.2),
        (77, 3.0, 0.42),
    ]
    motif_b = [
        (84, 0.0, 0.18),
        (87, 0.25, 0.18),
        (89, 0.5, 0.18),
        (87, 0.75, 0.18),
        (84, 1.0, 0.18),
        (82, 1.25, 0.18),
        (80, 1.5, 0.18),
        (77, 1.75, 0.18),
        (77, 2.5, 0.2),
        (80, 3.0, 0.18),
        (84, 3.25, 0.36),
    ]
    notes = []
    for bar in range(bars):
        offset = bar * 4.0
        motif = motif_a if bar % 2 == 0 else motif_b
        transpose = 0 if bar < 4 else 12
        for pitch, start, duration in motif:
            notes.append(note(pitch + transpose, offset + start, duration, 98))
    return notes


def section_variation_plan(
    base_track_index=5,
    scene_index=1,
    prefix="AI Jam 01 B",
    track_names=None,
    scene_name=None,
):
    length = 32.0
    roles = ["drums", "bass", "chords", "lead"]
    if track_names is not None and len(track_names) != len(roles):
        raise ValueError("section_variation_plan requires exactly four track_names")
    return {
        "plan_version": 1,
        "name": "section-variation",
        "description": "Create a second-scene variation on existing drums, bass, chords, and lead tracks.",
        "operations": [
            variation_clip_op("drums", 0, base_track_index, track_names, scene_index, scene_name, length, prefix),
            variation_clip_op("bass", 1, base_track_index, track_names, scene_index, scene_name, length, prefix),
            variation_clip_op("chords", 2, base_track_index, track_names, scene_index, scene_name, length, prefix),
            variation_clip_op("lead", 3, base_track_index, track_names, scene_index, scene_name, length, prefix),
            {"type": "add_notes", "clip_ref": "clip.drums", "notes": variation_drum_notes(length)},
            {"type": "add_notes", "clip_ref": "clip.bass", "notes": variation_bass_notes()},
            {"type": "add_notes", "clip_ref": "clip.chords", "notes": variation_chord_notes()},
            {"type": "add_notes", "clip_ref": "clip.lead", "notes": variation_lead_notes()},
        ],
    }


def variation_clip_op(role, offset, base_track_index, track_names, scene_index, scene_name, length, prefix):
    operation = {
        "id": "clip.%s" % role,
        "type": "create_midi_clip",
        "length": length,
        "name": "%s %s" % (prefix, role.title()),
    }
    if track_names is not None:
        operation["track_name"] = track_names[offset]
    else:
        operation["track_index"] = base_track_index + offset
    if scene_name is not None:
        operation["scene_name"] = scene_name
    else:
        operation["scene_index"] = scene_index
    return operation


def note_metadata_proof_plan(track_name="AI Metadata Proof", clip_name="Metadata Proof", scene_index=0):
    notes = []
    pattern = [
        (60, 0.0, 0.5, 100, 1.0, 0.0, 64),
        (64, 0.5, 0.5, 92, 0.75, -10.0, 52),
        (67, 1.0, 0.5, 88, 0.5, 12.0, 70),
        (72, 1.5, 0.75, 104, 0.25, -20.0, 96),
    ]
    for bar in range(2):
        offset = bar * 4.0
        for pitch, start, duration, velocity, probability, velocity_deviation, release_velocity in pattern:
            notes.append(
                {
                    "pitch": pitch + (bar * 2),
                    "start_time": offset + start,
                    "duration": duration,
                    "velocity": velocity,
                    "probability": probability,
                    "velocity_deviation": velocity_deviation,
                    "release_velocity": release_velocity,
                }
            )

    return {
        "plan_version": 1,
        "name": "note-metadata-proof",
        "description": "Create a small MIDI clip that verifies Live 11+ note metadata preservation.",
        "operations": [
            {
                "id": "track.metadata",
                "type": "create_midi_track",
                "index": -1,
                "name": track_name,
            },
            {
                "id": "clip.metadata",
                "type": "create_midi_clip",
                "track_ref": "track.metadata",
                "scene_index": scene_index,
                "length": 8.0,
                "name": clip_name,
            },
            {
                "type": "add_notes",
                "clip_ref": "clip.metadata",
                "notes": notes,
            },
        ],
    }


def mixer_proof_plan(track_name="AI Mixer Proof"):
    return {
        "plan_version": 1,
        "name": "mixer-proof",
        "description": "Create a MIDI track and verify track state and mixer writes.",
        "operations": [
            {
                "id": "track.mixer",
                "type": "create_midi_track",
                "index": -1,
                "name": track_name,
            },
            {
                "type": "set_track_state",
                "track_ref": "track.mixer",
                "name": track_name,
                "arm": True,
                "mute": True,
                "solo": False,
            },
            {
                "type": "set_track_mixer",
                "track_ref": "track.mixer",
                "volume": 0.72,
                "panning": -0.2,
                "sends": [
                    {"index": 0, "value": 0.18},
                    {"index": 1, "value": 0.08},
                ],
            },
        ],
    }


def mixer_adjust_proof_plan(track_index=4, target_track_name=None, track_name="AI Mixer Proof Adjusted"):
    target = {"track_name": target_track_name} if target_track_name is not None else {"track_index": track_index}
    return {
        "plan_version": 1,
        "name": "mixer-adjust-proof",
        "description": "Adjust an existing track state and mixer values.",
        "operations": [
            {
                "type": "set_track_state",
                **target,
                "name": track_name,
                "arm": False,
                "mute": False,
                "solo": False,
            },
            {
                "type": "set_track_mixer",
                **target,
                "volume": 0.55,
                "panning": 0.25,
                "sends": [
                    {"index": 0, "value": 0.05},
                    {"index": 1, "value": 0.12},
                ],
            },
        ],
    }


def device_parameter_proof_plan():
    return {
        "plan_version": 1,
        "name": "device-parameter-proof",
        "description": "Adjust default return-track Reverb and Delay device parameters.",
        "operations": [
            {
                "type": "set_device_parameter",
                "track_type": "return",
                "track_index": 0,
                "device_index": 0,
                "device_name": "Reverb",
                "parameter_index": 20,
                "parameter_name": "Decay Time",
                "value": 0.36,
            },
            {
                "type": "set_device_parameter",
                "track_type": "return",
                "track_index": 1,
                "device_index": 0,
                "device_name": "Delay",
                "parameter_index": 12,
                "parameter_name": "Feedback",
                "value": 0.32,
            },
        ],
    }


def track_note_edit_proof_plan(track_name="AI Note Edit Proof", clip_name="Note Edit Proof", scene_index=0):
    initial_notes = [
        note(60, 0.0, 0.5, 80),
        note(64, 0.5, 0.5, 86),
        note(67, 1.0, 0.5, 92),
        note(72, 1.5, 0.5, 98),
    ]
    expected_notes = [
        note(60, 0.0, 0.5, 80),
        {
            "pitch": 65,
            "start_time": 0.5,
            "duration": 0.75,
            "velocity": 108,
            "probability": 0.8,
        },
        note(72, 1.5, 0.5, 98),
    ]
    return {
        "plan_version": 1,
        "name": "track-note-edit-proof",
        "description": "Create a MIDI clip, then modify and remove notes by note match selectors.",
        "expected_notes": expected_notes,
        "operations": [
            {
                "id": "track.note_edit",
                "type": "create_midi_track",
                "index": -1,
                "name": track_name,
            },
            {
                "id": "clip.note_edit",
                "type": "create_midi_clip",
                "track_ref": "track.note_edit",
                "scene_index": scene_index,
                "length": 4.0,
                "name": clip_name,
            },
            {
                "type": "add_notes",
                "clip_ref": "clip.note_edit",
                "notes": initial_notes,
            },
            {
                "type": "modify_notes",
                "clip_ref": "clip.note_edit",
                "patches": [
                    {
                        "match": {
                            "pitch": 64,
                            "start_time": 0.5,
                        },
                        "set": {
                            "pitch": 65,
                            "duration": 0.75,
                            "velocity": 108,
                            "probability": 0.8,
                        },
                    }
                ],
            },
            {
                "type": "remove_notes",
                "clip_ref": "clip.note_edit",
                "match": {
                    "pitch": 67,
                    "start_time": 1.0,
                },
            },
        ],
    }


def device_insertion_proof_plan(
    track_name="AI Native Device Proof",
    instrument_name="Drift",
    effect_name="Auto Filter",
):
    return {
        "plan_version": 1,
        "name": "device-insertion-proof",
        "description": "Create a MIDI track and insert native Live devices by UI name.",
        "operations": [
            {
                "id": "track.device_insert",
                "type": "create_midi_track",
                "index": -1,
                "name": track_name,
            },
            {
                "type": "insert_device",
                "track_ref": "track.device_insert",
                "device_name": instrument_name,
            },
            {
                "type": "insert_device",
                "track_ref": "track.device_insert",
                "device_name": effect_name,
            },
        ],
    }


def drum_notes(length):
    notes = []
    bar_count = int(length // 4)
    for bar in range(bar_count):
        start = bar * 4.0
        notes.extend(
            [
                note(36, start + 0.0, 0.25, 112),
                note(36, start + 2.0, 0.25, 104),
                note(38, start + 1.0, 0.25, 104),
                note(38, start + 3.0, 0.25, 108),
            ]
        )
        for step in range(8):
            velocity = 68 if step % 2 else 82
            notes.append(note(42, start + step * 0.5, 0.125, velocity))
        if bar % 4 == 3:
            notes.append(note(49, start + 3.5, 0.25, 96))
    return notes


def variation_drum_notes(length):
    notes = []
    bar_count = int(length // 4)
    for bar in range(bar_count):
        start = bar * 4.0
        notes.extend(
            [
                note(36, start + 0.0, 0.25, 112),
                note(36, start + 1.75, 0.25, 94),
                note(36, start + 2.5, 0.25, 104),
                note(38, start + 1.0, 0.25, 106),
                note(38, start + 3.0, 0.25, 110),
            ]
        )
        for step in range(8):
            velocity = 72 if step % 2 else 88
            notes.append(note(42, start + step * 0.5, 0.125, velocity))
        if bar % 4 == 3:
            notes.extend(
                [
                    note(45, start + 3.25, 0.125, 96),
                    note(47, start + 3.5, 0.125, 100),
                    note(49, start + 3.75, 0.25, 106),
                ]
            )
    return notes


def bass_notes():
    progression = [43, 39, 36, 38] * 4
    notes = []
    for bar, root in enumerate(progression):
        start = bar * 4.0
        notes.extend(
            [
                note(root, start + 0.0, 0.5, 100),
                note(root, start + 1.5, 0.5, 92),
                note(root + 7, start + 2.5, 0.5, 88),
                note(root, start + 3.5, 0.5, 94),
            ]
        )
    return notes


def variation_bass_notes():
    progression = [43, 41, 39, 38] * 2
    notes = []
    for bar, root in enumerate(progression):
        start = bar * 4.0
        notes.extend(
            [
                note(root, start + 0.0, 0.5, 102),
                note(root + 7, start + 0.75, 0.25, 86),
                note(root, start + 1.5, 0.5, 92),
                note(root + 10, start + 2.5, 0.5, 88),
                note(root + 12, start + 3.5, 0.25, 84),
            ]
        )
    return notes


def chord_notes():
    chords = [
        [55, 58, 62, 65],  # Gm7
        [51, 55, 58, 62],  # Ebmaj7-ish
        [48, 51, 55, 58],  # Cm7
        [50, 53, 57, 60],  # Dm7 color
    ]
    notes = []
    for cycle in range(4):
        for index, chord in enumerate(chords):
            start = (cycle * 16.0) + (index * 4.0)
            for pitch in chord:
                notes.append(note(pitch, start, 3.5, 78))
            if index % 2 == 1:
                for pitch in chord[:2]:
                    notes.append(note(pitch + 12, start + 3.0, 0.5, 70))
    return notes


def variation_chord_notes():
    chords = [
        [58, 62, 65, 70],  # Gm7 inversion
        [53, 57, 60, 65],  # F color
        [55, 58, 62, 67],  # Ebmaj7 inversion
        [57, 60, 64, 69],  # D7sus-ish tension
    ]
    notes = []
    for cycle in range(2):
        for index, chord in enumerate(chords):
            start = (cycle * 16.0) + (index * 4.0)
            for pitch in chord:
                notes.append(note(pitch, start, 2.75, 76))
            for pitch in chord[1:3]:
                notes.append(note(pitch + 12, start + 3.0, 0.5, 68))
    return notes


def lead_notes():
    motif = [
        (67, 0.0, 0.5),
        (70, 0.5, 0.5),
        (74, 1.0, 0.5),
        (77, 1.5, 0.5),
        (75, 2.0, 0.25),
        (74, 2.25, 0.25),
        (70, 2.5, 0.5),
        (67, 3.25, 0.5),
    ]
    notes = []
    for phrase in range(16):
        start = phrase * 4.0
        transpose = [0, -2, -5, 2][phrase % 4]
        for pitch, offset, duration in motif:
            notes.append(note(pitch + transpose, start + offset, duration, 94))
    return notes


def variation_lead_notes():
    motif = [
        (74, 0.0, 0.5),
        (77, 0.5, 0.25),
        (79, 0.75, 0.25),
        (82, 1.0, 0.5),
        (80, 1.75, 0.25),
        (79, 2.0, 0.5),
        (77, 2.75, 0.25),
        (74, 3.0, 0.75),
    ]
    notes = []
    for phrase in range(8):
        start = phrase * 4.0
        transpose = [0, -2, -4, 1][phrase % 4]
        for pitch, offset, duration in motif:
            item = note(pitch + transpose, start + offset, duration, 94)
            if offset in (0.75, 2.75):
                item["probability"] = 0.85
            notes.append(item)
    return notes


def note(pitch, start_time, duration, velocity):
    return {
        "pitch": pitch,
        "start_time": start_time,
        "duration": duration,
        "velocity": velocity,
    }


def load_plan(path):
    return json.loads(Path(path).read_text())


def write_plan(path, plan):
    ensure_parent(path).write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
