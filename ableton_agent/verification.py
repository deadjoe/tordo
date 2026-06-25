from ableton_agent.bridge_client import require_ok, send_request
from ableton_agent.plan_preflight import prepare_plan_for_apply
from ableton_agent.plans import load_plan
from ableton_agent.selectors import resolve_snapshot_clip_slot, resolve_snapshot_track

FLOAT_FIELDS = {
    "start_time",
    "duration",
    "velocity",
    "probability",
    "velocity_deviation",
    "release_velocity",
}
EXACT_FIELDS = {"pitch", "mute"}
DEFAULT_FIELDS = [
    "pitch",
    "start_time",
    "duration",
    "velocity",
    "mute",
    "probability",
    "velocity_deviation",
    "release_velocity",
]


def verify_note_metadata(
    plan_path,
    track_index=None,
    scene_index=None,
    track_name=None,
    scene_name=None,
    clip_name=None,
    host="127.0.0.1",
    port=8765,
    timeout=20.0,
):
    plan = load_plan(plan_path)
    expected_notes = expected_plan_notes(plan)
    target = resolve_clip_verification_target(
        plan,
        track_index=track_index,
        track_name=track_name,
        scene_index=scene_index,
        scene_name=scene_name,
        clip_name=clip_name,
        host=host,
        port=port,
        timeout=timeout,
    )
    response = send_request(
        "clip_notes",
        args={
            "track_index": target["track_index"],
            "scene_index": target["scene_index"],
            "limit": max(len(expected_notes), 1),
            "diagnostic": False,
        },
        host=host,
        port=port,
        timeout=timeout,
    )
    payload = require_ok(response, "clip_notes")
    actual_notes = payload.get("notes") or []
    comparison = compare_notes(expected_notes, actual_notes)
    return {
        "ok": comparison["ok"],
        "plan": plan.get("name"),
        **target,
        "clip": payload.get("clip"),
        "source": payload.get("source"),
        "expected_count": len(expected_notes),
        "actual_count": len(actual_notes),
        "mismatches": comparison["mismatches"],
    }


def verify_note_edit(
    plan_path,
    track_index=None,
    scene_index=None,
    track_name=None,
    scene_name=None,
    clip_name=None,
    host="127.0.0.1",
    port=8765,
    timeout=20.0,
):
    plan = load_plan(plan_path)
    expected_notes = plan.get("expected_notes")
    if not isinstance(expected_notes, list):
        raise ValueError("plan has no expected_notes list")
    target = resolve_clip_verification_target(
        plan,
        track_index=track_index,
        track_name=track_name,
        scene_index=scene_index,
        scene_name=scene_name,
        clip_name=clip_name,
        host=host,
        port=port,
        timeout=timeout,
    )
    response = send_request(
        "clip_notes",
        args={
            "track_index": target["track_index"],
            "scene_index": target["scene_index"],
            "limit": max(len(expected_notes) + 8, 16),
            "diagnostic": False,
        },
        host=host,
        port=port,
        timeout=timeout,
    )
    payload = require_ok(response, "clip_notes")
    actual_notes = payload.get("notes") or []
    comparison = compare_notes(expected_notes, actual_notes)
    return {
        "ok": comparison["ok"],
        "plan": plan.get("name"),
        **target,
        "clip": payload.get("clip"),
        "source": payload.get("source"),
        "expected_count": len(expected_notes),
        "actual_count": len(actual_notes),
        "mismatches": comparison["mismatches"],
    }


def verify_track_mixer(plan_path, track_index=None, track_name=None, host="127.0.0.1", port=8765, timeout=20.0):
    plan = load_plan(plan_path)
    response = send_request("snapshot", host=host, port=port, timeout=timeout)
    payload = require_ok(response, "snapshot")
    inferred = infer_track_target_from_plan(plan)
    if track_name is None:
        track_name = inferred.get("track_name")
    if track_index is None:
        track_index = inferred.get("track_index")
    track = resolve_snapshot_track(payload, name=track_name, index=track_index, label="verification")
    track_index = track.get("index")
    mismatches = []
    expected_state = expected_track_state(plan)
    expected_mixer = expected_track_mixer(plan)

    for field, expected_value in expected_state.items():
        actual_value = track.get(field)
        if not values_match(field, expected_value, actual_value):
            mismatches.append(
                {
                    "type": "track_state",
                    "field": field,
                    "expected": expected_value,
                    "actual": actual_value,
                }
            )

    mixer = track.get("mixer") or {}
    for field, expected_value in expected_mixer.items():
        actual_value = actual_mixer_value(mixer, field)
        if not values_match(field, expected_value, actual_value):
            mismatches.append(
                {
                    "type": "mixer",
                    "field": field,
                    "expected": expected_value,
                    "actual": actual_value,
                }
            )

    return {
        "ok": not mismatches,
        "plan": plan.get("name"),
        "track_index": track_index,
        "track": {
            "name": track.get("name"),
            "arm": track.get("arm"),
            "mute": track.get("mute"),
            "solo": track.get("solo"),
            "mixer": mixer,
        },
        "expected_state": expected_state,
        "expected_mixer": expected_mixer,
        "mismatches": mismatches,
    }


def verify_device_parameters(plan_path, host="127.0.0.1", port=8765, timeout=20.0):
    plan = load_plan(plan_path)
    response = send_request("snapshot", host=host, port=port, timeout=timeout)
    payload = require_ok(response, "snapshot")
    prepared_plan, _report = prepare_plan_for_apply(plan, payload)
    expected = expected_device_parameters(prepared_plan)
    mismatches = []
    actual = []

    for item in expected:
        parameter = snapshot_device_parameter(payload, item)
        if parameter is None:
            mismatches.append(
                {
                    "type": "device_parameter",
                    "expected": item,
                    "actual": None,
                }
            )
            continue
        actual_item = {
            **item,
            "actual_name": parameter.get("name"),
            "actual_value": parameter.get("value"),
        }
        actual.append(actual_item)
        if item.get("parameter_name") and item.get("parameter_name") != parameter.get("name"):
            mismatches.append(
                {
                    "type": "device_parameter_name",
                    "expected": item.get("parameter_name"),
                    "actual": parameter.get("name"),
                    "target": device_parameter_label(item),
                }
            )
        if not values_match("device_parameter", item.get("value"), parameter.get("value")):
            mismatches.append(
                {
                    "type": "device_parameter_value",
                    "expected": item.get("value"),
                    "actual": parameter.get("value"),
                    "target": device_parameter_label(item),
                }
            )

    return {
        "ok": not mismatches,
        "plan": plan.get("name"),
        "expected": expected,
        "actual": actual,
        "mismatches": mismatches,
    }


def expected_device_parameters(plan):
    expected = []
    for operation in plan.get("operations") or []:
        if operation.get("type") != "set_device_parameter":
            continue
        expected.append(
            {
                "track_type": operation.get("track_type", "track"),
                "track_index": int(operation.get("track_index", 0)),
                "device_index": int(operation.get("device_index")),
                "device_name": operation.get("device_name"),
                "parameter_index": int(operation.get("parameter_index")),
                "parameter_name": operation.get("parameter_name"),
                "value": operation.get("value"),
            }
        )
    return expected


def resolve_clip_verification_target(
    plan,
    track_index=None,
    track_name=None,
    scene_index=None,
    scene_name=None,
    clip_name=None,
    host="127.0.0.1",
    port=8765,
    timeout=20.0,
):
    response = send_request("snapshot", host=host, port=port, timeout=timeout)
    snapshot = require_ok(response, "snapshot")
    inferred = infer_clip_target_from_plan(plan)
    if track_name is None:
        track_name = inferred.get("track_name")
    if track_index is None:
        track_index = inferred.get("track_index")
    if scene_name is None:
        scene_name = inferred.get("scene_name")
    if scene_index is None:
        scene_index = inferred.get("scene_index")
    if clip_name is None:
        clip_name = inferred.get("clip_name")

    track = resolve_snapshot_track(snapshot, name=track_name, index=track_index, label="verification")
    scene, slot = resolve_snapshot_clip_slot(
        snapshot,
        track,
        scene_name=scene_name,
        scene_index=scene_index,
        clip_name=clip_name,
        label="verification",
    )
    clip = slot.get("clip") or {}
    return {
        "track_index": track.get("index"),
        "track_name": track.get("name"),
        "scene_index": scene.get("index"),
        "scene_name": scene.get("name"),
        "clip_name": clip.get("name"),
    }


def infer_clip_target_from_plan(plan):
    tracks_by_ref = {}
    scenes_by_ref = {}
    for operation in plan.get("operations") or []:
        if operation.get("type") in ("create_midi_track", "create_audio_track") and operation.get("id"):
            tracks_by_ref[operation.get("id")] = {
                "track_index": operation.get("track_index"),
                "track_name": operation.get("name") or operation.get("track_name"),
            }
        if operation.get("type") == "create_scene" and operation.get("id"):
            scenes_by_ref[operation.get("id")] = {
                "scene_index": operation.get("scene_index"),
                "scene_name": operation.get("name") or operation.get("scene_name"),
            }

    for operation in plan.get("operations") or []:
        if operation.get("type") != "create_midi_clip":
            continue
        target = {
            "track_index": operation.get("track_index"),
            "track_name": operation.get("track_name"),
            "scene_index": operation.get("scene_index"),
            "scene_name": operation.get("scene_name"),
            "clip_name": operation.get("name") or operation.get("clip_name"),
        }
        if target["track_name"] is None and operation.get("track_ref") in tracks_by_ref:
            target.update(
                {key: value for key, value in tracks_by_ref[operation.get("track_ref")].items() if value is not None}
            )
        if target["scene_name"] is None and operation.get("scene_ref") in scenes_by_ref:
            target.update(
                {key: value for key, value in scenes_by_ref[operation.get("scene_ref")].items() if value is not None}
            )
        return target
    return {}


def infer_track_target_from_plan(plan):
    tracks_by_ref = {}
    for operation in plan.get("operations") or []:
        if operation.get("type") in ("create_midi_track", "create_audio_track") and operation.get("id"):
            tracks_by_ref[operation.get("id")] = {
                "track_index": operation.get("track_index"),
                "track_name": operation.get("name") or operation.get("track_name"),
            }
    for operation in plan.get("operations") or []:
        if operation.get("type") not in ("set_track_state", "set_track_mixer"):
            continue
        target = {
            "track_index": operation.get("track_index"),
            "track_name": operation.get("track_name"),
        }
        if target["track_name"] is None and operation.get("track_ref") in tracks_by_ref:
            target.update(
                {key: value for key, value in tracks_by_ref[operation.get("track_ref")].items() if value is not None}
            )
        return target
    return {}


def snapshot_device_parameter(snapshot_payload, target):
    track = snapshot_track(snapshot_payload, target)
    if track is None:
        return None
    devices = track.get("devices") or []
    device_index = target["device_index"]
    if device_index >= len(devices):
        return None
    device = devices[device_index]
    if target.get("device_name") and target.get("device_name") != device.get("name"):
        return None
    parameters = device.get("parameters") or []
    parameter_index = target["parameter_index"]
    if parameter_index >= len(parameters):
        return None
    return parameters[parameter_index]


def snapshot_track(snapshot_payload, target):
    track_type = target.get("track_type", "track")
    if track_type == "track":
        tracks = snapshot_payload.get("tracks") or []
    elif track_type in ("return", "return_track"):
        tracks = snapshot_payload.get("return_tracks") or []
    elif track_type == "master":
        return snapshot_payload.get("master_track")
    else:
        return None

    track_index = target.get("track_index", 0)
    if track_index >= len(tracks):
        return None
    return tracks[track_index]


def device_parameter_label(item):
    return "%s:%s device:%s parameter:%s" % (
        item.get("track_type"),
        item.get("track_index"),
        item.get("device_index"),
        item.get("parameter_index"),
    )


def expected_track_state(plan):
    expected = {}
    for operation in plan.get("operations") or []:
        if operation.get("type") != "set_track_state":
            continue
        for field in ("name", "arm", "mute", "solo"):
            if field in operation:
                expected[field] = operation.get(field)
    return expected


def expected_track_mixer(plan):
    expected = {}
    for operation in plan.get("operations") or []:
        if operation.get("type") != "set_track_mixer":
            continue
        for field in ("volume", "panning"):
            if field in operation:
                expected[field] = operation.get(field)
        sends = operation.get("sends")
        if isinstance(sends, dict):
            for index, value in sends.items():
                expected["send:%s" % int(index)] = value
        elif isinstance(sends, list):
            for send in sends:
                expected["send:%s" % int(send.get("index"))] = send.get("value")
    return expected


def actual_mixer_value(mixer, field):
    if field in ("volume", "panning"):
        return ((mixer.get(field) or {}).get("value"))
    if field.startswith("send:"):
        index = int(field.split(":", 1)[1])
        sends = mixer.get("sends") or []
        if index >= len(sends):
            return None
        return sends[index].get("value")
    return None


def expected_plan_notes(plan):
    for operation in plan.get("operations") or []:
        if operation.get("type") == "add_notes":
            notes = operation.get("notes")
            if isinstance(notes, list):
                return sort_notes(notes)
    raise ValueError("plan has no add_notes operation with inline notes")


def compare_notes(expected_notes, actual_notes):
    expected = sort_notes(expected_notes)
    actual = sort_notes(actual_notes)
    mismatches = []

    if len(expected) != len(actual):
        mismatches.append(
            {
                "type": "count",
                "expected": len(expected),
                "actual": len(actual),
            }
        )

    for index, (expected_note, actual_note) in enumerate(zip(expected, actual)):
        for field in DEFAULT_FIELDS:
            if field not in expected_note:
                continue
            expected_value = expected_note.get(field)
            actual_value = actual_note.get(field)
            if not values_match(field, expected_value, actual_value):
                mismatches.append(
                    {
                        "type": "field",
                        "index": index,
                        "field": field,
                        "expected": expected_value,
                        "actual": actual_value,
                    }
                )

    return {"ok": not mismatches, "mismatches": mismatches}


def sort_notes(notes):
    return sorted(
        notes,
        key=lambda note: (
            numeric(note.get("start_time")),
            numeric(note.get("pitch")),
            numeric(note.get("duration")),
            numeric(note.get("velocity")),
        ),
    )


def values_match(field, expected, actual):
    if field in FLOAT_FIELDS:
        return abs(float(expected) - float(actual)) < 0.0001
    if field in {"volume", "panning", "device_parameter"} or field.startswith("send:"):
        return abs(float(expected) - float(actual)) < 0.0001
    if field in EXACT_FIELDS:
        return expected == actual
    return expected == actual


def numeric(value):
    try:
        return float(value)
    except Exception:
        return 0.0
