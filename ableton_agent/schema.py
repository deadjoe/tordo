PLAN_SCHEMA_VERSION = 1


def agent_plan_schema():
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_version": 1,
        "selector_policy": {
            "track": "Use track_name or track_selector.name for existing regular/return tracks.",
            "scene": "Use scene_name or scene_selector.name when scene names are unique.",
            "clip": (
                "Use clip_name or clip_selector.name with a track selector; "
                "duplicate clip names on one track are refused."
            ),
            "indices": (
                "Indices are execution details. If a name selector is present, "
                "preflight resolves the current index from a fresh snapshot."
            ),
            "guards": ["expected_track_name", "expected_scene_name", "expected_clip_name"],
        },
        "operation_targets": {
            "set_track_state": ["track"],
            "set_track_mixer": ["track"],
            "set_device_parameter": ["track", "device", "parameter"],
            "insert_device": ["track"],
            "load_browser_item": ["track", "browser_item"],
            "duplicate_track": ["track"],
            "delete_track": ["track"],
            "create_midi_clip": ["track", "scene"],
            "add_notes": ["track", "scene", "clip"],
            "modify_notes": ["track", "scene", "clip"],
            "remove_notes": ["track", "scene", "clip"],
            "quantize_clip": ["track", "scene", "clip"],
            "duplicate_clip_loop": ["track", "scene", "clip"],
            "crop_clip": ["track", "scene", "clip"],
            "fire_clip_slot": ["track", "scene"],
            "stop_clip_slot": ["track", "scene"],
            "fire_scene": ["scene"],
            "duplicate_scene": ["scene"],
            "delete_scene": ["scene"],
            "set_tempo": [],
            "set_transport": [],
            "create_midi_track": [],
            "create_audio_track": [],
            "create_return_track": [],
            "create_scene": [],
        },
        "destructive_operations": {
            "delete_track": {"requires": {"allow_destructive": True}},
            "delete_scene": {"requires": {"allow_destructive": True}},
        },
        "target_selector_fields": {
            "track": ["track_name", "track_selector.name", "track_index"],
            "scene": ["scene_name", "scene_selector.name", "scene_index"],
            "clip": ["clip_name", "clip_selector.name"],
            "return_track": ["track_type=return", "track_name", "track_index"],
            "master_track": ["track_type=master", "track_name"],
            "browser_item": ["browser_uri", "browser_name", "browser_query", "browser_roots"],
        },
    }
