import unittest

from tools.validate_real_set_contract import duplicate_clip_with_unique_scene_context


class RealSetContractHarnessTests(unittest.TestCase):
    def test_duplicate_clip_with_unique_scene_context_prefers_unique_scene_name(self):
        snapshot = {
            "scenes": [
                {"index": 0, "name": "Hook"},
                {"index": 1, "name": "Verse"},
                {"index": 2, "name": "Hook"},
            ]
        }
        profile = {
            "duplicates": {
                "same_track_clips": [
                    {
                        "track_index": 4,
                        "track_name": "Bass",
                        "clip_name": "Loop",
                        "matches": [
                            {"scene_index": 0, "scene_name": "Hook"},
                            {"scene_index": 1, "scene_name": "Verse"},
                        ],
                    }
                ]
            }
        }

        self.assertEqual(
            duplicate_clip_with_unique_scene_context(snapshot, profile),
            {
                "track_index": 4,
                "track_name": "Bass",
                "clip_name": "Loop",
                "scene_name": "Verse",
            },
        )

    def test_duplicate_clip_with_unique_scene_context_returns_none_when_scene_names_are_duplicate(self):
        snapshot = {
            "scenes": [
                {"index": 0, "name": "Hook"},
                {"index": 1, "name": "Hook"},
            ]
        }
        profile = {
            "duplicates": {
                "same_track_clips": [
                    {
                        "track_index": 4,
                        "track_name": "Bass",
                        "clip_name": "Loop",
                        "matches": [
                            {"scene_index": 0, "scene_name": "Hook"},
                            {"scene_index": 1, "scene_name": "Hook"},
                        ],
                    }
                ]
            }
        }

        self.assertIsNone(duplicate_clip_with_unique_scene_context(snapshot, profile))


if __name__ == "__main__":
    unittest.main()
