"""Answer-key (free) mode with tiny hand-made mornings; the full record is not generated.

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
    return [seg("07:00:00", "07:10:00", "eat_cereal"),
            seg("07:10:00", "07:10:04", "finish_drinking", role="candidate"),
            seg("07:10:04", "07:13:00", "eat_cereal"),
            seg("07:13:00", "07:13:06", "put_cup_in_dishwasher", role="action"),
            seg("07:13:06", "07:55:00", "eat_cereal"),
            seg("07:55:00", "08:00:00", "unseen", state="away", role="unseen")]


def tiny_key():
    return {"seed": 1, "line_seconds": 2, "tasks": list(TASKS), "states": dict(STATES),
            "events": {name: {"ko": e["ko"], "task": e["task"], "phrases": list(e["phrases"])}
                       for name, e in EVENTS.items()},
            "rules": [{"id": "R2", "state": "breakfast", "task": 1,
                       "candidates": [{"event": "finish_drinking", "expected_nights": [2]}], "forbidden": []}],
            "cases": [], "days": [{"day": day, "segments": tiny_day()} for day in (1, 2)]}


class FreeStepTests(unittest.TestCase):
    def test_true_marks_use_the_first_line_keep_the_state_and_end_unseen_at_its_last_line(self):
        segments = [seg("07:35:00", "07:36:00", "look_at_phone"),
                    seg("07:40:00", "07:41:00", "look_at_phone", state="rest"),
                    seg("07:53:00", "07:53:06", "put_cup_in_dishwasher", role="action"),
                    seg("07:57:16", "08:00:00", "unseen", state="away", role="unseen")]
        marks = fs.true_marks(segments, [{"state": "breakfast", "candidate": "look_at_phone"}],
                              [TASKS[1]], tiny_key(), step=2)
        self.assertEqual(marks, {
            "candidates": [{"state": "breakfast", "candidate": "look_at_phone", "times": ["07:35:00"]}],
            "actions": [{"action": TASKS[1], "times": ["07:53:00"]}],
            "unseen": [{"start": "07:57:16", "end": "07:59:58"}],
        })

    def test_true_memory_puts_every_rule_in_its_state(self):
        memory = fs.true_memory(tiny_key())
        self.assertEqual([state["id"] for state in memory["states"]], list(STATES))
        breakfast = next(state for state in memory["states"] if state["id"] == "breakfast")
        self.assertEqual(breakfast["rules"], [{"triggers": ["finish_drinking"], "action": TASKS[1]}])

    def test_tiny_two_morning_run_matches_the_expected_nights(self):
        key = tiny_key()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            records = {}
            for day in (1, 2):
                segments = [{**s, "start": mr.sec(s["start"]), "end": mr.sec(s["end"]),
                             "place": "table", "things": (), "curtains": True, "tv": False} for s in tiny_day()]
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
