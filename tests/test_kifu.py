import unittest

from koushougi.kifu import replay_record
from koushougi.position import position


class KifuTest(unittest.TestCase):
    def record(self):
        return {"format": "koushougi-kifu", "version": 1, "history": [
            {"from": "A14", "path": ["A13"], "shots": [], "promote": False},
            {"from": "A6", "path": ["A7"], "shots": [], "promote": False},
        ]}

    def test_all_frames_match_current_engine_and_round_trip(self):
        record = self.record()
        replay = replay_record(record)
        for index, frame in enumerate(replay["frames"]):
            actual = position(record["history"][:index])
            for key in ("pieces", "turn", "winner"):
                self.assertEqual(frame[key], actual[key])
        self.assertEqual(replay_record(replay["record"]), replay)

    def test_bad_moves_and_metadata_are_rejected(self):
        for changes in (
            {"version": True}, {"version": 2}, {"history": [None]},
            {"opponent": []}, {"humanSide": "red"}, {"resignedSide": []},
            {"history": [{"from": "A14", "path": ["A0"], "promote": False}]},
            {"history": [{"from": "A14", "path": ["A13"], "promote": 1}]},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replay_record({**self.record(), **changes})

    def test_invalid_later_move_reports_its_number(self):
        record = self.record()
        record["history"][1]["path"] = ["A19"]
        with self.assertRaisesRegex(ValueError, "2手目"):
            replay_record(record)

    def test_import_does_not_request_ai_moves(self):
        from unittest.mock import patch
        with patch("koushougi.position.choose_search_move", side_effect=AssertionError):
            replay_record({**self.record(), "opponent": "search"})

    def test_resignation_and_unfinished_result_preserved(self):
        for info in ({"resignedSide": "black"}, {"endReason": "ply_limit"}):
            result = replay_record({**self.record(), **info})["record"]
            for key, value in info.items():
                self.assertEqual(result[key], value)


if __name__ == "__main__":
    unittest.main()
