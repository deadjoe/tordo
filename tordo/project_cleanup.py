import re
from copy import deepcopy

DEFAULT_EMPTY_TRACK_NAME = re.compile(r"^\d+-(MIDI|Audio)$")
CREATE_REGULAR_TRACK_OPERATIONS = {"create_midi_track", "create_audio_track"}


def append_empty_project_track_cleanup(plan, snapshot, max_operations=64):
    operations = plan.get("operations") or []
    report = {
        "enabled": True,
        "applied": False,
        "reason": None,
        "tracks": [],
    }
    if not creates_regular_tracks(operations):
        report["reason"] = "plan_does_not_create_regular_tracks"
        return plan, report
    if not appends_regular_tracks(operations):
        report["reason"] = "plan_creates_regular_tracks_at_explicit_indices"
        return plan, report

    tracks = snapshot.get("tracks") or []
    if not tracks:
        report["reason"] = "no_regular_tracks"
        return plan, report

    candidates = []
    for index, track in enumerate(tracks):
        if not is_default_empty_track(track):
            report["reason"] = "project_has_non_default_or_non_empty_tracks"
            return plan, report
        candidates.append({"track_index": index, "track_name": track.get("name")})

    if len(operations) + len(candidates) > max_operations:
        raise ValueError(
            "empty-project cleanup would exceed max plan operations: %s + %s > %s"
            % (len(operations), len(candidates), max_operations)
        )

    prepared = deepcopy(plan)
    prepared_operations = prepared.setdefault("operations", [])
    for item in sorted(candidates, key=lambda value: value["track_index"], reverse=True):
        prepared_operations.append(
            {
                "type": "delete_track",
                "track_index": item["track_index"],
                "expected_track_name": item["track_name"],
                "allow_destructive": True,
            }
        )

    report["applied"] = True
    report["reason"] = "appended_delete_track_operations"
    report["tracks"] = candidates
    return prepared, report


def creates_regular_tracks(operations):
    return any(operation.get("type") in CREATE_REGULAR_TRACK_OPERATIONS for operation in operations)


def appends_regular_tracks(operations):
    for operation in operations:
        if operation.get("type") not in CREATE_REGULAR_TRACK_OPERATIONS:
            continue
        if int(operation.get("index", -1)) != -1:
            return False
    return True


def is_default_empty_track(track):
    name = track.get("name") or ""
    if DEFAULT_EMPTY_TRACK_NAME.match(name) is None:
        return False
    if track.get("devices"):
        return False
    return not has_clips(track)


def has_clips(track):
    return any(slot.get("clip") for slot in track.get("clip_slots") or [])
