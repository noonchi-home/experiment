"""Tests for the one-hour morning record (아침 1시간 합성 기록 생성기 검사).

Small hand-made examples check the story check. The in-memory week (five mornings)
checks the record format, that the mornings read like a real person's morning (no line
contradicts an earlier one, small movements now and then, one-time steps once and in
order) and that every planted case sits where the plan puts it, including the nights on
which each planted candidate must pass the 80%·p-value check. No record files are
written except in a temporary folder. Run from this folder:
    python -m unittest -v test_make_records
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_records as mr  # noqa: E402
from vocabulary import (CURTAINS_CLOSED, CURTAINS_OPEN, ELSEWHERE, EVENTS, LEFT, STATES, TASKS,  # noqa: E402
                        TV_ON, WORDS)
import free_steps  # noqa: E402,F401  (puts ai/ on the path for pam)
from pam.trigger_check import check_candidate  # noqa: E402

FIVE_MINUTES = 300
DAYS = range(1, 6)
WEEK: dict = {}
RECORD: dict = {}            # day -> record lines, as written to dayN.txt


def setUpModule():
    WEEK.update(mr.build_week(mr.SEED))
    RECORD.update({day: mr.render_lines(WEEK[day], f"{mr.SEED}-render-day{day}") for day in DAYS})


def t(text):
    hours, minutes, seconds = map(int, text.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def seg(start, end, event, state="breakfast", role="background", place="table"):
    return {"start": t(start), "end": t(end), "event": event, "state": state, "role": role, "case": None,
            "place": place, "things": (), "curtains": False, "tv": False}


def occurrences(day, event, state=None):
    return [s for s in WEEK[day] if s["event"] == event and (state is None or s["state"] == state)]


def once(day, event):
    found = occurrences(day, event)
    assert len(found) == 1, (day, event, len(found))
    return found[0]


def followed(day, segment, action):
    """True when `action` starts within five minutes after the segment starts."""
    return any(segment["start"] < s["start"] <= segment["start"] + FIVE_MINUTES for s in occurrences(day, action))


def task_starts(day, task):
    return [s["start"] for s in WEEK[day] if EVENTS[s["event"]]["task"] == task]


def check(rule, candidate, night):
    days = [{"start": mr.DAY_START, "end": mr.DAY_END,
             "candidate": [s["start"] for s in occurrences(day, candidate, rule["state"])],
             "action": task_starts(day, rule["task"]),
             "unseen": [(s["start"], s["end"]) for s in occurrences(day, "unseen")]}
            for day in range(1, night + 1)]
    return check_candidate(days)


def lines_of(day, segment):
    """The sentences written for one segment of the week."""
    first, last = (segment["start"] - mr.DAY_START) // 2, (segment["end"] - mr.DAY_START) // 2
    return [line.split(" | ", 1)[1] for line in RECORD[day][first:last]]


def phrases_at(event, place):
    words = WORDS.get(place, ELSEWHERE)
    return [phrase.format(**words) for phrase in EVENTS[event]["phrases"]]


class RecordLineTests(unittest.TestCase):
    def test_each_morning_has_1800_lines_two_seconds_apart_from_seven_to_eight(self):
        for day in DAYS:
            self.assertEqual([t(line[:8]) for line in RECORD[day]], list(range(mr.DAY_START, mr.DAY_END, 2)), day)

    def test_lines_carry_only_time_and_sentence(self):
        for day in DAYS:
            for line in RECORD[day]:
                self.assertRegex(line, r"^\d\d:\d\d:\d\d \| [^|_]+$")
                for hidden in ("background", "candidate", "approach"):
                    self.assertNotIn(hidden, line)

    def test_each_line_uses_a_phrase_of_the_event_at_that_time(self):
        for day in DAYS:
            for segment in WEEK[day]:
                options = phrases_at(segment["event"], segment["place"])
                if EVENTS[segment["event"]]["kind"] == "absent":
                    options += list(LEFT)
                for sentence in lines_of(day, segment):
                    self.assertTrue(any(option in sentence for option in options), (day, segment["event"], sentence))

    def test_same_seed_repeats_and_other_seed_differs(self):
        self.assertEqual(mr.build_day(1, mr.SEED), WEEK[1])
        self.assertEqual(mr.render_lines(WEEK[1], "abc"), mr.render_lines(WEEK[1], "abc"))
        self.assertNotEqual(mr.render_lines(WEEK[1], "abc"), mr.render_lines(WEEK[1], "xyz"))

    def test_no_phrase_sits_inside_a_phrase_of_another_event(self):
        for name, event in EVENTS.items():
            self.assertGreaterEqual(len(event["phrases"]), 3, name)
            for other, other_event in EVENTS.items():
                if other != name:
                    for phrase in event["phrases"]:
                        for longer in other_event["phrases"]:
                            self.assertNotIn(phrase, longer, (name, other))


class SentenceTests(unittest.TestCase):
    """The record reads like the real predictor's observation log, not like a list of action labels."""

    def test_no_sentence_says_again_and_no_light_has_another_name(self):
        for day in DAYS:
            for line in RECORD[day]:
                for word in (" again", "ceiling", "lamp"):
                    self.assertNotIn(word, line)

    def test_what_is_in_hand_is_not_listed_as_lying_around(self):
        checked = 0
        for day in DAYS:
            for segment in WEEK[day]:
                for used in EVENTS[segment["event"]]["uses"]:
                    for label in segment["things"]:
                        self.assertNotIn(used, label, (day, segment["event"]))
                    checked += 1
        self.assertGreater(checked, 50)

    def test_what_was_just_done_is_still_mentioned_on_the_next_line(self):
        checked = 0
        for day in DAYS:
            for before, segment in zip(WEEK[day], WEEK[day][1:]):
                done = EVENTS[before["event"]]["done"]
                if done and EVENTS[segment["event"]]["kind"] == "activity":
                    words = WORDS.get(before["place"], ELSEWHERE)
                    first = lines_of(day, segment)[0]
                    self.assertTrue(any(text.format(**words) in first for text in done), first)
                    checked += 1
        self.assertGreater(checked, 20)

    def test_a_step_is_worded_as_going_on_before_it_is_worded_as_done(self):
        for day in DAYS:
            for segment in WEEK[day]:
                lines = lines_of(day, segment)
                if EVENTS[segment["event"]]["kind"] == "step" and len(lines) > 1:
                    self.assertNotRegex(lines[0], r"^(The|A) person has ", (day, segment["event"]))

    def test_curtains_and_tv_are_described_as_they_are(self):
        for day in DAYS:
            for segment in WEEK[day]:
                for sentence in lines_of(day, segment):
                    if any(text in sentence for text in CURTAINS_CLOSED):
                        self.assertFalse(segment["curtains"], sentence)
                    if any(text in sentence for text in CURTAINS_OPEN):
                        self.assertTrue(segment["curtains"], sentence)
                    if any(text in sentence for text in TV_ON):
                        self.assertTrue(segment["tv"], sentence)
                        self.assertNotEqual(segment["event"], "watch_tv", sentence)   # never "watching TV, while the TV is on"

    def test_the_first_lines_after_the_person_walks_out_say_so(self):
        for day in DAYS:
            for segment in occurrences(day, "unseen"):
                for sentence in lines_of(day, segment)[:2]:
                    self.assertTrue(any(sentence.startswith(text) for text in LEFT), sentence)


class StoryCheckTests(unittest.TestCase):
    def test_no_morning_contradicts_itself(self):
        for day in DAYS:
            self.assertEqual(mr.story_problems(WEEK[day]), [], day)

    def test_contradictions_are_reported(self):
        cases = {
            "water without a cup": [seg("07:20:00", "07:20:06", "drink_water")],
            "eating without the spoon": [seg("07:18:00", "07:18:06", "bring_breakfast", place="kitchen"),
                                         seg("07:18:06", "07:18:20", "eat_cereal")],
            "curtains opened twice": [seg("07:02:00", "07:02:04", "open_curtains", "wake", place="window"),
                                      seg("07:02:04", "07:02:08", "open_curtains", "wake", place="window")],
            "talking without a call": [seg("07:40:00", "07:41:00", "talk_on_phone", "rest", place="sofa")],
            "TV watched while off": [seg("07:40:00", "07:41:00", "watch_tv", "rest", place="sofa")],
            "coffee from an unopened can": [seg("07:33:00", "07:33:04", "drink_coffee", "rest", place="sofa")],
            "zipping an unpacked bag": [seg("07:52:00", "07:52:04", "zip_bag", "leaving", place="deskside")],
            "acting after leaving": [seg("07:57:00", "07:57:02", "leave_home", "leaving", place="door"),
                                     seg("07:57:02", "07:57:10", "yawn", "away", place="room")],
        }
        for name, segments in cases.items():
            self.assertTrue(mr.story_problems(segments), name)


class DayShapeTests(unittest.TestCase):
    def test_each_morning_runs_from_seven_to_eight_without_gaps(self):
        for day in DAYS:
            segments = WEEK[day]
            self.assertEqual((segments[0]["start"], segments[-1]["end"]), (mr.DAY_START, mr.DAY_END), day)
            for before, after in zip(segments, segments[1:]):
                self.assertEqual(before["end"], after["start"], day)

    def test_neighbouring_segments_never_repeat_an_event(self):
        for day in DAYS:
            for before, after in zip(WEEK[day], WEEK[day][1:]):
                self.assertNotEqual(before["event"], after["event"], (day, mr.hms(after["start"])))

    def test_every_action_comes_right_after_its_approach_steps(self):
        for day in DAYS:
            segments = WEEK[day]
            for index, segment in enumerate(segments):
                if segment["role"] == "action":
                    roles = [s["role"] for s in segments[max(0, index - 3):index]]
                    self.assertIn("approach", roles, (day, segment["event"]))

    def test_the_morning_does_not_run_like_clockwork(self):
        for event in ("get_out_of_bed", "sit_at_table", "finish_meal", "finish_coffee", "put_on_bag"):
            starts = [once(day, event)["start"] for day in DAYS]
            self.assertGreaterEqual(max(starts) - min(starts), 60, event)


ONCE_IN_ORDER = ("turn_off_alarm", "sit_up_in_bed", "get_out_of_bed", "turn_on_room_light", "get_dressed",
                 "bring_breakfast", "sit_at_table", "finish_drinking", "finish_meal", "pick_up_dishes",
                 "put_bowl_in_dishwasher", "put_cup_in_dishwasher", "take_coffee_from_fridge", "put_can_next_to_self",
                 "turn_on_tv", "open_coffee_can", "finish_coffee", "turn_off_tv", "put_can_in_storage", "pack_bag",
                 "zip_bag", "put_on_jacket", "check_pockets", "put_on_bag", "leave_home")


class RealismTests(unittest.TestCase):
    def test_steps_done_once_happen_once_and_in_order(self):
        for day in DAYS:
            for event in ("open_curtains", "make_bed", "phone_rings"):
                once(day, event)
            starts = [once(day, event)["start"] for event in ONCE_IN_ORDER]
            self.assertEqual(starts, sorted(starts), day)

    def test_small_movements_come_now_and_then_and_never_again_and_again(self):
        for day in DAYS:
            for event, gap in mr.RARE.items():
                starts = [s["start"] for s in occurrences(day, event)]
                for before, after in zip(starts, starts[1:]):
                    self.assertGreaterEqual(after - before, gap, (day, event))

    def test_breakfast_takes_eleven_to_fifteen_minutes_with_sips_and_the_spoon_put_down(self):
        for day in DAYS:
            sat, done = once(day, "sit_at_table")["start"], once(day, "finish_meal")["start"]
            self.assertTrue(11 * 60 <= done - sat <= 15 * 60 + 10, (day, done - sat))
            drank = once(day, "finish_drinking")["start"]
            self.assertGreaterEqual(len([s for s in occurrences(day, "drink_water") if s["start"] < drank]), 1, day)
            self.assertGreaterEqual(len(occurrences(day, "put_down_spoon")), 2, day)

    def test_coffee_is_sipped_several_times_before_it_is_finished(self):
        for day in DAYS:
            opened, finished = once(day, "open_coffee_can")["start"], once(day, "finish_coffee")["start"]
            sips = [s for s in occurrences(day, "drink_coffee") if opened < s["start"] < finished]
            self.assertGreaterEqual(len(sips), 3, day)

    def test_the_person_is_out_of_view_to_wash_to_brush_teeth_and_after_leaving(self):
        for day in DAYS:
            washing, teeth, away = [s["end"] - s["start"] for s in occurrences(day, "unseen")]
            self.assertTrue(7 * 60 <= washing <= 10 * 60, day)
            self.assertTrue(150 <= teeth <= 240, day)
            self.assertGreaterEqual(away, 120, day)
            self.assertEqual(WEEK[day][-1]["event"], "unseen")

    def test_the_phone_is_picked_up_many_times(self):
        for day in DAYS:
            self.assertGreaterEqual(len(occurrences(day, "look_at_phone")), 5, day)


class PlantedCaseTests(unittest.TestCase):
    def test_curtains_are_opened_within_a_minute_of_getting_up_except_on_day_two(self):
        for day in DAYS:
            gap = once(day, "open_curtains")["start"] - once(day, "get_out_of_bed")["start"]
            if day == mr.LATE_CURTAIN_DAY:
                self.assertGreater(gap, FIVE_MINUTES)
            else:
                self.assertLessEqual(gap, 60, day)

    def test_on_day_two_the_person_stays_in_view_over_five_minutes_and_opens_the_curtains_after_washing(self):
        day = mr.LATE_CURTAIN_DAY
        washing = occurrences(day, "unseen")[0]
        self.assertGreater(washing["start"] - once(day, "get_out_of_bed")["start"], FIVE_MINUTES + 30)
        self.assertGreater(once(day, "open_curtains")["start"], washing["end"])

    def test_cup_goes_in_the_dishwasher_one_and_a_half_to_four_and_a_half_minutes_after_the_last_drink(self):
        for day in DAYS:
            gap = once(day, "put_cup_in_dishwasher")["start"] - once(day, "finish_drinking")["start"]
            self.assertTrue(90 <= gap <= 270, (day, gap))

    def test_bowl_and_coffee_come_within_five_minutes_after_the_last_spoonful(self):
        for day in DAYS:
            for action in ("put_bowl_in_dishwasher", "put_can_next_to_self"):
                self.assertTrue(followed(day, once(day, "finish_meal"), action), (day, action))

    def test_only_the_wipe_after_the_meal_is_followed_by_the_bowl(self):
        for day in DAYS:
            wipes = occurrences(day, "wipe_mouth", "breakfast")
            self.assertIn(len(wipes), (2, 3), day)
            done = once(day, "finish_meal")["start"]
            self.assertEqual([wipe["start"] > done for wipe in wipes], [False] * (len(wipes) - 1) + [True], day)
            self.assertTrue(followed(day, wipes[-1], "put_bowl_in_dishwasher"), day)

    def test_breakfast_phone_checks_lie_near_the_cup_only_on_days_one_three_and_four(self):
        for day in DAYS:
            checks = occurrences(day, "look_at_phone", "breakfast")
            self.assertGreaterEqual(len(checks), 2, day)
            near = [check for check in checks if followed(day, check, "put_cup_in_dishwasher")]
            self.assertEqual(near, [checks[-1]] if day in mr.NEAR_PHONE_DAYS else [], day)

    def test_the_call_is_followed_by_putting_the_can_away_only_on_days_one_and_two(self):
        for day in DAYS:
            call = once(day, "phone_rings")
            self.assertEqual(call["state"], "rest")
            self.assertEqual(followed(day, call, "put_can_in_storage"), day in mr.CALL_THEN_CAN_DAYS, day)
            if day not in mr.CALL_THEN_CAN_DAYS:
                self.assertGreaterEqual(once(day, "put_can_in_storage")["start"] - call["start"], 7 * 60 + 30, day)

    def test_the_room_light_is_turned_off_in_view_except_on_days_three_and_five(self):
        for day in DAYS:
            bag = once(day, "put_on_bag")
            if day in mr.UNSEEN_LIGHT_DAYS:
                self.assertEqual(occurrences(day, "turn_off_room_light"), [], day)
                after = WEEK[day][WEEK[day].index(bag) + 1:]
                self.assertEqual([s["event"] for s in after], ["leave_home", "unseen"], day)
            else:
                self.assertLessEqual(once(day, "turn_off_room_light")["start"] - bag["start"], 30, day)

    def test_every_planted_candidate_passes_on_exactly_the_expected_nights(self):
        for rule in mr.RULES:
            for candidate in rule["candidates"]:
                passed = [night for night in DAYS if check(rule, candidate["event"], night)["passed"]]
                self.assertEqual(passed, list(candidate["expected_nights"]), (rule["id"], candidate["event"]))


class AnswerKeyTests(unittest.TestCase):
    def test_the_robot_can_open_the_curtains_as_the_eleventh_task(self):
        self.assertEqual(TASKS[10], "Open the curtains.")
        self.assertEqual(EVENTS["open_curtains"]["task"], 10)

    def test_rules_use_real_tasks_and_one_to_three_candidates(self):
        for rule in mr.RULES:
            self.assertIn(rule["task"], range(len(TASKS)), rule["id"])
            self.assertIn(rule["state"], STATES, rule["id"])
            self.assertTrue(1 <= len(rule["candidates"]) <= 3, rule["id"])
            for candidate in rule["candidates"]:
                self.assertIn(candidate["event"], EVENTS, rule["id"])
                self.assertTrue(set(candidate["expected_nights"]) <= set(DAYS), rule["id"])

    def test_forbidden_steps_lead_into_the_rule_task(self):
        checked = 0
        for rule in mr.RULES:
            self.assertTrue(rule["forbidden"], rule["id"])
            for event in rule["forbidden"]:
                for day in DAYS:
                    for segment in occurrences(day, event):
                        self.assertEqual(segment["role"], "approach", (rule["id"], day))
                        self.assertTrue(any(segment["start"] < start <= segment["start"] + 60
                                            for start in task_starts(day, rule["task"])), (rule["id"], event, day))
                        checked += 1
        self.assertGreater(checked, 0)

    def test_every_case_points_at_its_rule_candidate(self):
        self.assertEqual(len(mr.CASES), 10)
        rules = {rule["id"]: rule for rule in mr.RULES}
        for case in mr.CASES:
            if case["rule"] is not None:
                events = [candidate["event"] for candidate in rules[case["rule"]]["candidates"]]
                self.assertIn(case["candidate"], events, case["id"])


class OutputFileTests(unittest.TestCase):
    def test_written_answer_key_matches_written_record(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "data"
            mr.write_outputs(out, {1: WEEK[1]}, mr.SEED)
            self.assertEqual((out / "day1.txt").read_text(encoding="utf-8").splitlines(), RECORD[1])
            key = json.loads((out / "answer_key.json").read_text(encoding="utf-8"))
            self.assertEqual((key["day_start"], key["day_end"], key["line_seconds"]), ("07:00:00", "08:00:00", 2))
            segments = key["days"][0]["segments"]
            self.assertEqual([(s["start"], s["event"]) for s in segments],
                             [(mr.hms(s["start"]), s["event"]) for s in WEEK[1]])

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / "day1.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                mr.write_outputs(out, {1: WEEK[1]}, mr.SEED)
            self.assertEqual((out / "day1.txt").read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
