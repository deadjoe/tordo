from collections import defaultdict
from pathlib import Path

import mido

DEFAULT_TIME_SCALE = 0.5
DEFAULT_TEMPO = 138.0
DEFAULT_NOTE_CHUNK_SIZE = 1000
MIN_NOTE_DURATION = 0.000001


def midi_file_plan(
    midi_path,
    prefix=None,
    scene_name=None,
    tempo=DEFAULT_TEMPO,
    time_scale=DEFAULT_TIME_SCALE,
):
    return build_midi_file_plan(
        midi_path,
        prefix=prefix,
        scene_name=scene_name,
        tempo=tempo,
        time_scale=time_scale,
        include_notes=True,
    )


def midi_file_structure_plan(
    midi_path,
    prefix=None,
    scene_name=None,
    tempo=DEFAULT_TEMPO,
    time_scale=DEFAULT_TIME_SCALE,
):
    return build_midi_file_plan(
        midi_path,
        prefix=prefix,
        scene_name=scene_name,
        tempo=tempo,
        time_scale=time_scale,
        include_notes=False,
    )


def midi_file_note_chunk_plans(
    midi_path,
    prefix=None,
    scene_name=None,
    time_scale=DEFAULT_TIME_SCALE,
    note_chunk_size=DEFAULT_NOTE_CHUNK_SIZE,
):
    parsed, prefix, scene_name, layers, _clip_length = midi_file_context(
        midi_path,
        prefix=prefix,
        scene_name=scene_name,
        time_scale=time_scale,
    )
    note_chunk_size = max(1, int(note_chunk_size))
    plans = []
    chunk_number = 0
    for layer in layers:
        notes = layer_notes(parsed, layer, time_scale)
        track_name = layer_track_name(layer, prefix)
        clip_name = layer_clip_name(layer, prefix)
        for offset in range(0, len(notes), note_chunk_size):
            chunk_number += 1
            chunk = notes[offset : offset + note_chunk_size]
            plans.append(
                {
                    "plan_version": 1,
                    "name": "midi-file-note-chunk",
                    "description": "Add one chunk of MIDI notes to an existing imported clip.",
                    "source_midi": str(midi_path),
                    "layer": layer["name"],
                    "chunk_number": chunk_number,
                    "chunk_note_offset": offset,
                    "chunk_note_count": len(chunk),
                    "operations": [
                        {
                            "type": "add_notes",
                            "track_name": track_name,
                            "scene_name": scene_name,
                            "clip_name": clip_name,
                            "notes": chunk,
                        }
                    ],
                }
            )
    return plans


def build_midi_file_plan(
    midi_path,
    prefix=None,
    scene_name=None,
    tempo=DEFAULT_TEMPO,
    time_scale=DEFAULT_TIME_SCALE,
    include_notes=True,
):
    parsed, prefix, scene_name, layers, clip_length = midi_file_context(
        midi_path,
        prefix=prefix,
        scene_name=scene_name,
        time_scale=time_scale,
    )
    operations = midi_file_structure_operations(prefix, scene_name, layers, clip_length, tempo)
    if include_notes:
        operations = add_layer_note_operations(operations, parsed, layers, time_scale)
    operations.append({"type": "fire_scene", "scene_ref": "scene.main"})
    return {
        "plan_version": 1,
        "name": "midi-file-import",
        "description": "Import a MIDI file into Live tracks with role-based racks and effects.",
        "source_midi": str(midi_path),
        "midi_summary": midi_summary(parsed),
        "notes_inline": include_notes,
        "operations": operations,
    }


def midi_file_context(midi_path, prefix=None, scene_name=None, time_scale=DEFAULT_TIME_SCALE):
    parsed = parse_midi_file(midi_path)
    prefix = prefix or Path(midi_path).stem.replace("_", " ").title()
    scene_name = scene_name or ("%s MIDI Import" % prefix)
    layers = select_layers(parsed)
    clip_length = round_up_to_bar(parsed["max_beat"] * time_scale)
    return parsed, prefix, scene_name, layers, clip_length


def midi_file_structure_operations(prefix, scene_name, layers, clip_length, tempo):
    operations = [
        {"type": "set_tempo", "tempo": tempo},
        {"id": "scene.main", "type": "create_scene", "index": -1, "name": scene_name},
    ]
    for layer in layers:
        track_ref = "track.%s" % layer["id"]
        clip_ref = "clip.%s" % layer["id"]
        operations.append(
            {
                "id": track_ref,
                "type": "create_midi_track",
                "index": -1,
                "name": layer_track_name(layer, prefix),
            }
        )
        operations.append(
            {
                "type": "load_browser_item",
                "track_ref": track_ref,
                "browser_name": layer["rack"],
                **({"browser_uri": layer["browser_uri"]} if layer.get("browser_uri") else {}),
                "browser_exact": True,
                "browser_roots": [layer["root"]],
                "browser_max_depth": 8,
            }
        )
        for device_name in layer.get("effects", []):
            operations.append({"type": "insert_device", "track_ref": track_ref, "device_name": device_name})
        operations.append(
            {
                "id": clip_ref,
                "type": "create_midi_clip",
                "track_ref": track_ref,
                "scene_ref": "scene.main",
                "length": clip_length,
                "name": layer_clip_name(layer, prefix),
            }
        )
        operations.append(
            {
                "type": "set_track_mixer",
                "track_ref": track_ref,
                "volume": layer["volume"],
                "panning": layer["panning"],
            }
        )
    return operations


def add_layer_note_operations(operations, parsed, layers, time_scale):
    notes_by_ref = {"clip.%s" % layer["id"]: layer_notes(parsed, layer, time_scale) for layer in layers}
    result = []
    for operation in operations:
        result.append(operation)
        if operation.get("type") == "create_midi_clip":
            clip_ref = operation.get("id")
            result.append(
                {
                    "type": "add_notes",
                    "clip_ref": clip_ref,
                    "notes": notes_by_ref.get(clip_ref, []),
                }
            )
    return result


def parse_midi_file(midi_path):
    midi = mido.MidiFile(midi_path)
    notes_by_channel = defaultdict(list)
    programs = {}
    track_names_by_channel = {}
    track_name = None
    tempo = None
    time_signature = None
    max_tick = 0

    for track in midi.tracks:
        absolute_tick = 0
        local_track_name = None
        open_notes = defaultdict(list)
        for message in track:
            absolute_tick += message.time
            max_tick = max(max_tick, absolute_tick)
            if message.is_meta:
                if message.type == "track_name":
                    track_name = message.name
                    local_track_name = message.name
                elif message.type == "set_tempo" and tempo is None:
                    tempo = mido.tempo2bpm(message.tempo)
                elif message.type == "time_signature" and time_signature is None:
                    time_signature = {
                        "numerator": message.numerator,
                        "denominator": message.denominator,
                    }
                continue

            channel = getattr(message, "channel", None)
            if channel is not None and local_track_name and channel not in track_names_by_channel:
                track_names_by_channel[channel] = local_track_name
            if message.type == "program_change":
                programs[channel] = message.program
            elif message.type == "note_on" and message.velocity > 0:
                open_notes[(channel, message.note)].append((absolute_tick, message.velocity))
            elif message.type in ("note_off", "note_on"):
                queue = open_notes[(channel, message.note)]
                if not queue:
                    continue
                start_tick, velocity = queue.pop(0)
                duration_ticks = max(1, absolute_tick - start_tick)
                notes_by_channel[channel].append(
                    {
                        "pitch": message.note,
                        "start_tick": start_tick,
                        "duration_ticks": duration_ticks,
                        "velocity": velocity,
                    }
                )

    max_note_tick = 0
    for notes in notes_by_channel.values():
        for note in notes:
            max_note_tick = max(max_note_tick, note["start_tick"] + note["duration_ticks"])

    return {
        "path": str(midi_path),
        "type": midi.type,
        "ticks_per_beat": midi.ticks_per_beat,
        "track_name": track_name,
        "track_names_by_channel": track_names_by_channel,
        "tempo": tempo,
        "time_signature": time_signature,
        "programs": programs,
        "notes_by_channel": dict(notes_by_channel),
        "max_tick": max(max_tick, max_note_tick),
        "max_beat": max(max_tick, max_note_tick) / float(midi.ticks_per_beat),
    }


def select_layers(parsed):
    if is_axel_profile(parsed):
        return select_axel_layers(parsed)
    return select_general_layers(parsed)


def is_axel_profile(parsed):
    channels = set(parsed["notes_by_channel"])
    return bool(channels.intersection({7, 8, 10, 15}))


def select_axel_layers(parsed):
    channels = parsed["notes_by_channel"]
    layers = []

    if 9 in channels:
        layers.append(
            layer(
                "drums",
                "Dance Drums",
                [9],
                "Foundation Dance Kit.adg",
                "drums",
                volume=0.72,
                panning=0.0,
                effects=["Compressor"],
                drum_map=True,
            )
        )
    if 1 in channels:
        layers.append(
            layer(
                "bass",
                "Synth Bass",
                [1],
                "Retromancer Bass.adg",
                "sounds",
                volume=0.66,
                panning=0.0,
                transpose=12,
                effects=["Saturator"],
            )
        )
    if 7 in channels:
        layers.append(
            layer(
                "drive",
                "Low Drive",
                [7],
                "Detonate Bass.adg",
                "sounds",
                volume=0.42,
                panning=-0.08,
                transpose=12,
            )
        )
    if 15 in channels:
        layers.append(
            layer(
                "chords",
                "Chord Bed",
                [15],
                "Star Eyes Keys.adg",
                "sounds",
                volume=0.45,
                panning=0.12,
            )
        )
    if 8 in channels:
        layers.append(
            layer(
                "hook",
                "Main Hook",
                [8],
                "Antenna Lead.adg",
                "sounds",
                volume=0.72,
                panning=0.0,
                effects=["Auto Filter"],
            )
        )
    if 10 in channels:
        layers.append(
            layer(
                "hook-layer",
                "Hook Layer",
                [10],
                "Bouncy Castle Mallets.adg",
                "sounds",
                volume=0.44,
                panning=0.18,
                transpose=12,
            )
        )
    if 3 in channels:
        layers.append(
            layer(
                "counter",
                "Counter Lead",
                [3],
                "Raindrop Lead.adg",
                "sounds",
                volume=0.42,
                panning=-0.18,
            )
        )
    return [item for item in layers if any(channel in channels for channel in item["channels"])]


def select_general_layers(parsed):
    layers = []
    role_counts = defaultdict(int)
    for channel in sorted(parsed["notes_by_channel"], key=lambda item: general_layer_order(parsed, item)):
        if not parsed["notes_by_channel"].get(channel):
            continue
        role = classify_channel(parsed, channel)
        role_counts[role] += 1
        layer_id = "%s-%s" % (role, channel)
        layers.append(general_layer(layer_id, role, channel, role_counts[role], parsed))
    return layers


def classify_channel(parsed, channel):
    if channel == 9:
        return "drums"
    name = channel_track_name(parsed, channel).lower()
    program = parsed["programs"].get(channel)
    _pitch_min, pitch_max = channel_pitch_range(parsed, channel)
    if "drum" in name:
        return "drums"
    if "bass" in name or (program is not None and 32 <= program <= 39) or pitch_max <= 52:
        return "bass"
    if "melody" in name or "lead" in name:
        return "lead"
    if "vocal" in name or "choir" in name:
        return "vocal"
    if "string" in name:
        return "strings"
    if "overdriv" in name or "distort" in name:
        return "drive_guitar"
    if "acoustic guitar" in name or program in (24, 25):
        return "acoustic_guitar"
    if "electric guitar" in name or program in (26, 27, 28):
        return "electric_guitar"
    if "guitar" in name or program in (29, 30, 31):
        return "drive_guitar"
    return "melodic"


def general_layer_order(parsed, channel):
    role_order = {
        "drums": 0,
        "bass": 1,
        "lead": 2,
        "vocal": 3,
        "strings": 4,
        "electric_guitar": 5,
        "acoustic_guitar": 6,
        "drive_guitar": 7,
        "melodic": 8,
    }
    return (role_order.get(classify_channel(parsed, channel), 99), channel)


def general_layer(layer_id, role, channel, role_index, parsed):
    settings = {
        "drums": (
            "Dance Drums",
            "Foundation Dance Kit.adg",
            "drums",
            0.72,
            0.0,
            0,
            ["Compressor"],
            True,
            None,
            "gm",
        ),
        "bass": (
            "Bass",
            "Retromancer Bass.adg",
            "sounds",
            0.62,
            0.0,
            bass_transpose(parsed, channel),
            ["Saturator"],
            False,
        ),
        "lead": ("Main Melody", "Raindrop Lead.adg", "sounds", 0.62, 0.0, 0, ["Auto Filter"], False),
        "vocal": ("Vocal Pad", "Vocal Ambience.adg", "sounds", 0.34, 0.18, 0, [], False),
        "strings": ("Strings", "Ambient Strings.adg", "sounds", 0.38, -0.12, 0, [], False),
        "electric_guitar": (
            "Electric Guitar",
            "Guitar Electric Clean.adg",
            "sounds",
            0.44,
            -0.08,
            0,
            [],
            False,
            "query:Sounds#Guitar%20&%20Plucked:FileId_70176",
        ),
        "acoustic_guitar": (
            "Acoustic Guitar",
            "Guitar Acoustic.adg",
            "sounds",
            0.40,
            0.10,
            0,
            [],
            False,
            "query:Sounds#Guitar%20&%20Plucked:FileId_70175",
        ),
        "drive_guitar": ("Drive Guitar", "Strat Muted Guitar.adv", "sounds", 0.32, -0.18, 0, [], False),
        "melodic": ("MIDI Part", "Star Eyes Keys.adg", "sounds", 0.40, 0.0, 0, [], False),
    }
    setting = settings[role]
    browser_uri = setting[8] if len(setting) > 8 else None
    drum_map_mode = setting[9] if len(setting) > 9 else "compact"
    name, rack, root, volume, panning, transpose, effects, drum_map = setting[:8]
    if role_index > 1:
        name = "%s %s" % (name, role_index)
    return layer(
        layer_id,
        name,
        [channel],
        rack,
        root,
        volume=volume,
        panning=panning,
        transpose=transpose,
        effects=effects,
        drum_map=drum_map,
        browser_uri=browser_uri,
        drum_map_mode=drum_map_mode,
    )


def bass_transpose(parsed, channel):
    pitch_min, _pitch_max = channel_pitch_range(parsed, channel)
    return 12 if pitch_min < 36 else 0


def channel_track_name(parsed, channel):
    return parsed.get("track_names_by_channel", {}).get(channel) or "Channel %s" % (channel + 1)


def channel_pitch_range(parsed, channel):
    notes = parsed["notes_by_channel"].get(channel) or []
    if not notes:
        return 0, 0
    pitches = [note["pitch"] for note in notes]
    return min(pitches), max(pitches)


def layer(
    id_,
    name,
    channels,
    rack,
    root,
    volume,
    panning,
    transpose=0,
    effects=None,
    drum_map=False,
    browser_uri=None,
    drum_map_mode="compact",
):
    return {
        "id": id_,
        "name": name,
        "channels": channels,
        "rack": rack,
        "root": root,
        "volume": volume,
        "panning": panning,
        "transpose": transpose,
        "effects": effects or [],
        "drum_map": drum_map,
        "browser_uri": browser_uri,
        "drum_map_mode": drum_map_mode,
    }


def layer_track_name(layer, prefix):
    return "%s - %s" % (layer["name"], prefix)


def layer_clip_name(layer, prefix):
    return "%s %s" % (layer["name"], prefix)


def layer_notes(parsed, layer, time_scale):
    ticks_per_beat = parsed["ticks_per_beat"]
    result = []
    minimum_duration = max(MIN_NOTE_DURATION, round(time_scale / float(ticks_per_beat), 6))
    for channel in layer["channels"]:
        for item in parsed["notes_by_channel"].get(channel, []):
            pitch = item["pitch"]
            if layer.get("drum_map"):
                pitch = map_drum_pitch(pitch, mode=layer.get("drum_map_mode", "compact"))
            else:
                pitch += layer.get("transpose", 0)
            if pitch < 0 or pitch > 127:
                continue
            start_time = round((item["start_tick"] / float(ticks_per_beat)) * time_scale, 6)
            duration = max(
                minimum_duration,
                round((item["duration_ticks"] / float(ticks_per_beat)) * time_scale, 6),
            )
            result.append(
                {
                    "pitch": pitch,
                    "start_time": start_time,
                    "duration": duration,
                    "velocity": max(1, min(127, item["velocity"])),
                    "probability": 1.0,
                    "velocity_deviation": 0.0,
                    "release_velocity": 64,
                }
            )
    return normalize_clip_notes(result)


def normalize_clip_notes(notes):
    collapsed = {}
    for note in notes:
        key = (note["pitch"], note["start_time"])
        current = collapsed.get(key)
        if current is None:
            collapsed[key] = dict(note)
            continue
        current["duration"] = max(current["duration"], note["duration"])
        current["velocity"] = max(current["velocity"], note["velocity"])

    by_pitch = defaultdict(list)
    for note in collapsed.values():
        by_pitch[note["pitch"]].append(note)

    normalized = []
    for pitch_notes in by_pitch.values():
        pitch_notes.sort(key=lambda note: note["start_time"])
        for index, note in enumerate(pitch_notes):
            duration = note["duration"]
            if index + 1 < len(pitch_notes):
                next_start = pitch_notes[index + 1]["start_time"]
                end_time = note["start_time"] + duration
                if end_time > next_start:
                    duration = round(next_start - note["start_time"], 6)
            if duration <= 0:
                continue
            normalized_note = dict(note)
            normalized_note["duration"] = duration
            normalized.append(normalized_note)

    normalized.sort(key=lambda note: (note["start_time"], note["pitch"], note["duration"]))
    return normalized


def map_drum_pitch(pitch, mode="compact"):
    drum_map = {
        28: 36,
        35: 36,
        36: 36,
        37: 39,
        38: 38,
        40: 38,
        41: 43,
        42: 42,
        43: 43,
        44: 44,
        45: 47,
        46: 46,
        47: 47,
        48: 50,
        49: 49,
        50: 50,
        51: 51,
        57: 49,
        70: 70,
        82: 82,
    }
    if mode == "compact":
        drum_map.update({44: 42, 70: 42, 82: 42})
    return drum_map.get(pitch, pitch)


def round_up_to_bar(beats):
    bars = int((beats + 3.999999) // 4)
    return float(max(4, bars * 4))


def midi_summary(parsed):
    channels = []
    for channel, notes in sorted(parsed["notes_by_channel"].items()):
        pitches = [note["pitch"] for note in notes]
        channels.append(
            {
                "channel": channel,
                "track_name": parsed.get("track_names_by_channel", {}).get(channel),
                "program": parsed["programs"].get(channel),
                "note_count": len(notes),
                "pitch_min": min(pitches),
                "pitch_max": max(pitches),
            }
        )
    return {
        "format": parsed["type"],
        "ticks_per_beat": parsed["ticks_per_beat"],
        "track_name": parsed["track_name"],
        "source_tempo": parsed["tempo"],
        "time_signature": parsed["time_signature"],
        "max_beat": parsed["max_beat"],
        "channels": channels,
    }
