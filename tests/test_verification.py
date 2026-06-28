import unittest

from tordo.verification import infer_track_target_from_plan, snapshot_track


class VerificationTargetTests(unittest.TestCase):
    def test_infer_track_target_keeps_return_track_type(self):
        plan = {
            "plan_version": 1,
            "operations": [
                {
                    "type": "set_track_mixer",
                    "track_type": "return",
                    "track_index": 0,
                    "track_name": "A-Reverb",
                    "volume": 0.65,
                }
            ],
        }

        target = infer_track_target_from_plan(plan)

        self.assertEqual(target["track_type"], "return")
        self.assertEqual(target["track_index"], 0)
        self.assertEqual(target["track_name"], "A-Reverb")

    def test_snapshot_track_reads_return_and_master_tracks(self):
        snapshot = {
            "tracks": [{"index": 0, "name": "Lead"}],
            "return_tracks": [{"index": 0, "name": "A-Reverb"}],
            "master_track": {"index": 0, "name": "Main"},
        }

        return_track = snapshot_track(snapshot, {"track_type": "return", "track_index": 0})
        master_track = snapshot_track(snapshot, {"track_type": "master"})

        self.assertEqual(return_track["name"], "A-Reverb")
        self.assertEqual(master_track["name"], "Main")


if __name__ == "__main__":
    unittest.main()
