"""Tests for the synthetic-week generator (합성 기록 생성기 검사).

Small hand-made examples check the record format. The in-memory week checks that each
planted case sits where the plan (구현계획서 7장) puts it. No record files are written
except tiny ones in a temporary folder. Run from this folder:
    python -m unittest -v test_make_records
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_records as mr  # noqa: E402
from vocabulary import EVENTS, STATES, TASKS  # noqa: E402

FIVE_MINUTES = 300
WEEK: dict = {}


def setUpModule():
    WEEK.update(mr.build_week(20261114))


def t(text):
    hours, minutes, seconds = map(int, text.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def seg(start, end, event, state="study", role="background", case=None):
    return {"start": t(start), "end": t(end), "event": event, "state": state, "role": role, "case": case}


def occurrences(day, event, state=None):
    return [s for s in WEEK.get(day, []) if s["event"] == event and (state is None or s["state"] == state)]


def followed(day, start, action):
    """True when `action` starts within five minutes after `start`."""
    return any(start < s["start"] <= start + FIVE_MINUTES for s in occurrences(day, action))


class RecordLineTests(unittest.TestCase):
    SMALL = [seg("07:00:00", "07:00:06", "drink_water"), seg("07:00:06", "07:00:10", "look_at_phone")]

    def test_lines_are_two_seconds_apart_across_segments(self):
        lines = mr.render_lines(self.SMALL, "small")
        self.assertEqual([line.split(" | ")[0] for line in lines],
                         ["07:00:00", "07:00:02", "07:00:04", "07:00:06", "07:00:08"])

    def test_each_line_uses_a_phrase_of_the_event_at_that_time(self):
        sentences = [line.split(" | ", 1)[1] for line in mr.render_lines(self.SMALL, "small")]
        self.assertEqual(len(sentences), 5)
        for sentence in sentences[:3]:
            self.assertIn(sentence, EVENTS["drink_water"]["phrases"])
        for sentence in sentences[3:]:
            self.assertIn(sentence, EVENTS["look_at_phone"]["phrases"])

    def test_lines_carry_only_time_and_sentence(self):
        lines = mr.render_lines(self.SMALL, "small")
        self.assertTrue(lines)
        for line in lines:
            self.assertRegex(line, r"^\d\d:\d\d:\d\d \| [^|]+$")
            for hidden in ("study", "background", "drink_water", "look_at_phone"):
                self.assertNotIn(hidden, line)

    def test_long_event_is_worded_in_more_than_one_way(self):
        lines = mr.render_lines([seg("07:00:00", "07:02:00", "look_at_phone")], "mix")
        self.assertEqual(len(lines), 60)
        self.assertGreaterEqual(len({line.split(" | ", 1)[1] for line in lines}), 2)

    def test_same_seed_repeats_and_other_seed_differs(self):
        long = [seg("07:00:00", "07:02:00", "look_at_phone")]
        first = mr.render_lines(long, "abc")
        self.assertTrue(first)
        self.assertEqual(first, mr.render_lines(long, "abc"))
        self.assertNotEqual(first, mr.render_lines(long, "xyz"))

    def test_every_phrase_belongs_to_one_event_only(self):
        owners = {}
        for name, event in EVENTS.items():
            self.assertGreaterEqual(len(event["phrases"]), 2, name)
            for phrase in event["phrases"]:
                self.assertNotIn(phrase, owners, f"{name} and {owners.get(phrase)} share a phrase")
                owners[phrase] = name


class OutputFileTests(unittest.TestCase):
    TINY = {1: [seg("07:00:00", "07:00:04", "drink_water", state="breakfast"),
                seg("07:00:04", "07:00:08", "finish_drinking", state="breakfast",
                    role="candidate", case="daily_habit")]}

    def test_written_answer_key_matches_written_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            mr.write_outputs(Path(tmp), self.TINY, seed=7)
            record_path, key_path = Path(tmp) / "day1.txt", Path(tmp) / "answer_key.json"
            self.assertTrue(record_path.exists())
            self.assertTrue(key_path.exists())
            record = record_path.read_text(encoding="utf-8").splitlines()
            key = json.loads(key_path.read_text(encoding="utf-8"))
        self.assertEqual([line.split(" | ")[0] for line in record], ["07:00:00", "07:00:02", "07:00:04", "07:00:06"])
        for line in record[2:]:
            self.assertIn(line.split(" | ", 1)[1], EVENTS["finish_drinking"]["phrases"])
        self.assertEqual(key["seed"], 7)
        self.assertEqual(key["days"], [{"day": 1, "segments": [
            {"start": "07:00:00", "end": "07:00:04", "event": "drink_water", "state": "breakfast",
             "role": "background", "case": None},
            {"start": "07:00:04", "end": "07:00:08", "event": "finish_drinking", "state": "breakfast",
             "role": "candidate", "case": "daily_habit"},
        ]}])
        self.assertEqual(len(key["cases"]), 13)

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            mr.write_outputs(Path(tmp), self.TINY, seed=7)
            record_path = Path(tmp) / "day1.txt"
            self.assertTrue(record_path.exists())
            before = record_path.read_text(encoding="utf-8")
            with self.assertRaises(FileExistsError):
                mr.write_outputs(Path(tmp), self.TINY, seed=8)
            self.assertEqual(record_path.read_text(encoding="utf-8"), before)


class WeekShapeTests(unittest.TestCase):
    def test_each_day_runs_from_seven_to_eleven_without_gaps(self):
        for day in range(1, 8):
            segments = WEEK.get(day, [])
            self.assertTrue(segments, f"day {day} is empty")
            self.assertEqual(segments[0]["start"], t("07:00:00"))
            self.assertEqual(segments[-1]["end"], t("23:00:00"))
            for before, after in zip(segments, segments[1:]):
                self.assertEqual(before["end"], after["start"], f"day {day}")
            for segment in segments:
                self.assertGreater(segment["end"], segment["start"])
                self.assertEqual((segment["start"] - t("07:00:00")) % 2, 0)

    def test_neighbouring_segments_never_repeat_an_event(self):
        for day in range(1, 8):
            segments = WEEK.get(day, [])
            self.assertTrue(segments, f"day {day} is empty")
            for before, after in zip(segments, segments[1:]):
                self.assertNotEqual(before["event"], after["event"], f"day {day} at {after['start']}")

    def test_every_action_is_preceded_by_an_approach_step(self):
        actions = 0
        for day in range(1, 8):
            segments = WEEK.get(day, [])
            for index, segment in enumerate(segments):
                if segment["role"] == "action":
                    actions += 1
                    self.assertGreater(index, 0)
                    self.assertEqual(segments[index - 1]["role"], "approach", f"day {day} {segment}")
        self.assertGreater(actions, 0)

    def test_candidate_events_appear_only_where_planted(self):
        once_a_day = ("close_book", "finish_meal", "put_down_spoon", "phone_rings",
                      "close_laptop", "sit_at_desk", "put_on_bag")
        for day in range(1, 8):
            self.assertEqual(len(occurrences(day, "finish_drinking")), 2, day)
            for event in once_a_day:
                self.assertEqual(len(occurrences(day, event)), 1, (day, event))
            self.assertEqual(len(occurrences(day, "guest_finishes_can")), 3 if day == 4 else 0, day)
            self.assertEqual(len(occurrences(day, "finish_vacuuming")), 1 if day == 6 else 0, day)
            self.assertEqual(len(occurrences(day, "put_down_chopsticks")), 3, day)


class PlantedCaseTests(unittest.TestCase):
    def test_cup_goes_in_dishwasher_after_finishing_a_drink_every_breakfast(self):
        for day in range(1, 8):
            drinks = occurrences(day, "finish_drinking", "breakfast")
            self.assertEqual(len(drinks), 1, day)
            self.assertTrue(followed(day, drinks[0]["start"], "put_cup_in_dishwasher"), day)

    def test_finishing_a_drink_while_studying_leaves_the_cup(self):
        for day in range(1, 8):
            drinks = occurrences(day, "finish_drinking", "study")
            self.assertEqual(len(drinks), 1, day)
            self.assertFalse(followed(day, drinks[0]["start"], "put_cup_in_dishwasher"), day)

    def test_lamp_follows_the_book_except_on_day_two(self):
        for day in range(1, 8):
            books = occurrences(day, "close_book", "bedtime")
            self.assertEqual(len(books), 1, day)
            self.assertEqual(followed(day, books[0]["start"], "turn_off_bedside_lamp"), day != 2, day)
            self.assertEqual(len(occurrences(day, "turn_off_bedside_lamp")), 1, day)

    def test_bowl_follows_both_dinner_candidates_every_day(self):
        for day in range(1, 8):
            for candidate in ("finish_meal", "put_down_spoon"):
                found = occurrences(day, candidate, "dinner")
                self.assertEqual(len(found), 1, (day, candidate))
                self.assertTrue(followed(day, found[0]["start"], "put_bowl_in_dishwasher"), (day, candidate))

    def test_chopsticks_go_down_three_times_before_every_dinner_bowl(self):
        for day in range(1, 8):
            downs = sorted(s["start"] for s in occurrences(day, "put_down_chopsticks", "dinner"))
            bowls = [s["start"] for s in occurrences(day, "put_bowl_in_dishwasher")]
            self.assertEqual(len(downs), 3, day)
            self.assertEqual(len(bowls), 1, day)
            # All three lie within five minutes before the bowl, so crediting each one
            # would count the bowl three times; only the last has no repeat after it.
            for down in downs:
                self.assertTrue(0 < bowls[0] - down <= FIVE_MINUTES, (day, down))
            pickups = [s["start"] for s in occurrences(day, "pick_up_chopsticks")]
            for before, after in zip(downs, downs[1:]):
                self.assertTrue(any(before < pickup < after for pickup in pickups), day)

    def test_breakfast_phone_is_checked_three_times_and_once_before_the_cup(self):
        for day in range(1, 8):
            phones = occurrences(day, "look_at_phone", "breakfast")
            self.assertEqual(len(phones), 3, day)
            self.assertEqual(sum(followed(day, p["start"], "put_cup_in_dishwasher") for p in phones), 1, day)

    def test_phone_is_checked_more_than_fifteen_times_each_day(self):
        for day in range(1, 8):
            self.assertGreater(len(occurrences(day, "look_at_phone")), 15, day)

    def test_call_brings_a_can_only_on_days_one_and_two(self):
        for day in range(1, 8):
            calls = occurrences(day, "phone_rings", "evening_rest")
            self.assertEqual(len(calls), 1, day)
            self.assertEqual(followed(day, calls[0]["start"], "put_can_next_to_self"), day in (1, 2), day)
            self.assertEqual(len(occurrences(day, "put_can_next_to_self")), 1 if day in (1, 2) else 0, day)

    def test_book_is_stored_after_closing_the_laptop_only_on_odd_days(self):
        for day in range(1, 8):
            closes = occurrences(day, "close_laptop", "study")
            self.assertEqual(len(closes), 1, day)
            self.assertEqual(followed(day, closes[0]["start"], "put_book_in_storage"), day % 2 == 1, day)

    def test_guest_cans_are_stored_three_times_only_on_day_four(self):
        cans = occurrences(4, "guest_finishes_can", "evening_rest")
        self.assertEqual(len(cans), 3)
        for can in cans:
            self.assertTrue(followed(4, can["start"], "put_can_in_storage"))
        for day in (1, 2, 3, 5, 6, 7):
            self.assertEqual(occurrences(day, "put_can_in_storage"), [], day)

    def test_lamp_is_stored_after_vacuuming_only_on_day_six(self):
        done = occurrences(6, "finish_vacuuming", "evening_rest")
        self.assertEqual(len(done), 1)
        self.assertTrue(followed(6, done[0]["start"], "put_lamp_in_storage"))
        for day in range(1, 8):
            self.assertEqual(len(occurrences(day, "put_lamp_in_storage")), 1 if day == 6 else 0, day)

    def test_room_light_is_unseen_on_days_three_and_five(self):
        for day in range(1, 8):
            bags = occurrences(day, "put_on_bag", "going_out")
            self.assertEqual(len(bags), 1, day)
            bag, segments = bags[0], WEEK[day]
            after = segments[segments.index(bag) + 1]
            if day in (3, 5):
                self.assertEqual(after["event"], "unseen", day)
                self.assertGreaterEqual(after["end"] - bag["end"], FIVE_MINUTES, day)
                self.assertEqual(occurrences(day, "turn_off_room_light"), [], day)
            else:
                self.assertTrue(followed(day, bag["start"], "turn_off_room_light"), day)
                light = occurrences(day, "turn_off_room_light")[0]
                self.assertFalse(any(s["event"] == "unseen" and bag["end"] <= s["start"] < light["start"]
                                     for s in segments), day)

    def test_cup_is_fetched_after_sitting_at_desk_except_day_three(self):
        for day in range(1, 8):
            sits = occurrences(day, "sit_at_desk", "study")
            self.assertEqual(len(sits), 1, day)
            self.assertEqual(followed(day, sits[0]["start"], "put_cup_next_to_self"), day != 3, day)

    def test_cup_fetches_fill_about_a_fifth_of_visible_slots(self):
        # With 6 of 7 mornings followed, the p-value must fail on night 6 (5 of 6) and
        # pass on night 7 (6 of 7). Worked out by hand, that holds for a base rate
        # between 0.185 and 0.235. The two slots right after sitting down are excluded.
        slots = list(range(t("07:00:00"), t("12:30:00"), 300)) + list(range(t("17:00:00"), t("23:00:00"), 300))
        slots = [slot for slot in slots if slot not in (t("08:00:00"), t("08:05:00"))]
        for day in range(1, 8):
            starts = [s["start"] for s in occurrences(day, "put_cup_next_to_self")]
            self.assertTrue(starts, day)
            filled = sum(any(slot <= start < slot + 300 for start in starts) for slot in slots)
            ratio = filled / len(slots)
            self.assertGreaterEqual(ratio, 0.185, (day, ratio))
            self.assertLessEqual(ratio, 0.235, (day, ratio))


class AnswerKeyTests(unittest.TestCase):
    def test_rules_use_real_tasks_and_one_to_three_candidates(self):
        self.assertTrue(mr.RULES)
        for rule in mr.RULES:
            self.assertIn(rule["task"], range(len(TASKS)), rule["id"])
            self.assertIn(rule["state"], STATES, rule["id"])
            self.assertTrue(1 <= len(rule["candidates"]) <= 3, rule["id"])
            for candidate in rule["candidates"]:
                self.assertIn(candidate["event"], EVENTS, rule["id"])
                self.assertTrue(set(candidate["expected_nights"]) <= set(range(1, 8)), rule["id"])

    def test_forbidden_steps_lead_into_the_rule_task(self):
        checked = 0
        for rule in mr.RULES:
            self.assertTrue(rule["forbidden"], rule["id"])
            for event in rule["forbidden"]:
                for day in range(1, 8):
                    segments = WEEK[day]
                    for index, segment in enumerate(segments):
                        if segment["event"] != event:
                            continue
                        self.assertEqual(segment["role"], "approach", (rule["id"], day))
                        action = next(s for s in segments[index:] if s["role"] == "action")
                        self.assertEqual(EVENTS[action["event"]]["task"], rule["task"], (rule["id"], day))
                        checked += 1
        self.assertGreater(checked, 0)

    def test_every_case_points_at_its_rule_candidate(self):
        self.assertEqual(len(mr.CASES), 13)
        rules = {rule["id"]: rule for rule in mr.RULES}
        for case in mr.CASES:
            if case["rule"] is None:
                continue
            self.assertIn(case["rule"], rules, case["id"])
            events = [candidate["event"] for candidate in rules[case["rule"]]["candidates"]]
            self.assertIn(case["candidate"], events, case["id"])


if __name__ == "__main__":
    unittest.main()
