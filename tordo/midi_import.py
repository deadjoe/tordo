from collections import defaultdict
from pathlib import Path

import mido

DEFAULT_TIME_SCALE = 0.5
DEFAULT_TEMPO = 138.0


def midi_file_plan(
    midi_path,
    prefix=None,
    scene_name=None,
    tempo=DEFAULT_TEMPO,
    time_scale=DEFAULT_TIME_SCALE,
):
    parsed = parse_midi_file(midi_path)
    prefix = prefix or Path(midi_path).stem.replace("_", " ").title()
    scene_name = scene_name or ("%s MIDI Import" % prefix)
    layers = select_layers(parsed)
    clip_length = round_up_to_bar(parsed["max_beat"] * time_scale)

    operations = [
        {"type": "set_tempo", "tempo": tempo},
        {"id": "scene.main", "type": "create_scene", "index": -1, "name": scene_name},
    ]
    for layer_index, layer in enumerate(layers):
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
                "type": "add_notes",
                "clip_ref": clip_ref,
                "notes": layer_notes(parsed, layer, time_scale),
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

    operations.append({"type": "fire_scene", "scene_ref": "scene.main"})
    return {
        "plan_version": 1,
        "name": "midi-file-import",
        "description": "Import a MIDI file into Live tracks with role-based racks and effects.",
        "source_midi": str(midi_path),
        "midi_summary": midi_summary(parsed),
        "operations": operations,
    }


def parse_midi_file(midi_path):
    midi = mido.MidiFile(midi_path)
    notes_by_channel = defaultdict(list)
    programs = {}
    track_name = None
    tempo = None
    time_signature = None
    max_tick = 0

    for track in midi.tracks:
        absolute_tick = 0
        open_notes = defaultdict(list)
        for message in track:
            absolute_tick += message.time
            max_tick = max(max_tick, absolute_tick)
            if message.is_meta:
                if message.type == "track_name":
                    track_name = message.name
                elif message.type == "set_tempo" and tempo is None:
                    tempo = mido.tempo2bpm(message.tempo)
                elif message.type == "time_signature" and time_signature is None:
                    time_signature = {
                        "numerator": message.numerator,
                        "denominator": message.denominator,
                    }
                continue

            channel = getattr(message, "channel", None)
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
        "tempo": tempo,
        "time_signature": time_signature,
        "programs": programs,
        "notes_by_channel": dict(notes_by_channel),
        "max_tick": max(max_tick, max_note_tick),
        "max_beat": max(max_tick, max_note_tick) / float(midi.ticks_per_beat),
    }


def select_layers(parsed):
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


def layer(id_, name, channels, rack, root, volume, panning, transpose=0, effects=None, drum_map=False):
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
    }


def layer_track_name(layer, prefix):
    return "%s - %s" % (layer["name"], prefix)


def layer_clip_name(layer, prefix):
    return "%s %s" % (layer["name"], prefix)


def layer_notes(parsed, layer, time_scale):
    ticks_per_beat = parsed["ticks_per_beat"]
    result = []
    seen = set()
    for channel in layer["channels"]:
        for item in parsed["notes_by_channel"].get(channel, []):
            pitch = item["pitch"]
            if layer.get("drum_map"):
                pitch = map_drum_pitch(pitch)
            else:
                pitch += layer.get("transpose", 0)
            if pitch < 0 or pitch > 127:
                continue
            start_time = round((item["start_tick"] / float(ticks_per_beat)) * time_scale, 6)
            duration = max(0.03125, round((item["duration_ticks"] / float(ticks_per_beat)) * time_scale, 6))
            dedupe_key = (pitch, start_time, duration)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
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
    result.sort(key=lambda note: (note["start_time"], note["pitch"], note["duration"]))
    return result


def map_drum_pitch(pitch):
    drum_map = {
        28: 36,
        36: 36,
        37: 39,
        38: 38,
        44: 42,
        46: 46,
        57: 49,
        82: 42,
    }
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
