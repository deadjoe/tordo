def requested_selector_value(payload, field, selector_field, selector_key):
    top_level_value = payload.get(field)
    selector = payload.get(selector_field)
    selector_value = None
    if isinstance(selector, dict):
        selector_value = selector.get(selector_key)
    if top_level_value is not None and selector_value is not None and top_level_value != selector_value:
        raise ValueError(
            "conflicting %s %r and %s.%s %r"
            % (field, top_level_value, selector_field, selector_key, selector_value)
        )
    if top_level_value is not None:
        return top_level_value
    return selector_value


def requested_name(payload, name_field, selector_field):
    return requested_selector_value(payload, name_field, selector_field, "name")


def requested_expected_name(payload, expected_name_field, selector_field):
    return requested_selector_value(payload, expected_name_field, selector_field, "expected_name")


def requested_index(payload, index_field, selector_field):
    top_level_value = payload.get(index_field)
    selector = payload.get(selector_field)
    selector_value = None
    if isinstance(selector, dict):
        selector_value = selector.get("index")
    if top_level_value is not None and selector_value is not None:
        top_level_index = required_index(top_level_value, index_field)
        selector_index = required_index(selector_value, "%s.index" % selector_field)
        if top_level_index != selector_index:
            raise ValueError(
                "conflicting %s %r and %s.index %r"
                % (index_field, top_level_value, selector_field, selector_value)
            )
        return top_level_index
    raw_value = top_level_value if top_level_value is not None else selector_value
    if raw_value is None:
        return None
    return required_index(raw_value, index_field)


def normalize_track_type(track_type):
    if track_type in (None, "", "track"):
        return "track"
    if track_type in ("return", "return_track"):
        return "return"
    if track_type == "master":
        return "master"
    raise ValueError("unsupported track_type %r" % track_type)


def snapshot_tracks(snapshot, track_type):
    if track_type == "track":
        return snapshot.get("tracks") or []
    if track_type == "return":
        return snapshot.get("return_tracks") or []
    raise ValueError("unsupported indexed track_type %r" % track_type)


def resolve_snapshot_track(snapshot, track_type="track", name=None, index=None, label="target"):
    track_type = normalize_track_type(track_type)
    if track_type == "master":
        track = snapshot.get("master_track")
        if name is not None:
            validate_item_name(track, name, "%s master track" % label)
        return track

    tracks = snapshot_tracks(snapshot, track_type)
    if name is not None:
        return resolve_unique_name(tracks, name, "%s %s track" % (label, track_type))
    if index is None:
        raise ValueError("%s requires track_name or track_index" % label)
    index = required_index(index, "%s track_index" % label)
    if index >= len(tracks):
        raise ValueError("%s references missing %s track index %s" % (label, track_type, index))
    return tracks[index]


def resolve_snapshot_scene(snapshot, name=None, index=None, label="target"):
    scenes = snapshot.get("scenes") or []
    if name is not None:
        return resolve_unique_name(scenes, name, "%s scene" % label)
    if index is None:
        raise ValueError("%s requires scene_name or scene_index" % label)
    index = required_index(index, "%s scene_index" % label)
    if index >= len(scenes):
        raise ValueError("%s references missing scene index %s" % (label, index))
    return scenes[index]


def resolve_snapshot_clip_slot(
    snapshot,
    track,
    scene_name=None,
    scene_index=None,
    clip_name=None,
    label="target",
):
    if scene_name is not None or scene_index is not None:
        scene = resolve_snapshot_scene(snapshot, name=scene_name, index=scene_index, label=label)
        slot = clip_slot_at(track, scene.get("index"), label)
        if clip_name is not None:
            clip = slot.get("clip")
            validate_item_name(clip, clip_name, "%s clip" % label)
        return scene, slot

    if clip_name is None:
        raise ValueError("%s requires scene_name, scene_index, or clip_name" % label)

    matches = []
    scenes = snapshot.get("scenes") or []
    for slot in track.get("clip_slots") or []:
        clip = slot.get("clip")
        if clip and clip.get("name") == clip_name:
            scene = scene_at(scenes, slot.get("index"), label)
            matches.append((scene, slot))
    if not matches:
        raise ValueError("%s found no clip named %r on track %r" % (label, clip_name, track.get("name")))
    if len(matches) > 1:
        indexes = [slot.get("index") for _scene, slot in matches]
        raise ValueError(
            "%s clip name %r is not unique on track %r, matched scene indexes %s"
            % (label, clip_name, track.get("name"), indexes)
        )
    return matches[0]


def clip_slot_at(track, scene_index, label):
    slots = track.get("clip_slots") or []
    if scene_index is None:
        raise ValueError("%s scene index is missing" % label)
    if scene_index >= len(slots):
        raise ValueError("%s track %r has no clip slot at scene index %s" % (label, track.get("name"), scene_index))
    return slots[scene_index]


def scene_at(scenes, scene_index, label):
    if scene_index is None:
        raise ValueError("%s scene index is missing" % label)
    if scene_index >= len(scenes):
        raise ValueError("%s references missing scene index %s" % (label, scene_index))
    return scenes[scene_index]


def resolve_unique_name(items, name, label):
    matches = [item for item in items if item and item.get("name") == name]
    if not matches:
        raise ValueError("%s named %r was not found" % (label, name))
    if len(matches) > 1:
        indexes = [item.get("index") for item in matches]
        raise ValueError("%s name %r is not unique, matched indexes %s" % (label, name, indexes))
    return matches[0]


def validate_item_name(item, expected_name, label):
    actual_name = None if item is None else item.get("name")
    if actual_name != expected_name:
        raise ValueError("%s expected name %r, got %r" % (label, expected_name, actual_name))


def required_index(raw_value, label):
    try:
        parsed = int(raw_value)
    except Exception as exc:
        raise ValueError("%s must be an integer" % label) from exc
    if parsed < 0:
        raise ValueError("%s must be >= 0" % label)
    return parsed
