"""Day scoring: the right answer at each moment, asking, and scoring (no model calls).

Run from this folder: python -m unittest test_day_scoring
"""

from pathlib import Path
import tempfile
import unittest

import day_scoring as ds

NO = ds.NO_ACT
TASKS = [f"task {index}" for index in range(8)]
TASK_OF = {"put_cup_in_dishwasher": 1, "put_can_next_to_self": 2, "put_bowl_in_dishwasher": 6,
           "turn_off_room_light": 7}
EVENTS = ("eat_breakfast", "finish_drinking", "look_at_phone", "pick_up_empty_cup", "carry_cup_to_kitchen",
          "put_cup_in_dishwasher", "type_on_laptop", "phone_rings", "talk_on_phone", "watch_tv", "get_can",
          "put_can_next_to_self", "put_on_bag", "check_pockets", "walk_to_light_switch", "turn_off_room_light",
          "unseen", "finish_meal", "sit_idle_at_table", "wipe_mouth", "pick_up_bowl", "put_bowl_in_dishwasher")
RULES = [
    {"id": "R1", "state": "breakfast", "task": 1, "forbidden": ["pick_up_empty_cup", "carry_cup_to_kitchen"],
     "candidates": [{"event": "finish_drinking", "expected_nights": [2]},
                    {"event": "look_at_phone", "expected_nights": []}]},
    {"id": "R3", "state": "dinner", "task": 6, "forbidden": ["pick_up_bowl"],
     "candidates": [{"event": "finish_meal", "expected_nights": [2]},
                    {"event": "wipe_mouth", "expected_nights": [2]}]},
    {"id": "R4", "state": "evening_rest", "task": 2, "forbidden": ["get_can"],
     "candidates": [{"event": "phone_rings", "expected_nights": [2]}]},
    {"id": "R9", "state": "going_out", "task": 7, "forbidden": ["walk_to_light_switch"],
     "candidates": [{"event": "put_on_bag", "expected_nights": [2]}]},
]
CASES = [{"id": "daily_habit", "rule": "R1", "candidate": "finish_drinking", "true_habit": "예"},
         {"id": "two_candidates", "rule": "R3", "candidate": "finish_meal", "true_habit": "예 (둘 다 맞음)"},
         {"id": "early_coincidence", "rule": "R4", "candidate": "phone_rings", "true_habit": "아니요 (기준의 약점)"},
         {"id": "unseen", "rule": "R9", "candidate": "put_on_bag", "true_habit": "예"}]


def seg(start, end, event, state, role="background"):
    return {"start": start, "end": end, "event": event, "state": state, "role": role, "case": None}


def key_for(segments):
    return {"line_seconds": 2, "tasks": TASKS, "rules": RULES, "cases": CASES,
            "events": {name: {"ko": name, "task": TASK_OF.get(name), "phrases": [name]} for name in EVENTS},
            "days": [{"day": 1, "segments": segments}]}


def labels(segments):
    return [(row["time"], row["labels"]) for row in ds.day_labels(key_for(segments), 1)]


def record(segments):
    """One record line every 2 seconds, naming the event of that time."""
    return [f"{ds._hms(moment)} | The person: {s['event']}."
            for s in segments for moment in range(ds._sec(s["start"]), ds._sec(s["end"]), 2)]


def answer(time, task):
    """A saved answer; task None is a broken answer."""
    if task is None:
        return {"time": time, "status": "invalid", "output": None, "errors": ["broken"]}
    return {"time": time, "status": "valid", "output": {"observation": "x", "reasoning": "y", "task_index": task},
            "errors": []}


FSM = {"initial_state": "breakfast",
       "states": [{"id": "breakfast", "description": "Breakfast.", "rules": [], "next": []}]}


BREAKFAST = [seg("07:30:00", "07:40:00", "eat_breakfast", "breakfast"),
             seg("07:40:00", "07:40:04", "finish_drinking", "breakfast", "candidate"),
             seg("07:40:04", "07:42:00", "eat_breakfast", "breakfast"),
             seg("07:42:00", "07:42:04", "pick_up_empty_cup", "breakfast", "approach"),
             seg("07:42:04", "07:42:08", "carry_cup_to_kitchen", "breakfast", "approach"),
             seg("07:42:08", "07:42:14", "put_cup_in_dishwasher", "breakfast", "action"),
             seg("07:42:14", "08:00:00", "type_on_laptop", "study")]
DINNER = [seg("19:00:00", "19:00:04", "finish_meal", "dinner", "candidate"),
          seg("19:00:04", "19:00:40", "sit_idle_at_table", "dinner"),
          seg("19:00:40", "19:00:44", "wipe_mouth", "dinner", "candidate"),
          seg("19:00:44", "19:02:00", "sit_idle_at_table", "dinner"),
          seg("19:02:00", "19:02:04", "pick_up_bowl", "dinner", "approach"),
          seg("19:02:04", "19:02:10", "put_bowl_in_dishwasher", "dinner", "action")]


class DayLabelTests(unittest.TestCase):
    def test_help_runs_from_the_signal_until_the_person_starts_moving(self):
        self.assertEqual(labels(BREAKFAST), [
            ("07:30:00", [NO]), ("07:39:58", [NO]),
            ("07:40:00", [1]), ("07:40:04", [1]), ("07:41:58", [1]),
            ("07:42:00", [NO]), ("07:42:04", [NO]), ("07:42:08", [NO]), ("07:42:12", [NO]),
            ("07:42:14", [NO]), ("07:59:58", [NO])])

    def test_no_help_when_the_person_does_not_do_it_within_five_minutes(self):
        late = [*BREAKFAST[:2], seg("07:40:04", "07:46:00", "eat_breakfast", "breakfast"),
                *[{**s, "start": f"07:46:{s['start'][6:]}", "end": f"07:46:{s['end'][6:]}"} for s in BREAKFAST[3:6]],
                seg("07:46:14", "08:00:00", "type_on_laptop", "study")]
        self.assertTrue(all(found == [NO] for _, found in labels(late)))

    def test_a_coincidence_is_never_a_moment_to_help(self):
        evening = [seg("17:40:00", "17:40:04", "phone_rings", "evening_rest", "candidate"),
                   seg("17:40:04", "17:41:00", "talk_on_phone", "evening_rest"),
                   seg("17:41:00", "17:42:00", "watch_tv", "evening_rest"),
                   seg("17:42:00", "17:42:04", "get_can", "evening_rest", "approach"),
                   seg("17:42:04", "17:42:08", "put_can_next_to_self", "evening_rest", "action"),
                   seg("17:42:08", "18:00:00", "watch_tv", "evening_rest")]
        self.assertTrue(all(found == [NO] for _, found in labels(evening)))

    def test_leaving_the_view_right_after_the_signal_makes_the_signal_a_moment_to_help(self):
        gone = [seg("12:00:00", "12:00:04", "put_on_bag", "going_out", "candidate"),
                seg("12:00:04", "17:00:00", "unseen", "away", "unseen"),
                seg("17:00:00", "17:01:00", "watch_tv", "evening_rest")]
        self.assertEqual(labels(gone), [("12:00:00", [7]), ("17:00:00", [NO]), ("17:00:58", [NO])])
        seen = [seg("12:00:00", "12:00:04", "put_on_bag", "going_out", "candidate"),
                seg("12:00:04", "12:00:40", "check_pockets", "going_out"),
                seg("12:00:40", "12:00:44", "walk_to_light_switch", "going_out", "approach"),
                seg("12:00:44", "12:00:50", "turn_off_room_light", "going_out", "action"),
                seg("12:00:50", "17:00:00", "unseen", "away", "unseen")]
        self.assertEqual(labels(seen), [("12:00:00", [7]), ("12:00:04", [7]), ("12:00:38", [7]),
                                        ("12:00:40", [NO]), ("12:00:44", [NO]), ("12:00:48", [NO])])

    def test_two_signals_of_one_habit_make_one_stretch_to_help(self):
        self.assertEqual(labels(DINNER), [
            ("19:00:00", [6]), ("19:00:04", [6]), ("19:00:38", [6]), ("19:00:40", [6]), ("19:00:44", [6]),
            ("19:01:58", [6]), ("19:02:00", [NO]), ("19:02:04", [NO]), ("19:02:08", [NO])])


class AskTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "scoring" / "day-1-answers.jsonl"
        self.key, self.lines = key_for(BREAKFAST), record(BREAKFAST)

    def asker(self, fail_at=None):
        asked = []

        def ask(bundle):
            if len(asked) == fail_at:
                raise RuntimeError("connection lost")
            asked.append(bundle)
            return {"status": "valid", "output": {"observation": "x", "reasoning": "y", "task_index": NO},
                    "errors": []}
        return ask, asked

    def test_every_moment_is_asked_once_with_the_latest_five_lines(self):
        ask, asked = self.asker()
        answers = ds.ask_day(self.key, 1, self.lines, FSM, ask, self.path)
        moments = [time for time, _ in labels(BREAKFAST)]
        self.assertEqual([bundle["time"] for bundle in asked], moments)
        self.assertEqual([saved["time"] for saved in answers], moments)
        self.assertEqual(asked[0]["line_count"], 1)
        self.assertEqual(asked[2]["messages"][1]["content"][0]["text"].splitlines()[-5:],
                         ["07:39:52 | The person: eat_breakfast.", "07:39:54 | The person: eat_breakfast.",
                          "07:39:56 | The person: eat_breakfast.", "07:39:58 | The person: eat_breakfast.",
                          "07:40:00 | The person: finish_drinking."])

    def test_a_stopped_run_continues_without_asking_again(self):
        ask, _ = self.asker(fail_at=3)
        with self.assertRaises(RuntimeError):
            ds.ask_day(self.key, 1, self.lines, FSM, ask, self.path)
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 3)
        ask, asked = self.asker()
        answers = ds.ask_day(self.key, 1, self.lines, FSM, ask, self.path)
        self.assertEqual(len(asked), 8)
        self.assertEqual([saved["time"] for saved in answers], [time for time, _ in labels(BREAKFAST)])


class ScoreTests(unittest.TestCase):
    def test_the_answer_key_predictor_gets_everything_right(self):
        key = key_for(BREAKFAST)
        with tempfile.TemporaryDirectory() as temp:
            answers = ds.ask_day(key, 1, record(BREAKFAST), FSM, ds.answer_key_predictor(key, 1),
                                 Path(temp) / "answers.jsonl")
        report = ds.score_day(key, 1, answers)
        self.assertEqual((report["paper"]["accuracy"], report["paper"]["task_macro"]["f1"]), (1.0, 1.0))
        self.assertEqual(report["habits"], [{"task": 1, "action": "task 1", "should_help": 1, "helped": 1,
                                             "missed": 0, "wrong_help": 0, "missed_at": [], "wrong_at": []}])

    def test_missed_help_wrong_help_and_broken_answers_are_counted(self):
        picks = {"07:30:00": None, "07:42:00": 1}   # a broken answer; helping after the person started moving
        report = ds.score_day(key_for(BREAKFAST), 1, [answer(time, picks.get(time, NO))
                                                       for time, _ in labels(BREAKFAST)])
        self.assertEqual(report["asks"], 11)
        self.assertEqual(report["broken_answers"], 1)
        self.assertAlmostEqual(report["paper"]["accuracy"], 6 / 11)
        self.assertEqual(report["habits"], [{"task": 1, "action": "task 1", "should_help": 1, "helped": 0,
                                             "missed": 1, "wrong_help": 1, "missed_at": ["07:40:00"],
                                             "wrong_at": ["07:42:00"]}])

    def test_one_habit_with_two_signals_is_one_time_to_help(self):
        report = ds.score_day(key_for(DINNER), 1, [answer(time, 6 if time == "19:01:58" else NO)
                                                   for time, _ in labels(DINNER)])
        self.assertEqual([(h["should_help"], h["helped"], h["missed"]) for h in report["habits"]], [(1, 1, 0)])

    def test_answers_must_cover_every_moment_once(self):
        answers = [answer(time, NO) for time, _ in labels(BREAKFAST)]
        for wrong in (answers[1:], answers + answers[:1]):
            with self.assertRaises(ValueError):
                ds.score_day(key_for(BREAKFAST), 1, wrong)


if __name__ == "__main__":
    unittest.main()
