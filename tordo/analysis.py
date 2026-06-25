import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from tordo.paths import ensure_parent, tmp_path

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
BAR_LENGTH = 4.0
PHRASE_BARS = 4

PERCUSSIVE_HINTS = [
    "drum",
    "kick",
    "snare",
    "hat",
    "clap",
    "tom",
    "cymbal",
    "perc",
    "percussion",
]

CHORD_TEMPLATES = [
    ("maj7", [0, 4, 7, 11]),
    ("m7", [0, 3, 7, 10]),
    ("7", [0, 4, 7, 10]),
    ("m", [0, 3, 7]),
    ("maj", [0, 4, 7]),
    ("dim", [0, 3, 6]),
    ("sus2", [0, 2, 7]),
    ("sus4", [0, 5, 7]),
    ("5", [0, 7]),
]

GM_DRUM_NAMES = {
    35: "Acoustic Bass Drum",
    36: "Bass Drum 1",
    37: "Side Stick",
    38: "Acoustic Snare",
    39: "Hand Clap",
    40: "Electric Snare",
    41: "Low Floor Tom",
    42: "Closed Hi-Hat",
    43: "High Floor Tom",
    44: "Pedal Hi-Hat",
    45: "Low Tom",
    46: "Open Hi-Hat",
    47: "Low-Mid Tom",
    48: "Hi-Mid Tom",
    49: "Crash Cymbal 1",
    50: "High Tom",
    51: "Ride Cymbal 1",
}


def load_set_notes(path):
    data = json.loads(Path(path).read_text())
    if not data.get("ok"):
        raise ValueError("set-notes response is not ok")
    payload = data.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("set-notes response has no payload object")
    return payload


def analyze_set_notes(payload):
    clips = payload.get("clips", [])
    clip_analyses = [analyze_clip(clip) for clip in clips]
    tonal_notes = []
    all_notes = []

    for clip, clip_analysis in zip(clips, clip_analyses):
        notes = clip.get("notes", [])
        all_notes.extend(notes)
        if clip_analysis.get("role") != "percussive":
            tonal_notes.extend(notes)

    timeline = analyze_timeline(clips, clip_analyses)
    return {
        "song": payload.get("song", {}),
        "midi_clip_count": len(clips),
        "total_note_count": len(all_notes),
        "tonal_note_count": len(tonal_notes),
        "estimated_key": estimate_key(tonal_notes),
        "timeline": timeline,
        "clips": clip_analyses,
    }


def analyze_clip(clip_payload):
    notes = sorted_notes(clip_payload.get("notes", []))
    clip = clip_payload.get("clip") or {}
    track = clip_payload.get("track") or {}
    scene = clip_payload.get("scene") or {}
    role = infer_clip_role(track.get("name"), clip.get("name"))

    pitch_values = [note["pitch"] for note in notes if note.get("pitch") is not None]
    velocity_values = [note["velocity"] for note in notes if note.get("velocity") is not None]
    starts = [note["start_time"] for note in notes if note.get("start_time") is not None]
    ends = [
        note["start_time"] + note["duration"]
        for note in notes
        if note.get("start_time") is not None and note.get("duration") is not None
    ]

    analysis = {
        "track_index": clip_payload.get("track_index"),
        "scene_index": clip_payload.get("scene_index"),
        "track_name": track.get("name"),
        "scene_name": scene.get("name"),
        "clip_name": clip.get("name"),
        "role": role,
        "clip_length": clip.get("length"),
        "note_count": len(notes),
        "source": clip_payload.get("source"),
        "truncated": clip_payload.get("truncated", False),
        "pitch_range": range_or_none(pitch_values),
        "pitch_names": [midi_note_name(pitch) for pitch in sorted(set(pitch_values))],
        "pitch_class_distribution": pitch_class_distribution(notes),
        "top_pitches": top_pitches(notes),
        "velocity_range": range_or_none(velocity_values),
        "velocity_stats": numeric_stats(velocity_values),
        "duration_stats": numeric_stats([note.get("duration") for note in notes]),
        "duration_histogram": duration_histogram(notes),
        "time_range": range_or_none(starts, ends),
        "notes_per_bar": notes_per_bar(notes, BAR_LENGTH),
        "phrase_blocks": phrase_blocks(notes, BAR_LENGTH, PHRASE_BARS),
        "activity_segments": activity_segments(notes, BAR_LENGTH),
        "onset_positions": onset_positions(notes, BAR_LENGTH),
        "estimated_key": None if role == "percussive" else estimate_key(notes),
    }

    if role == "percussive":
        analysis["percussion_lanes"] = percussion_lanes(notes)
    else:
        events = top_voice_events(notes)
        analysis["melodic_profile"] = melodic_profile(events)
        analysis["motifs"] = repeated_motifs(events)

    return analysis


def analyze_timeline(clips, clip_analyses):
    max_end = 0.0
    for clip in clips:
        for note in clip.get("notes", []):
            max_end = max(max_end, note_end(note))
        clip_length = (clip.get("clip") or {}).get("length")
        if isinstance(clip_length, (int, float)):
            max_end = max(max_end, float(clip_length))

    bar_count = int(math.ceil(max_end / BAR_LENGTH)) if max_end else 0
    bars = []
    role_by_track = {clip["track_index"]: clip.get("role") for clip in clip_analyses}

    for bar_index in range(bar_count):
        start = bar_index * BAR_LENGTH
        end = start + BAR_LENGTH
        bar_notes = []
        tonal_notes = []
        percussive_notes = []
        active_clips = []

        for clip in clips:
            role = role_by_track.get(clip.get("track_index"), "tonal")
            notes_in_bar = notes_starting_in_range(clip.get("notes", []), start, end)
            if not notes_in_bar:
                continue
            active_clips.append(
                {
                    "track_index": clip.get("track_index"),
                    "clip_name": (clip.get("clip") or {}).get("name"),
                    "role": role,
                    "note_count": len(notes_in_bar),
                }
            )
            bar_notes.extend(notes_in_bar)
            if role == "percussive":
                percussive_notes.extend(notes_in_bar)
            else:
                tonal_notes.extend(notes_in_bar)

        bars.append(
            {
                "bar": bar_index + 1,
                "start_time": start,
                "end_time": end,
                "note_count": len(bar_notes),
                "tonal_note_count": len(tonal_notes),
                "percussive_note_count": len(percussive_notes),
                "active_clips": active_clips,
                "pitch_classes": pitch_class_names(tonal_notes),
                "estimated_chord": estimate_chord(tonal_notes),
            }
        )

    return {
        "bar_length": BAR_LENGTH,
        "bar_count": bar_count,
        "bars": bars,
        "sections": timeline_sections(bars, PHRASE_BARS),
        "chord_progression": compact_chord_progression(bars),
    }


def infer_clip_role(track_name, clip_name):
    text = "%s %s" % (track_name or "", clip_name or "")
    text = text.lower()
    if any(hint in text for hint in PERCUSSIVE_HINTS):
        return "percussive"
    return "tonal"


def estimate_key(notes):
    pitch_classes = weighted_pitch_classes(notes)
    if not any(pitch_classes):
        return None

    candidates = []
    for root in range(12):
        candidates.append(key_score(root, "major", MAJOR_PROFILE, pitch_classes))
        candidates.append(key_score(root, "minor", MINOR_PROFILE, pitch_classes))
    candidates.sort(key=lambda item: item["score"], reverse=True)
    best = candidates[0]
    runner_up = candidates[1] if len(candidates) > 1 else None
    confidence = best["score"] - (runner_up["score"] if runner_up else 0)
    return {
        "name": "%s %s" % (NOTE_NAMES[best["root"]], best["mode"]),
        "score": round(best["score"], 4),
        "confidence": round(confidence, 4),
        "runner_up": (
            {
                "name": "%s %s" % (NOTE_NAMES[runner_up["root"]], runner_up["mode"]),
                "score": round(runner_up["score"], 4),
            }
            if runner_up
            else None
        ),
    }


def estimate_chord(notes):
    weights = pitch_class_weights(notes)
    if not weights:
        return None

    total_weight = sum(weights.values())
    best = None
    for root in range(12):
        for quality, intervals in CHORD_TEMPLATES:
            template = {(root + interval) % 12 for interval in intervals}
            inside = sum(weight for pitch_class, weight in weights.items() if pitch_class in template)
            outside = total_weight - inside
            root_weight = weights.get(root, 0)
            score = inside + (root_weight * 0.35) - (outside * 0.25)
            candidate = {
                "root": root,
                "quality": quality,
                "score": score,
                "coverage": inside / total_weight if total_weight else 0,
            }
            if best is None or candidate["score"] > best["score"]:
                best = candidate

    if not best or best["coverage"] < 0.45:
        return None
    return {
        "name": chord_name(best["root"], best["quality"]),
        "coverage": round(best["coverage"], 3),
        "pitch_classes": pitch_class_names(notes),
    }


def key_score(root, mode, profile, pitch_classes):
    score = 0.0
    for pitch_class, weight in enumerate(pitch_classes):
        profile_index = (pitch_class - root) % 12
        score += weight * profile[profile_index]
    return {"root": root, "mode": mode, "score": score}


def weighted_pitch_classes(notes):
    counts = [0.0] * 12
    total = 0.0
    for note in notes:
        pitch = note.get("pitch")
        if pitch is None:
            continue
        weight = note_weight(note)
        counts[int(pitch) % 12] += weight
        total += weight
    if total <= 0:
        return counts
    return [value / total for value in counts]


def pitch_class_weights(notes):
    weights = defaultdict(float)
    for note in notes:
        pitch = note.get("pitch")
        if pitch is not None:
            weights[int(pitch) % 12] += note_weight(note)
    return dict(weights)


def pitch_class_distribution(notes):
    weights = pitch_class_weights(notes)
    total = sum(weights.values())
    items = []
    for pitch_class, weight in sorted(weights.items()):
        items.append(
            {
                "pitch_class": pitch_class,
                "name": NOTE_NAMES[pitch_class],
                "weight": round(weight, 4),
                "share": round(weight / total, 4) if total else 0,
            }
        )
    return items


def top_pitches(notes, limit=10):
    counts = Counter()
    for note in notes:
        pitch = note.get("pitch")
        if pitch is not None:
            counts[int(pitch)] += 1
    return [
        {
            "pitch": pitch,
            "name": midi_note_name(pitch),
            "count": count,
        }
        for pitch, count in counts.most_common(limit)
    ]


def notes_per_bar(notes, bar_length):
    bars = defaultdict(int)
    for note in notes:
        start = note.get("start_time")
        if start is None:
            continue
        bars[int(float(start) // bar_length)] += 1
    return [{"bar": index + 1, "count": bars[index]} for index in sorted(bars)]


def phrase_blocks(notes, bar_length, phrase_bars):
    blocks = defaultdict(int)
    for note in notes:
        start = note.get("start_time")
        if start is None:
            continue
        bar = int(float(start) // bar_length)
        block = bar // phrase_bars
        blocks[block] += 1
    return [
        {
            "bars": [block * phrase_bars + 1, (block + 1) * phrase_bars],
            "note_count": blocks[block],
        }
        for block in sorted(blocks)
    ]


def activity_segments(notes, bar_length):
    active_bars = sorted(
        {
            int(float(note["start_time"]) // bar_length)
            for note in notes
            if note.get("start_time") is not None
        }
    )
    if not active_bars:
        return []

    segments = []
    start = active_bars[0]
    previous = active_bars[0]
    for bar in active_bars[1:]:
        if bar == previous + 1:
            previous = bar
            continue
        segments.append({"bars": [start + 1, previous + 1]})
        start = bar
        previous = bar
    segments.append({"bars": [start + 1, previous + 1]})
    return segments


def onset_positions(notes, bar_length, limit=12):
    counts = Counter()
    for note in notes:
        start = note.get("start_time")
        if start is None:
            continue
        position = round(float(start) % bar_length, 3)
        counts[position] += 1
    return [{"beat": beat, "count": count} for beat, count in counts.most_common(limit)]


def duration_histogram(notes, limit=12):
    counts = Counter()
    for note in notes:
        duration = note.get("duration")
        if duration is not None:
            counts[round(float(duration), 3)] += 1
    return [{"duration": duration, "count": count} for duration, count in counts.most_common(limit)]


def top_voice_events(notes):
    grouped = defaultdict(list)
    for note in notes:
        start = note.get("start_time")
        pitch = note.get("pitch")
        if start is None or pitch is None:
            continue
        grouped[round(float(start), 6)].append(note)

    events = []
    for start in sorted(grouped):
        group = grouped[start]
        top_note = max(group, key=lambda item: item.get("pitch", -1))
        events.append(
            {
                "start_time": start,
                "pitch": top_note.get("pitch"),
                "name": midi_note_name(top_note.get("pitch")),
                "duration": top_note.get("duration"),
                "chord_size": len(group),
            }
        )
    return events


def melodic_profile(events):
    if not events:
        return None

    intervals = []
    for previous, current in zip(events, events[1:]):
        intervals.append(current["pitch"] - previous["pitch"])

    interval_counts = Counter(intervals)
    leap_count = sum(1 for interval in intervals if abs(interval) >= 5)
    step_count = sum(1 for interval in intervals if 0 < abs(interval) <= 2)
    repeated_count = sum(1 for interval in intervals if interval == 0)

    return {
        "event_count": len(events),
        "first_events": events[:12],
        "direction": {
            "ascending": sum(1 for interval in intervals if interval > 0),
            "descending": sum(1 for interval in intervals if interval < 0),
            "repeated": repeated_count,
        },
        "motion": {
            "step_count": step_count,
            "leap_count": leap_count,
            "largest_leap": max((abs(interval) for interval in intervals), default=0),
        },
        "top_intervals": [
            {"interval": interval, "count": count}
            for interval, count in interval_counts.most_common(10)
        ],
    }


def repeated_motifs(events, window_size=4, limit=8):
    if len(events) < window_size:
        return []

    motifs = defaultdict(list)
    for index in range(0, len(events) - window_size + 1):
        window = events[index : index + window_size]
        intervals = tuple(window[i + 1]["pitch"] - window[i]["pitch"] for i in range(window_size - 1))
        durations = tuple(round(float(event.get("duration") or 0), 3) for event in window)
        token = (intervals, durations)
        motifs[token].append(window)

    repeated = []
    for (intervals, durations), occurrences in motifs.items():
        if len(occurrences) < 2:
            continue
        first = occurrences[0]
        repeated.append(
            {
                "count": len(occurrences),
                "intervals": list(intervals),
                "durations": list(durations),
                "example_pitches": [event["name"] for event in first],
                "starts": [round(window[0]["start_time"], 3) for window in occurrences[:12]],
                "start_bars": [int(window[0]["start_time"] // BAR_LENGTH) + 1 for window in occurrences[:12]],
            }
        )

    repeated.sort(key=lambda item: (item["count"], len(set(item["start_bars"]))), reverse=True)
    return repeated[:limit]


def percussion_lanes(notes):
    lanes = defaultdict(list)
    for note in notes:
        pitch = note.get("pitch")
        if pitch is not None:
            lanes[int(pitch)].append(note)

    summaries = []
    for pitch, lane_notes in lanes.items():
        starts = [note["start_time"] for note in lane_notes if note.get("start_time") is not None]
        summaries.append(
            {
                "pitch": pitch,
                "name": GM_DRUM_NAMES.get(pitch, midi_note_name(pitch)),
                "count": len(lane_notes),
                "first_start": min(starts) if starts else None,
                "last_start": max(starts) if starts else None,
                "notes_per_bar": notes_per_bar(lane_notes, BAR_LENGTH),
                "onset_positions": onset_positions(lane_notes, BAR_LENGTH, limit=8),
            }
        )
    summaries.sort(key=lambda item: item["count"], reverse=True)
    return summaries


def timeline_sections(bars, phrase_bars):
    sections = []
    for index in range(0, len(bars), phrase_bars):
        block = bars[index : index + phrase_bars]
        chord_names = []
        for bar in block:
            chord = bar.get("estimated_chord")
            chord_names.append(chord["name"] if chord else "-")
        sections.append(
            {
                "bars": [index + 1, index + len(block)],
                "note_count": sum(bar["note_count"] for bar in block),
                "tonal_note_count": sum(bar["tonal_note_count"] for bar in block),
                "percussive_note_count": sum(bar["percussive_note_count"] for bar in block),
                "chords": chord_names,
            }
        )
    return sections


def compact_chord_progression(bars):
    progression = []
    previous = None
    start_bar = None
    for bar in bars:
        chord = bar.get("estimated_chord")
        name = chord["name"] if chord else "-"
        if name != previous:
            if previous is not None:
                progression.append({"bars": [start_bar, bar["bar"] - 1], "chord": previous})
            previous = name
            start_bar = bar["bar"]
    if previous is not None:
        progression.append({"bars": [start_bar, bars[-1]["bar"]], "chord": previous})
    return progression


def notes_starting_in_range(notes, start, end):
    return [
        note
        for note in notes
        if note.get("start_time") is not None and start <= float(note["start_time"]) < end
    ]


def sorted_notes(notes):
    return sorted(
        notes,
        key=lambda note: (
            note.get("start_time", 0),
            note.get("pitch", 0),
            note.get("duration", 0),
        ),
    )


def numeric_stats(values):
    clean = [float(value) for value in values if isinstance(value, (int, float))]
    if not clean:
        return None
    clean.sort()
    return {
        "min": clean[0],
        "max": clean[-1],
        "mean": round(sum(clean) / len(clean), 4),
        "median": median(clean),
    }


def median(values):
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return round((values[midpoint - 1] + values[midpoint]) / 2, 4)


def range_or_none(values, alternate_values=None):
    if alternate_values is None:
        alternate_values = values
    if not values or not alternate_values:
        return None
    return [min(values), max(alternate_values)]


def note_end(note):
    return float(note.get("start_time") or 0) + float(note.get("duration") or 0)


def note_weight(note):
    duration = note.get("duration")
    return duration if isinstance(duration, (int, float)) and duration > 0 else 1.0


def pitch_class_names(notes):
    return [NOTE_NAMES[pitch_class] for pitch_class in sorted(pitch_class_weights(notes))]


def midi_note_name(pitch):
    pitch = int(pitch)
    octave = pitch // 12 - 1
    return "%s%s" % (NOTE_NAMES[pitch % 12], octave)


def chord_name(root, quality):
    if quality == "maj":
        return NOTE_NAMES[root]
    return "%s%s" % (NOTE_NAMES[root], quality)


def format_markdown(analysis):
    song = analysis.get("song") or {}
    timeline = analysis.get("timeline") or {}
    lines = [
        "# Tordo Set Note Analysis",
        "",
        "## Song",
        "",
        "- Name: %s" % (song.get("name") or ""),
        "- Tempo: %s" % song.get("tempo"),
        "- MIDI clips: %s" % analysis.get("midi_clip_count"),
        "- Total notes: %s" % analysis.get("total_note_count"),
        "- Tonal notes used for key estimate: %s" % analysis.get("tonal_note_count"),
        "- Bars: %s" % timeline.get("bar_count"),
    ]
    estimated_key = analysis.get("estimated_key")
    if estimated_key:
        lines.append("- Estimated key: %s" % estimated_key["name"])

    lines.extend(format_timeline_markdown(timeline))
    lines.extend(["", "## Clips", ""])
    for clip in analysis.get("clips", []):
        lines.extend(format_clip_markdown(clip))
    return "\n".join(lines) + "\n"


def format_timeline_markdown(timeline):
    lines = ["", "## Timeline", ""]
    sections = timeline.get("sections") or []
    if sections:
        lines.append("### 4-bar sections")
        lines.append("")
        for section in sections:
            lines.append(
                "- Bars %s-%s: notes=%s tonal=%s perc=%s chords=%s"
                % (
                    section["bars"][0],
                    section["bars"][1],
                    section["note_count"],
                    section["tonal_note_count"],
                    section["percussive_note_count"],
                    " | ".join(section["chords"]),
                )
            )

    progression = timeline.get("chord_progression") or []
    if progression:
        lines.extend(["", "### Compact chord progression", ""])
        lines.append(
            "- "
            + " -> ".join(
                "bars %s-%s: %s" % (item["bars"][0], item["bars"][1], item["chord"])
                for item in progression
            )
        )
    return lines


def format_clip_markdown(clip):
    lines = [
        "### Track %s / Scene %s: %s" % (
            clip.get("track_index"),
            clip.get("scene_index"),
            clip.get("clip_name") or "",
        ),
        "",
        "- Track: %s" % (clip.get("track_name") or ""),
        "- Role: %s" % (clip.get("role") or ""),
        "- Notes: %s" % clip.get("note_count"),
        "- Length: %s" % clip.get("clip_length"),
        "- Pitch range: %s" % format_range(clip.get("pitch_range"), midi=True),
        "- Unique pitches: %s" % ", ".join(clip.get("pitch_names") or []),
        "- Velocity range: %s" % format_range(clip.get("velocity_range")),
        "- Duration stats: %s" % format_stats(clip.get("duration_stats")),
    ]
    estimated_key = clip.get("estimated_key")
    if estimated_key:
        lines.append("- Estimated key: %s" % estimated_key["name"])

    append_short_list(lines, "Top pitches", clip.get("top_pitches"), format_pitch_count)
    append_short_list(lines, "Durations", clip.get("duration_histogram"), format_duration_count)
    append_short_list(lines, "Onsets in bar", clip.get("onset_positions"), format_onset_count)
    append_short_list(lines, "Notes per bar", clip.get("notes_per_bar"), format_bar_count)
    append_short_list(lines, "Phrase blocks", clip.get("phrase_blocks"), format_phrase_block)

    if clip.get("role") == "percussive":
        append_short_list(lines, "Percussion lanes", clip.get("percussion_lanes"), format_percussion_lane)
    else:
        profile = clip.get("melodic_profile")
        if profile:
            lines.append(
                "- Melodic motion: up=%s down=%s repeated=%s steps=%s leaps=%s largest_leap=%s"
                % (
                    profile["direction"]["ascending"],
                    profile["direction"]["descending"],
                    profile["direction"]["repeated"],
                    profile["motion"]["step_count"],
                    profile["motion"]["leap_count"],
                    profile["motion"]["largest_leap"],
                )
            )
        append_short_list(lines, "Repeated motifs", clip.get("motifs"), format_motif, limit=5)

    lines.append("")
    return lines


def append_short_list(lines, label, values, formatter, limit=10):
    if not values:
        return
    lines.append("- %s: %s" % (label, ", ".join(formatter(item) for item in values[:limit])))


def format_range(value, midi=False):
    if not value:
        return ""
    if midi:
        return "%s..%s" % (midi_note_name(value[0]), midi_note_name(value[1]))
    return "%s..%s" % (value[0], value[1])


def format_stats(value):
    if not value:
        return ""
    return "min=%s max=%s mean=%s median=%s" % (
        value["min"],
        value["max"],
        value["mean"],
        value["median"],
    )


def format_pitch_count(item):
    return "%s:%s" % (item["name"], item["count"])


def format_duration_count(item):
    return "%s:%s" % (item["duration"], item["count"])


def format_onset_count(item):
    return "%s:%s" % (item["beat"], item["count"])


def format_bar_count(item):
    return "%s:%s" % (item["bar"], item["count"])


def format_phrase_block(item):
    return "%s-%s:%s" % (item["bars"][0], item["bars"][1], item["note_count"])


def format_percussion_lane(item):
    return "%s/%s:%s" % (item["name"], midi_note_name(item["pitch"]), item["count"])


def format_motif(item):
    starts = "/".join(str(bar) for bar in item["start_bars"][:6])
    return "%sx %s bars=%s" % (item["count"], "-".join(item["example_pitches"]), starts)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze JSON generated by `python3 -m tordo.client set-notes`."
    )
    parser.add_argument("input", nargs="?", default=tmp_path("set-notes.json"))
    parser.add_argument("--json-out", default=tmp_path("set-analysis.json"))
    parser.add_argument("--md-out", default=tmp_path("set-analysis.md"))
    args = parser.parse_args(argv)

    payload = load_set_notes(args.input)
    analysis = analyze_set_notes(payload)
    ensure_parent(args.json_out).write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n")
    ensure_parent(args.md_out).write_text(format_markdown(analysis))
    print("wrote %s" % args.json_out)
    print("wrote %s" % args.md_out)


if __name__ == "__main__":
    main()
