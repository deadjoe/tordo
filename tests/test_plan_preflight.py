import unittest

from tordo.plan_preflight import prepare_plan_for_apply

SNAPSHOT = {
    "tracks": [
        {
            "index": 0,
            "name": "Bass",
            "clip_slots": [
                {"index": 0, "clip": {"name": "Loop"}},
                {"index": 1, "clip": {"name": "Loop"}},
            ],
        },
        {"index": 1, "name": "Bass", "clip_slots": [{"index": 0, "clip": None}, {"index": 1, "clip": None}]},
        {"index": 2, "name": "Lead", "clip_slots": [{"index": 0, "clip": {"name": "Hook"}}]},
    ],
    "return_tracks": [{"index": 0, "name": "A-Reverb", "clip_slots": []}],
    "master_track": {"index": 0, "name": "Main"},
    "scenes": [
        {"index": 0, "name": "Verse"},
        {"index": 1, "name": "Verse"},
    ],
}


class PlanPreflightSelectorTests(unittest.TestCase):
    def test_track_selector_index_expected_name_normalizes_to_bridge_fields(self):
        plan = {
            "plan_version": 1,
            "operations": [
                {
                    "type": "set_track_mixer",
                    "track_selector": {"index": "0", "expected_name": "Bass"},
                    "volume": 0.8,
                }
            ],
        }

        prepared, report = prepare_plan_for_apply(plan, SNAPSHOT)

        operation = prepared["operations"][0]
        self.assertEqual(operation["track_index"], 0)
        self.assertEqual(operation["expected_track_name"], "Bass")
        self.assertEqual(report["validated_tracks"][0]["track_name"], "Bass")

    def test_scene_selector_index_expected_name_normalizes_to_bridge_fields(self):
        plan = {
            "plan_version": 1,
            "operations": [
                {
                    "type": "fire_scene",
                    "scene_selector": {"index": 1, "expected_name": "Verse"},
                }
            ],
        }

        prepared, report = prepare_plan_for_apply(plan, SNAPSHOT)

        operation = prepared["operations"][0]
        self.assertEqual(operation["scene_index"], 1)
        self.assertEqual(operation["expected_scene_name"], "Verse")
        self.assertEqual(report["resolved_scenes"][0]["scene_index"], 1)

    def test_clip_selector_uses_scene_selector_context(self):
        plan = {
            "plan_version": 1,
            "operations": [
                {
                    "type": "quantize_clip",
                    "track_selector": {"index": 0, "expected_name": "Bass"},
                    "scene_selector": {"index": 1, "expected_name": "Verse"},
                    "clip_selector": {"name": "Loop"},
                    "quantization_grid": 5,
                }
            ],
        }

        prepared, report = prepare_plan_for_apply(plan, SNAPSHOT)

        operation = prepared["operations"][0]
        self.assertEqual(operation["track_index"], 0)
        self.assertEqual(operation["scene_index"], 1)
        self.assertEqual(operation["expected_track_name"], "Bass")
        self.assertEqual(operation["expected_scene_name"], "Verse")
        self.assertEqual(operation["expected_clip_name"], "Loop")
        self.assertEqual(report["resolved_clips"][0]["scene_index"], 1)

    def test_unique_name_selector_still_resolves(self):
        plan = {
            "plan_version": 1,
            "operations": [
                {
                    "type": "set_track_state",
                    "track_selector": {"name": "Lead"},
                    "mute": True,
                }
            ],
        }

        prepared, report = prepare_plan_for_apply(plan, SNAPSHOT)

        operation = prepared["operations"][0]
        self.assertEqual(operation["track_index"], 2)
        self.assertEqual(operation["expected_track_name"], "Lead")
        self.assertEqual(report["resolved_tracks"][0]["track_name"], "Lead")

    def test_conflicting_top_level_and_selector_index_refuses(self):
        plan = {
            "plan_version": 1,
            "operations": [
                {
                    "type": "set_track_mixer",
                    "track_index": 0,
                    "track_selector": {"index": 1, "expected_name": "Bass"},
                    "volume": 0.8,
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "conflicting track_index"):
            prepare_plan_for_apply(plan, SNAPSHOT)

    def test_conflicting_top_level_and_selector_name_refuses(self):
        plan = {
            "plan_version": 1,
            "operations": [
                {
                    "type": "fire_scene",
                    "scene_name": "Verse",
                    "scene_selector": {"name": "Chorus"},
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "conflicting scene_name"):
            prepare_plan_for_apply(plan, SNAPSHOT)

    def test_conflicting_clip_name_and_expected_name_refuses(self):
        plan = {
            "plan_version": 1,
            "operations": [
                {
                    "type": "quantize_clip",
                    "track_selector": {"index": 0, "expected_name": "Bass"},
                    "scene_selector": {"index": 1, "expected_name": "Verse"},
                    "clip_selector": {"name": "Loop", "expected_name": "Other"},
                    "quantization_grid": 5,
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "conflicting clip_name"):
            prepare_plan_for_apply(plan, SNAPSHOT)


if __name__ == "__main__":
    unittest.main()
