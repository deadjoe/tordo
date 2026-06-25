from copy import deepcopy

from tordo.selectors import (
    normalize_track_type,
    requested_name,
    resolve_snapshot_clip_slot,
    resolve_snapshot_scene,
    resolve_snapshot_track,
    snapshot_tracks,
    validate_item_name,
)

TRACK_TARGET_OPERATIONS = {
    "add_notes",
    "create_midi_clip",
    "crop_clip",
    "delete_track",
    "duplicate_clip_loop",
    "duplicate_track",
    "fire_clip_slot",
    "insert_device",
    "load_browser_item",
    "modify_notes",
    "quantize_clip",
    "remove_notes",
    "set_device_parameter",
    "set_track_mixer",
    "set_track_state",
    "stop_clip_slot",
}

SCENE_TARGET_OPERATIONS = {
    "add_notes",
    "create_midi_clip",
    "crop_clip",
    "delete_scene",
    "duplicate_clip_loop",
    "duplicate_scene",
    "fire_clip_slot",
    "fire_scene",
    "modify_notes",
    "quantize_clip",
    "remove_notes",
    "stop_clip_slot",
}

CLIP_TARGET_OPERATIONS = {
    "add_notes",
    "crop_clip",
    "duplicate_clip_loop",
    "modify_notes",
    "quantize_clip",
    "remove_notes",
}


def prepare_plan_for_apply(plan, snapshot):
    prepared = deepcopy(plan)
    report = {"resolved_tracks": [], "validated_tracks": [], "resolved_scenes": [], "resolved_clips": []}
    operations = prepared.get("operations") or []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            continue
        prepare_existing_track_target(operation, snapshot, index, report)
        prepare_scene_target(operation, snapshot, index, report)
        prepare_clip_target(operation, snapshot, index, report)
    return prepared, report


def prepare_existing_track_target(operation, snapshot, operation_index, report):
    operation_type = operation.get("type")
    if operation_type not in TRACK_TARGET_OPERATIONS:
        return
    if "track_ref" in operation or "clip_ref" in operation:
        return

    track_type = normalize_track_type(operation.get("track_type", "track"))
    track_name = requested_name(operation, "track_name", "track_selector")
    expected_name = operation.get("expected_track_name")

    if track_name is not None and expected_name is not None and track_name != expected_name:
        raise ValueError(
            "operation %s has conflicting track_name %r and expected_track_name %r"
            % (operation_index, track_name, expected_name)
        )

    if track_name is not None:
        target = resolve_snapshot_track(
            snapshot,
            track_type=track_type,
            name=track_name,
            label="operation %s" % operation_index,
        )
        operation["track_index"] = target.get("index", 0)
        operation["expected_track_name"] = target.get("name")
        report["resolved_tracks"].append(track_report(operation_index, track_type, target))
        return

    if expected_name is not None:
        target = resolve_snapshot_track(
            snapshot,
            track_type=track_type,
            index=operation.get("track_index"),
            label="operation %s" % operation_index,
        )
        validate_item_name(target, expected_name, "operation %s %s track" % (operation_index, track_type))
        report["validated_tracks"].append(track_report(operation_index, track_type, target))


def prepare_scene_target(operation, snapshot, operation_index, report):
    operation_type = operation.get("type")
    if operation_type not in SCENE_TARGET_OPERATIONS:
        return
    if "scene_ref" in operation:
        return

    scene_name = requested_name(operation, "scene_name", "scene_selector")
    expected_name = operation.get("expected_scene_name")

    if scene_name is not None and expected_name is not None and scene_name != expected_name:
        raise ValueError(
            "operation %s has conflicting scene_name %r and expected_scene_name %r"
            % (operation_index, scene_name, expected_name)
        )

    if scene_name is not None:
        scene = resolve_snapshot_scene(snapshot, name=scene_name, label="operation %s" % operation_index)
        operation["scene_index"] = scene.get("index")
        operation["expected_scene_name"] = scene.get("name")
        report["resolved_scenes"].append(scene_report(operation_index, scene))
        return

    if expected_name is not None:
        scene = resolve_snapshot_scene(
            snapshot,
            index=operation.get("scene_index"),
            label="operation %s" % operation_index,
        )
        validate_item_name(scene, expected_name, "operation %s scene" % operation_index)
        report["resolved_scenes"].append(scene_report(operation_index, scene))


def prepare_clip_target(operation, snapshot, operation_index, report):
    operation_type = operation.get("type")
    if operation_type not in CLIP_TARGET_OPERATIONS:
        return
    if "clip_ref" in operation:
        return

    clip_name = requested_name(operation, "clip_name", "clip_selector")
    expected_clip_name = operation.get("expected_clip_name")
    if clip_name is not None and expected_clip_name is not None and clip_name != expected_clip_name:
        raise ValueError(
            "operation %s has conflicting clip_name %r and expected_clip_name %r"
            % (operation_index, clip_name, expected_clip_name)
        )
    if clip_name is None and expected_clip_name is None:
        return

    track = operation_track(snapshot, operation, operation_index)
    scene_name = requested_name(operation, "scene_name", "scene_selector")
    scene, slot = resolve_snapshot_clip_slot(
        snapshot,
        track,
        scene_name=scene_name,
        scene_index=operation.get("scene_index"),
        clip_name=clip_name or expected_clip_name,
        label="operation %s" % operation_index,
    )

    operation["scene_index"] = scene.get("index")
    operation["expected_scene_name"] = scene.get("name")
    operation["expected_clip_name"] = (slot.get("clip") or {}).get("name")
    report["resolved_clips"].append(
        {
            "operation_index": operation_index,
            "track_index": track.get("index"),
            "track_name": track.get("name"),
            "scene_index": scene.get("index"),
            "scene_name": scene.get("name"),
            "clip_name": operation["expected_clip_name"],
        }
    )


def operation_track(snapshot, operation, operation_index):
    track_type = normalize_track_type(operation.get("track_type", "track"))
    track_name = requested_name(operation, "track_name", "track_selector")
    if track_name is not None:
        return resolve_snapshot_track(
            snapshot,
            track_type=track_type,
            name=track_name,
            label="operation %s" % operation_index,
        )
    return resolve_snapshot_track(
        snapshot,
        track_type=track_type,
        index=operation.get("track_index"),
        label="operation %s" % operation_index,
    )


def track_report(operation_index, track_type, track):
    payload = {
        "operation_index": operation_index,
        "track_type": track_type,
        "track_name": track.get("name"),
    }
    if track_type != "master":
        payload["track_index"] = track.get("index")
    return payload


def scene_report(operation_index, scene):
    return {
        "operation_index": operation_index,
        "scene_index": scene.get("index"),
        "scene_name": scene.get("name"),
    }


def report_has_entries(report):
    return any(report.get(key) for key in report)


def has_track_name(snapshot, name, track_type="track"):
    return any(track.get("name") == name for track in snapshot_tracks(snapshot, normalize_track_type(track_type)))
