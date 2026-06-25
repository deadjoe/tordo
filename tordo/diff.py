import argparse
import json
from pathlib import Path

from tordo.paths import ensure_parent, tmp_path


def load_archive(path):
    root = Path(path)
    manifest = read_json(root / "manifest.json")
    analysis = read_json(root / "analysis.json")
    snapshot = read_json(root / "snapshot.json")
    set_notes = read_json(root / "set-notes.json")
    return {
        "root": root,
        "manifest": manifest,
        "analysis": analysis,
        "snapshot": snapshot,
        "set_notes": set_notes,
    }


def diff_archives(before_path, after_path):
    before = load_archive(before_path)
    after = load_archive(after_path)

    return {
        "before": str(before["root"]),
        "after": str(after["root"]),
        "song": diff_song(before["manifest"], after["manifest"]),
        "counts": diff_counts(before["manifest"], after["manifest"]),
        "clips": diff_clips(before["analysis"], after["analysis"]),
        "tracks": diff_tracks(before["snapshot"], after["snapshot"]),
        "return_tracks": diff_return_tracks(before["snapshot"], after["snapshot"]),
        "summary": summarize_diff(before, after),
    }


def diff_song(before_manifest, after_manifest):
    return diff_mapping(before_manifest.get("song", {}), after_manifest.get("song", {}))


def diff_counts(before_manifest, after_manifest):
    return diff_mapping(before_manifest.get("counts", {}), after_manifest.get("counts", {}))


def diff_tracks(before_snapshot, after_snapshot):
    return diff_track_collection(before_snapshot, after_snapshot, "tracks")


def diff_return_tracks(before_snapshot, after_snapshot):
    return diff_track_collection(before_snapshot, after_snapshot, "return_tracks")


def diff_track_collection(before_snapshot, after_snapshot, collection_name):
    before_tracks = index_by_track_key((before_snapshot.get("payload") or {}).get(collection_name, []))
    after_tracks = index_by_track_key((after_snapshot.get("payload") or {}).get(collection_name, []))
    common_keys = sorted(set(before_tracks) & set(after_tracks), key=int)

    changed = []
    for key in common_keys:
        changes = diff_track(before_tracks[key], after_tracks[key])
        if changes:
            changed.append(
                {
                    "track": track_label(after_tracks[key]),
                    "changes": changes,
                }
            )

    return {
        "added": [track_label(after_tracks[key]) for key in sorted(set(after_tracks) - set(before_tracks), key=int)],
        "removed": [track_label(before_tracks[key]) for key in sorted(set(before_tracks) - set(after_tracks), key=int)],
        "changed": changed,
    }


def diff_track(before, after):
    changes = {}
    for field in ("name", "arm", "mute", "solo"):
        if before.get(field) != after.get(field):
            changes[field] = {"before": before.get(field), "after": after.get(field)}

    before_mixer = before.get("mixer") or {}
    after_mixer = after.get("mixer") or {}
    for field in ("volume", "panning"):
        before_value = parameter_value((before_mixer.get(field) or {}))
        after_value = parameter_value((after_mixer.get(field) or {}))
        if before_value != after_value:
            changes[field] = {"before": before_value, "after": after_value}

    before_sends = before_mixer.get("sends") or []
    after_sends = after_mixer.get("sends") or []
    for index in sorted(set(range(len(before_sends))) | set(range(len(after_sends)))):
        before_value = parameter_value(safe_index(before_sends, index) or {})
        after_value = parameter_value(safe_index(after_sends, index) or {})
        if before_value != after_value:
            changes["send:%s" % index] = {"before": before_value, "after": after_value}

    device_changes = diff_devices(before.get("devices") or [], after.get("devices") or [])
    changes.update(device_changes)
    return changes


def diff_devices(before_devices, after_devices):
    changes = {}
    common_indices = sorted(set(range(len(before_devices))) & set(range(len(after_devices))))
    for device_index in common_indices:
        before_device = before_devices[device_index]
        after_device = after_devices[device_index]
        if before_device.get("name") != after_device.get("name"):
            changes["device:%s:name" % device_index] = {
                "before": before_device.get("name"),
                "after": after_device.get("name"),
            }
            continue
        changes.update(diff_device_parameters(device_index, before_device, after_device))
    return changes


def diff_device_parameters(device_index, before_device, after_device):
    changes = {}
    before_parameters = before_device.get("parameters") or []
    after_parameters = after_device.get("parameters") or []
    common_indices = sorted(set(range(len(before_parameters))) & set(range(len(after_parameters))))
    for parameter_index in common_indices:
        before_parameter = before_parameters[parameter_index]
        after_parameter = after_parameters[parameter_index]
        before_value = parameter_value(before_parameter)
        after_value = parameter_value(after_parameter)
        if before_value == after_value:
            continue
        key = "device:%s:%s:%s" % (
            device_index,
            parameter_index,
            after_parameter.get("name") or before_parameter.get("name") or "",
        )
        changes[key] = {"before": before_value, "after": after_value}
    return changes


def diff_clips(before_analysis, after_analysis):
    before_clips = {clip_key(clip): clip for clip in before_analysis.get("clips", [])}
    after_clips = {clip_key(clip): clip for clip in after_analysis.get("clips", [])}
    common_keys = sorted(set(before_clips) & set(after_clips))

    changed = []
    for key in common_keys:
        before = before_clips[key]
        after = after_clips[key]
        changes = diff_clip(before, after)
        if changes:
            changed.append({"clip": key, "changes": changes})

    return {
        "added": sorted(set(after_clips) - set(before_clips)),
        "removed": sorted(set(before_clips) - set(after_clips)),
        "changed": changed,
    }


def diff_clip(before, after):
    changes = {}
    fields = ["note_count", "role", "clip_length", "pitch_range", "velocity_range"]
    for field in fields:
        if before.get(field) != after.get(field):
            changes[field] = {"before": before.get(field), "after": after.get(field)}

    before_key = key_name(before.get("estimated_key"))
    after_key = key_name(after.get("estimated_key"))
    if before_key != after_key:
        changes["estimated_key"] = {"before": before_key, "after": after_key}

    before_top = compact_top_pitches(before.get("top_pitches") or [])
    after_top = compact_top_pitches(after.get("top_pitches") or [])
    if before_top != after_top:
        changes["top_pitches"] = {"before": before_top, "after": after_top}

    return changes


def summarize_diff(before, after):
    before_counts = before["manifest"].get("counts", {})
    after_counts = after["manifest"].get("counts", {})
    total_notes_delta = (after_counts.get("total_notes") or 0) - (before_counts.get("total_notes") or 0)
    midi_clips_delta = (after_counts.get("midi_clips") or 0) - (before_counts.get("midi_clips") or 0)
    tracks_delta = (after_counts.get("tracks") or 0) - (before_counts.get("tracks") or 0)
    before_key = key_name(before["manifest"].get("estimated_key"))
    after_key = key_name(after["manifest"].get("estimated_key"))
    return {
        "total_notes_delta": total_notes_delta,
        "midi_clips_delta": midi_clips_delta,
        "tracks_delta": tracks_delta,
        "estimated_key_before": before_key,
        "estimated_key_after": after_key,
        "estimated_key_changed": before_key != after_key,
    }


def diff_mapping(before, after):
    changes = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes[key] = {"before": before.get(key), "after": after.get(key)}
    return changes


def clip_key(clip):
    return "%s:%s:%s:%s" % (
        clip.get("track_index"),
        clip.get("scene_index"),
        clip.get("track_name") or "",
        clip.get("clip_name") or "",
    )


def key_name(value):
    if not value:
        return None
    return value.get("name")


def compact_top_pitches(values, limit=8):
    return ["%s:%s" % (item.get("name"), item.get("count")) for item in values[:limit]]


def index_by_name(items):
    result = {}
    for item in items:
        name = item.get("name")
        if name:
            result[name] = item
    return result


def index_by_track_key(items):
    result = {}
    for item in items:
        index = item.get("index")
        if index is not None:
            result[str(index)] = item
    return result


def track_label(track):
    return "%s:%s" % (track.get("index"), track.get("name") or "")


def parameter_value(parameter):
    value = parameter.get("value")
    if isinstance(value, float):
        return round(value, 6)
    return value


def safe_index(values, index):
    try:
        return values[index]
    except Exception:
        return None


def read_json(path):
    return json.loads(path.read_text())


def write_diff_markdown(diff, path):
    lines = [
        "# Tordo Archive Diff",
        "",
        "- Before: %s" % diff["before"],
        "- After: %s" % diff["after"],
        "- Total notes delta: %s" % diff["summary"]["total_notes_delta"],
        "- MIDI clips delta: %s" % diff["summary"]["midi_clips_delta"],
        "- Tracks delta: %s" % diff["summary"]["tracks_delta"],
        "- Estimated key: %s -> %s"
        % (diff["summary"]["estimated_key_before"], diff["summary"]["estimated_key_after"]),
        "",
        "## Clip Changes",
        "",
    ]

    clips = diff.get("clips", {})
    if clips.get("added"):
        lines.append("- Added: %s" % ", ".join(clips["added"]))
    if clips.get("removed"):
        lines.append("- Removed: %s" % ", ".join(clips["removed"]))
    if not clips.get("changed"):
        lines.append("- No changed common clips.")
    else:
        for item in clips["changed"]:
            lines.append("### %s" % item["clip"])
            for field, change in item["changes"].items():
                lines.append("- %s: %s -> %s" % (field, change["before"], change["after"]))
            lines.append("")

    lines.extend(["", "## Track Changes", ""])
    tracks = diff.get("tracks", {})
    if tracks.get("added"):
        lines.append("- Added: %s" % ", ".join(tracks["added"]))
    if tracks.get("removed"):
        lines.append("- Removed: %s" % ", ".join(tracks["removed"]))
    if not tracks.get("changed"):
        lines.append("- No changed common tracks.")
    else:
        for item in tracks["changed"]:
            lines.append("### %s" % item["track"])
            for field, change in item["changes"].items():
                lines.append("- %s: %s -> %s" % (field, change["before"], change["after"]))
            lines.append("")

    lines.extend(["", "## Return Track Changes", ""])
    return_tracks = diff.get("return_tracks", {})
    if return_tracks.get("added"):
        lines.append("- Added: %s" % ", ".join(return_tracks["added"]))
    if return_tracks.get("removed"):
        lines.append("- Removed: %s" % ", ".join(return_tracks["removed"]))
    if not return_tracks.get("changed"):
        lines.append("- No changed common return tracks.")
    else:
        for item in return_tracks["changed"]:
            lines.append("### %s" % item["track"])
            for field, change in item["changes"].items():
                lines.append("- %s: %s -> %s" % (field, change["before"], change["after"]))
            lines.append("")

    ensure_parent(path).write_text("\n".join(lines).rstrip() + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Diff two Tordo export archives.")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--json-out", default=tmp_path("archive-diff.json"))
    parser.add_argument("--md-out", default=tmp_path("archive-diff.md"))
    args = parser.parse_args(argv)

    diff = diff_archives(args.before, args.after)
    ensure_parent(args.json_out).write_text(json.dumps(diff, indent=2, sort_keys=True) + "\n")
    write_diff_markdown(diff, args.md_out)
    print("wrote %s" % args.json_out)
    print("wrote %s" % args.md_out)


if __name__ == "__main__":
    main()
