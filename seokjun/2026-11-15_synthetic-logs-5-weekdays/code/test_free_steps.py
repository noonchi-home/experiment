"""Answer-key (free) mode with tiny hand-made days; the full record is not generated.

Run from this folder:
    python -m unittest -v test_free_steps
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import free_steps as fs  # noqa: E402
import make_records as mr  # noqa: E402
from vocabulary import EVENTS, STATES, TASKS  # noqa: E402
from pam.daily_run import run_night  # noqa: E402  (free_steps puts ai/ on the path)


def seg(start, end, event, state="breakfast", role="background", case=None):
    return {"start": start, "end": end, "event": event, "state": state, "role": role, "case": case}


def tiny_day():
    return [seg("07:00:00", "07:10:00", "eat_breakfast"),
            seg("07:10:00", "07:10:04", "finish_drinking", role="candidate"),
            seg("07:10:04", "07:13:00", "eat_breakfast"),
            seg("07:13:00", "07:13:06", "put_cup_in_dishwasher", role="action"),
            seg("07:13:06", "08:00:00", "eat_breakfast")]


def tiny_key():
    return {"seed": 1, "line_seconds": 2, "tasks": list(TASKS), "states": dict(STATES),
            "events": {name: {"ko": e["ko"], "task": e["task"], "phrases": list(e["phrases"])}
                       for name, e in EVENTS.items()},
            "rules": [{"id": "R1", "state": "breakfast", "task": 1,
                       "candidates": [{"event": "finish_drinking", "expected_nights": [2]}], "forbidden": []}],
            "cases": [], "days": [{"day": day, "segments": tiny_day()} for day in (1, 2)]}


class FreeStepTests(unittest.TestCase):
    def test_segments_become_moments_by_length(self):
        moments = fs.moments_from_segments([seg("07:00:00", "07:00:04", "finish_drinking"),
                                            seg("07:00:04", "07:01:04", "look_at_phone")], step=2)
        self.assertEqual(moments, [
            {"time": "07:00:00", "kind": "moment", "text": "finish_drinking"},
            {"time": "07:00:04", "kind": "start", "text": "look_at_phone"},
            {"time": "07:01:02", "kind": "end", "text": "look_at_phone"},
        ])

    def test_true_marks_keep_the_state_and_use_the_end_of_long_events(self):
        segments = [seg("07:35:00", "07:36:00", "look_at_phone"),
                    seg("09:00:00", "09:01:00", "look_at_phone", state="study"),
                    seg("07:53:00", "07:53:06", "put_cup_in_dishwasher", role="action"),
                    seg("12:30:04", "17:00:00", "unseen", state="away")]
        marks = fs.true_marks(segments, [{"state": "breakfast", "candidate": "look_at_phone"}],
                              [TASKS[1]], tiny_key(), step=2)
        self.assertEqual(marks, {
            "candidates": [{"state": "breakfast", "candidate": "look_at_phone", "times": ["07:35:58"]}],
            "actions": [{"action": TASKS[1], "times": ["07:53:00"]}],
            "unseen": [{"start": "12:30:04", "end": "16:59:58"}],
        })

    def test_tiny_two_day_run_matches_the_expected_nights(self):
        key = tiny_key()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            records = {}
            for day in (1, 2):
                segments = [{**s, "start": mr.sec(s["start"]), "end": mr.sec(s["end"])} for s in tiny_day()]
                records[day] = folder / f"day{day}.txt"
                records[day].write_text("\n".join(mr.render_lines(segments, f"tiny-{day}")) + "\n", encoding="utf-8")
            steps = fs.answer_key_steps(key)
            scores = []
            for night in (1, 2):
                run_night(night, records, folder / "run", steps)
                results = json.loads((folder / "run" / f"night-{night}" / "check_results.json").read_text("utf-8"))
                scores.append(fs.score_night(results, key, night))
        self.assertEqual([[(row["passed"], row["expected"], row["match"]) for row in rows] for rows in scores],
                         [[(False, False, True)], [(True, True, True)]])


if __name__ == "__main__":
    unittest.main()
