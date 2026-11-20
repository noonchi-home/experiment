"""Tests for the weekday synthetic record (합성 기록 생성기 검사).

Small hand-made examples check the record format and the story check. The in-memory
week (five weekdays) checks that the days read like a real person's day (no line
contradicts an earlier one, utensils go down many times, counts taken from real-world
data) and that every planted case sits where the plan puts it. No record files are
written except tiny ones in a temporary folder. Run from this folder:
    python -m unittest -v test_make_records
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_records as mr  # noqa: E402
from vocabulary import EVENTS, STATES, TASKS  # noqa: E402
import free_steps  # noqa: E402,F401  (puts ai/ on the path for pam)
from pam.trigger_check import check_candidate  # noqa: E402

FIVE_MINUTES = 300
DAYS = range(1, 6)
WEEK: dict = {}
RECORD: dict = {}            # day -> record lines, as written to dayN.txt


def setUpModule():
    WEEK.update(mr.build_week(mr.SEED))
    RECORD.update({day: mr.render_lines(WEEK[day], f"{mr.SEED}-render-day{day}") for day in DAYS})


def says(sentence, event, place="desk"):
    """True when the sentence uses one of the event's phrases, filled in for that place."""
    words = mr.WORDS.get(place, mr.ELSEWHERE)
    return any(phrase.format(**words).rstrip(".") in sentence for phrase in EVENTS[event]["phrases"])


def lines_of(day, segment):
    """The sentences written for one segment of the week."""
    first, last = (segment["start"] - mr.DAY_START) // 2, (segment["end"] - mr.DAY_START) // 2
    return [line.split(" | ", 1)[1] for line in RECORD[day][first:last]]


def t(text):
    hours, minutes, seconds = map(int, text.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def seg(start, end, event, state="study", role="background", case=None):
    return {"start": t(start), "end": t(end), "event": event, "state": state, "role": role, "case": case}


def occurrences(day, event, state=None):
    return [s for s in WEEK.get(day, []) if s["event"] == event and (state is None or s["state"] == state)]


def moment(segment):
    """When a moment counts, as in the moment list: a short event at its start, a long one at its last line."""
    return segment["start"] if segment["end"] - segment["start"] <= 4 else segment["end"] - 2


def followed(day, segment, action):
    """True when `action` starts within five minutes after the segment's moment."""
    start = moment(segment)
    return any(start < s["start"] <= start + FIVE_MINUTES for s in occurrences(day, action))


def task_starts(day, task):
    return [s["start"] for s in WEEK[day] if EVENTS[s["event"]]["task"] == task]


def check(rule, candidate, night):
    days = [{"start": mr.DAY_START, "end": mr.DAY_END,
             "candidate": [moment(s) for s in occurrences(day, candidate, rule["state"])],
             "action": task_starts(day, rule["task"]),
             "unseen": [(s["start"], s["end"]) for s in occurrences(day, "unseen")]}
            for day in range(1, night + 1)]
    return check_candidate(days)


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
            self.assertTrue(says(sentence, "drink_water"), sentence)
        for sentence in sentences[3:]:
            self.assertTrue(says(sentence, "look_at_phone"), sentence)

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


class SentenceTests(unittest.TestCase):
    """The record reads like the real predictor's observation log, not like a list of action labels.

    Real lines (ai/artifacts/routine_vllm_fsm_2026-11-04) give the posture, what the person
    is doing and the things lying around; what was just done is still mentioned for a few
    seconds; the person is seen leaving. The person's behaviour is in the timeline and the
    phrases of one event only word the same visible thing in different ways. On 2026-11-16
    "cook dinner" mixed a microwave and a pot, and "pack the bag" zipped the bag in the
    middle of packing: every two seconds the person seemed to do something else.
    """

    def segments(self, kind):
        return [(day, s) for day in DAYS for s in WEEK[day] if EVENTS[s["event"]]["kind"] == kind]

    def test_an_event_seen_in_several_places_names_no_place(self):
        places = {}
        for day in DAYS:
            for s in WEEK[day]:
                places.setdefault(s["event"], set()).add(s["place"])
        for name, seen in places.items():
            if len(seen & {"table", "desk", "sofa"}) > 1:
                for phrase in (*EVENTS[name]["phrases"], *EVENTS[name]["done"]):
                    for place in ("table", "desk", "sofa"):
                        self.assertNotIn(place, phrase, name)

    def test_no_sentence_says_again_because_an_event_can_be_the_first_time(self):
        for name, event in EVENTS.items():
            for phrase in (*event["phrases"], *event["done"]):
                self.assertNotIn("again", phrase.rstrip(".").split(), name)

    def test_an_activity_line_gives_the_posture_of_where_the_person_is(self):
        checked = 0
        for day, s in self.segments("activity"):
            for sentence in lines_of(day, s):
                if ", and is now " in sentence or sentence.split(" ", 2)[2].startswith(("is vacuuming", "is running",
                                                                                         "is pushing")):
                    continue
                self.assertTrue(any(posture in sentence for posture in mr.POSTURE[s["place"]]), sentence)
                checked += 1
        self.assertGreater(checked, 50000)

    def test_things_lying_around_are_mentioned_but_never_the_thing_in_use(self):
        typing = [line for day, s in self.segments("activity") if s["event"] == "type_on_laptop"
                  for line in lines_of(day, s)]
        reading = [line for day, s in self.segments("activity") if s["event"] == "read_book_at_desk"
                   for line in lines_of(day, s)]
        self.assertFalse([line for line in typing if "laptop on the desk" in line or "open laptop" in line])
        self.assertTrue([line for line in typing if "a cup" in line and "on the desk" in line])
        self.assertTrue([line for line in reading if "open laptop" in line])
        watching = [line for s in WEEK[1] if s["event"] == "watch_tv" for line in lines_of(1, s)]
        self.assertTrue([line for line in watching if "a can" in line and "side table" in line])

    def test_what_was_just_done_is_still_mentioned_for_a_few_lines(self):
        mentioned = 0
        for day in DAYS:
            for before, s in zip(WEEK[day], WEEK[day][1:]):
                still = [", and is now " in sentence for sentence in lines_of(day, s)]
                if EVENTS[s["event"]]["kind"] != "activity" or not EVENTS[before["event"]]["done"]:
                    self.assertNotIn(True, still, (day, s["event"]))
                    continue
                count = sum(still)
                self.assertLessEqual(count, 4)
                self.assertEqual(still[:count], [True] * count)       # only the first lines
                mentioned += count
        self.assertGreater(mentioned, 100)

    def test_a_step_is_worded_as_going_on_before_it_is_worded_as_done(self):
        for day, s in self.segments("step"):
            done = [" has " in f" {sentence}" for sentence in lines_of(day, s)]
            if len(done) > 1:
                self.assertFalse(done[0], (day, s["event"]))
            self.assertEqual(done, sorted(done), (day, s["event"]))

    def test_the_room_light_keeps_the_names_the_real_predictor_uses(self):
        # In the real logs (2,102 lines) the light was "room light" 45 times and "main room
        # light" 47 times, never "ceiling light". A third name made one switch-off read as two
        # different lights on 2026-11-16, so the record now uses the real names only.
        names = {name for day in DAYS for line in RECORD[day]
                 for name in ("ceiling light", "overhead light", "main light") if name in line.replace("main room", "")}
        self.assertEqual(names, set())
        self.assertTrue(any("main room light" in line for day in DAYS for line in RECORD[day]))

    def test_the_first_lines_after_the_person_walks_out_say_so(self):
        for day, s in self.segments("absent"):
            sentences = lines_of(day, s)
            self.assertTrue(sentences[0].startswith(mr.LEFT), sentences[0])
            for sentence in sentences:
                self.assertTrue(sentence.startswith((*mr.LEFT, *EVENTS["unseen"]["phrases"])), sentence)


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
            self.assertTrue(says(line, "finish_drinking", "table"), line)
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


class StoryCheckTests(unittest.TestCase):
    def test_a_consistent_little_breakfast_has_no_problems(self):
        story = [seg("07:00:00", "07:00:04", "get_cup", "breakfast", "approach"),
                 seg("07:00:04", "07:00:08", "put_cup_next_to_self", "breakfast", "action"),
                 seg("07:00:08", "07:00:12", "sit_at_table", "breakfast"),
                 seg("07:00:12", "07:00:40", "eat_breakfast", "breakfast"),
                 seg("07:00:40", "07:00:46", "drink_water", "breakfast"),
                 seg("07:00:46", "07:00:50", "finish_drinking", "breakfast", "candidate"),
                 seg("07:00:50", "07:00:54", "finish_breakfast", "breakfast"),
                 seg("07:00:54", "07:00:58", "pick_up_empty_cup", "breakfast", "approach"),
                 seg("07:00:58", "07:01:02", "carry_cup_to_kitchen", "breakfast", "approach"),
                 seg("07:01:02", "07:01:08", "put_cup_in_dishwasher", "breakfast", "action")]
        self.assertEqual(mr.story_problems(story), [])

    def test_contradictions_are_reported(self):
        cup = [seg("07:00:00", "07:00:04", "get_cup", "breakfast", "approach"),
               seg("07:00:04", "07:00:08", "put_cup_next_to_self", "breakfast", "action")]
        stories = {
            "drinks after the cup went to the dishwasher": cup + [
                seg("07:00:08", "07:00:12", "pick_up_empty_cup", "breakfast", "approach"),
                seg("07:00:12", "07:00:16", "carry_cup_to_kitchen", "breakfast", "approach"),
                seg("07:00:16", "07:00:22", "put_cup_in_dishwasher", "breakfast", "action"),
                seg("07:00:22", "07:00:28", "drink_water", "breakfast")],
            "drinks from an emptied cup": cup + [
                seg("07:00:08", "07:00:12", "finish_drinking", "breakfast", "candidate"),
                seg("07:00:12", "07:00:18", "drink_water", "breakfast")],
            "eats after finishing the meal": [
                seg("18:30:00", "18:30:04", "sit_at_table", "dinner"),
                seg("18:30:04", "18:30:08", "pick_up_spoon", "dinner"),
                seg("18:30:08", "18:30:30", "eat_dinner", "dinner"),
                seg("18:30:30", "18:30:34", "finish_meal", "dinner", "candidate"),
                seg("18:30:34", "18:30:50", "eat_dinner", "dinner")],
            "puts down a spoon it does not hold": [
                seg("18:30:00", "18:30:04", "sit_at_table", "dinner"),
                seg("18:30:04", "18:30:08", "put_down_spoon", "dinner", "candidate")],
            "reads in bed with the lamp off": [seg("22:00:00", "22:05:00", "read_in_bed", "bedtime")],
            "the guest finishes a can that was never opened": [
                seg("17:00:00", "17:00:10", "guest_arrives", "evening_rest"),
                seg("17:00:10", "17:00:14", "guest_finishes_can", "evening_rest", "candidate")],
            "the guest drinks from a finished can": [
                seg("17:00:00", "17:00:10", "guest_arrives", "evening_rest"),
                seg("17:00:10", "17:00:14", "guest_opens_can", "evening_rest"),
                seg("17:00:14", "17:00:18", "guest_finishes_can", "evening_rest", "candidate"),
                seg("17:00:18", "17:00:24", "guest_drinks_can", "evening_rest")],
            "drinks from a can that was never brought": [seg("17:00:00", "17:00:06", "drink_from_can", "evening_rest")],
            "sits up in bed after getting out of it": [
                seg("07:00:00", "07:00:04", "get_out_of_bed", "morning"),
                seg("07:00:04", "07:00:08", "sit_up_in_bed", "morning")],
            "takes food out of a microwave that was never started": [
                seg("18:30:00", "18:30:04", "take_food_from_microwave", "dinner")],
            "zips a bag that was not packed": [seg("12:00:00", "12:00:04", "zip_bag", "going_out")],
        }
        for name, story in stories.items():
            self.assertTrue(mr.story_problems(story), name)

    def test_the_light_may_change_while_the_person_is_out_of_view(self):
        story = [seg("07:00:00", "07:00:04", "turn_on_room_light", "morning"),
                 seg("07:00:04", "12:00:00", "unseen", "away", "unseen"),
                 seg("12:00:00", "12:00:04", "turn_on_room_light", "evening_rest")]
        self.assertEqual(mr.story_problems(story), [])


class WeekShapeTests(unittest.TestCase):
    def test_five_weekdays_each_from_seven_to_eleven_without_gaps(self):
        self.assertEqual(sorted(WEEK), list(DAYS))
        for day in DAYS:
            segments = WEEK[day]
            self.assertEqual(segments[0]["start"], t("07:00:00"))
            self.assertEqual(segments[-1]["end"], t("23:00:00"))
            for before, after in zip(segments, segments[1:]):
                self.assertEqual(before["end"], after["start"], f"day {day}")
            for segment in segments:
                self.assertGreater(segment["end"], segment["start"])
                self.assertEqual((segment["start"] - t("07:00:00")) % 2, 0)

    def test_neighbouring_segments_never_repeat_an_event(self):
        for day in DAYS:
            for before, after in zip(WEEK[day], WEEK[day][1:]):
                self.assertNotEqual(before["event"], after["event"], f"day {day} at {after['start']}")

    def test_every_action_is_preceded_by_an_approach_step(self):
        actions = 0
        for day in DAYS:
            segments = WEEK[day]
            for index, segment in enumerate(segments):
                if segment["role"] == "action":
                    actions += 1
                    self.assertEqual(segments[index - 1]["role"], "approach", f"day {day} {segment}")
        self.assertGreater(actions, 0)

    def test_no_day_contradicts_itself(self):
        for day in DAYS:
            self.assertEqual(mr.story_problems(WEEK[day]), [], f"day {day}")

    def test_the_day_does_not_run_like_clockwork(self):
        breakfasts = {occurrences(day, "sit_at_table", "breakfast")[0]["start"] for day in DAYS}
        dinners = {occurrences(day, "sit_at_table", "dinner")[0]["start"] for day in DAYS}
        self.assertGreaterEqual(len(breakfasts), 4)
        self.assertGreaterEqual(len(dinners), 4)


class RealismTests(unittest.TestCase):
    def test_spoon_and_chopsticks_go_down_many_times_at_every_dinner(self):
        for day in DAYS:
            spoon = occurrences(day, "put_down_spoon", "dinner")
            chopsticks = occurrences(day, "put_down_chopsticks", "dinner")
            self.assertGreaterEqual(len(spoon), 8, day)
            self.assertGreaterEqual(len(chopsticks), 4, day)

    def test_phone_is_checked_35_to_55_times_a_day(self):
        for day in DAYS:
            count = len(occurrences(day, "look_at_phone"))
            self.assertTrue(35 <= count <= 55, (day, count))

    def test_a_drink_is_brought_seven_to_nine_times_a_day(self):
        for day in DAYS:
            count = len(task_starts(day, 0))
            self.assertTrue(7 <= count <= 9, (day, count))

    def test_meals_take_a_realistic_time(self):
        for day in DAYS:
            sat = occurrences(day, "sit_at_table", "breakfast")[0]["start"]
            done = occurrences(day, "finish_breakfast", "breakfast")[0]["start"]
            self.assertTrue(10 * 60 <= done - sat <= 22 * 60, (day, done - sat))
            sat = occurrences(day, "sit_at_table", "dinner")[0]["start"]
            done = occurrences(day, "finish_meal", "dinner")[0]["start"]
            self.assertTrue(16 * 60 <= done - sat <= 32 * 60, (day, done - sat))

    # 2026-11-16: read as a person's day, the filler between planned events was not human.
    def test_small_movements_come_now_and_then_and_never_again_and_again(self):
        for day in DAYS:                         # a stretch came 14 to 21 times, 6 to 11 of them within 25 minutes
            self.assertLessEqual(len(occurrences(day, "stretch")), 7, day)
            for event, gap in mr.RARE.items():
                starts = [s["start"] for s in occurrences(day, event)]
                for earlier, later in zip(starts, starts[1:]):
                    self.assertGreaterEqual(later - earlier, gap, (day, event, mr.hms(later)))
        for event in mr.RARE:                    # but they do happen: a real person does not sit still
            self.assertTrue(any(occurrences(day, event) for day in DAYS), event)

    def test_the_person_is_seen_walking_out_and_coming_back(self):
        for day in DAYS:                         # the person used to vanish and reappear between two lines
            segments = WEEK[day]
            for index, s in enumerate(segments):
                if s["event"] == "unseen":
                    self.assertIn(segments[index - 1]["event"], ("leave_room", "leave_home", "put_on_bag"),
                                  (day, mr.hms(s["start"])))
                    self.assertIn(segments[index + 1]["event"], ("enter_room", "come_home"), (day, mr.hms(s["end"])))

    def test_a_drink_for_the_desk_or_sofa_is_fetched_by_walking_to_the_kitchen_and_back(self):
        for day in DAYS:                         # a cup used to appear 8 seconds after the person sat typing
            for index, s in enumerate(WEEK[day]):
                if s["event"] == "put_cup_next_to_self" and s["state"] in ("study", "evening_rest"):
                    trip = [step["event"] for step in WEEK[day][index - 4:index]]
                    self.assertEqual(trip[:2] + trip[3:], ["stand_up", "walk_to_kitchen", "carry_cup_back"], day)
                    self.assertIn(trip[2], ("get_cup", "fill_cup_at_purifier"), day)
                    self.assertGreaterEqual(s["start"] - WEEK[day][index - 4]["start"], 16, day)

    def test_steps_done_once_happen_once_and_in_order(self):
        for day in DAYS:                         # the bag used to be zipped 17 times while it was being packed
            order = [s["event"] for s in WEEK[day]]
            for event in ("sit_up_in_bed", "get_out_of_bed", "put_food_in_microwave", "take_food_from_microwave",
                          "zip_bag"):
                self.assertEqual(order.count(event), 1, (day, event))
            self.assertLess(order.index("sit_up_in_bed"), order.index("get_out_of_bed"), day)
            self.assertLess(order.index("put_food_in_microwave"), order.index("take_food_from_microwave"), day)
            self.assertEqual(order[order.index("zip_bag") - 1], "pack_bag", day)

    def test_a_can_is_drunk_as_soon_as_it_is_brought_and_finished_within_the_hour(self):
        for day in DAYS:                         # on day 2 the first sip came 167 minutes after the can
            cans = occurrences(day, "put_can_next_to_self")
            sips = occurrences(day, "drink_from_can")
            if not cans:
                self.assertEqual(sips, [], day)
                continue
            after = [s["start"] - cans[0]["end"] for s in sips]
            self.assertEqual(after[0], 0, day)
            self.assertGreaterEqual(len(after), 4, day)
            self.assertLessEqual(after[-1], 60 * 60, day)

    def test_a_drink_brought_to_the_desk_or_sofa_is_drunk_right_away(self):
        for day in DAYS:                         # a cup used to be refilled 38 minutes after an untouched refill
            for index, s in enumerate(WEEK[day]):
                if s["event"] == "put_cup_next_to_self" and s["state"] in ("study", "evening_rest"):
                    self.assertEqual(WEEK[day][index + 1]["event"], "drink_water", (day, mr.hms(s["start"])))

    def test_pockets_are_checked_once_before_the_bag_goes_on(self):
        for day in DAYS:                         # they were checked again and again after the bag was on
            checks = occurrences(day, "check_pockets")
            self.assertEqual(len(checks), 1, day)
            self.assertLess(checks[0]["start"], occurrences(day, "put_on_bag")[0]["start"], day)


class PlantedCaseTests(unittest.TestCase):
    def test_cup_goes_in_dishwasher_after_finishing_a_drink_every_breakfast(self):
        for day in DAYS:
            drinks = occurrences(day, "finish_drinking", "breakfast")
            self.assertEqual(len(drinks), 1, day)
            self.assertTrue(followed(day, drinks[0], "put_cup_in_dishwasher"), day)

    def test_finishing_a_drink_while_studying_leaves_the_cup(self):
        for day in DAYS:
            drinks = occurrences(day, "finish_drinking", "study")
            self.assertTrue(drinks, day)
            for drink in drinks:
                self.assertFalse(followed(day, drink, "put_cup_in_dishwasher"), day)

    def test_breakfast_phone_checks_lie_near_the_cup_at_most_once(self):
        for day in DAYS:
            phones = occurrences(day, "look_at_phone", "breakfast")
            self.assertTrue(2 <= len(phones) <= 4, (day, len(phones)))
            self.assertLessEqual(sum(followed(day, p, "put_cup_in_dishwasher") for p in phones), 1, day)

    def test_lamp_follows_the_book_except_on_day_two(self):
        for day in DAYS:
            books = occurrences(day, "close_book", "bedtime")
            self.assertEqual(len(books), 1, day)
            self.assertEqual(followed(day, books[0], "turn_off_bedside_lamp"), day != 2, day)
            self.assertEqual(len(occurrences(day, "turn_off_bedside_lamp")), 1, day)

    def test_bowl_follows_finishing_and_wiping_the_mouth_every_dinner(self):
        for day in DAYS:
            for candidate in ("finish_meal", "wipe_mouth"):
                found = occurrences(day, candidate, "dinner")
                self.assertEqual(len(found), 1, (day, candidate))
                self.assertTrue(followed(day, found[0], "put_bowl_in_dishwasher"), (day, candidate))

    def test_call_brings_a_can_only_on_days_one_and_two(self):
        for day in DAYS:
            calls = occurrences(day, "phone_rings", "evening_rest")
            self.assertEqual(len(calls), 1, day)
            self.assertEqual(followed(day, calls[0], "put_can_next_to_self"), day in (1, 2), day)
            self.assertEqual(len(occurrences(day, "put_can_next_to_self")), 1 if day in (1, 2) else 0, day)

    def test_book_is_stored_after_closing_the_laptop_only_on_odd_days(self):
        for day in DAYS:
            closes = occurrences(day, "close_laptop", "study")
            self.assertEqual(len(closes), 1, day)
            self.assertEqual(followed(day, closes[0], "put_book_in_storage"), day % 2 == 1, day)

    def test_guest_comes_and_cans_are_stored_three_times_only_on_day_four(self):
        cans = occurrences(4, "guest_finishes_can", "evening_rest")
        self.assertEqual(len(cans), 3)
        for can in cans:
            self.assertTrue(followed(4, can, "put_can_in_storage"))
        # The guest opens each can before finishing it (2026-11-16: a can used to be finished out of nowhere).
        opened = [s["start"] for s in occurrences(4, "guest_opens_can")]
        self.assertEqual(len(opened), 3)
        for start, can in zip(opened, cans):
            self.assertLess(start, can["start"])
        for day in (1, 2, 3, 5):
            self.assertEqual(occurrences(day, "guest_arrives"), [], day)
            self.assertEqual(occurrences(day, "put_can_in_storage"), [], day)

    def test_book_is_brought_after_vacuuming_only_on_day_five(self):
        done = occurrences(5, "finish_vacuuming", "evening_rest")
        self.assertEqual(len(done), 1)
        self.assertTrue(followed(5, done[0], "put_book_next_to_self"))
        for day in DAYS:
            self.assertEqual(len(occurrences(day, "put_book_next_to_self")), 1 if day == 5 else 0, day)

    def test_room_light_is_unseen_on_days_three_and_five(self):
        for day in DAYS:
            bags = occurrences(day, "put_on_bag", "going_out")
            self.assertEqual(len(bags), 1, day)
            bag, segments = bags[0], WEEK[day]
            after = segments[segments.index(bag) + 1]
            if day in (3, 5):
                self.assertEqual(after["event"], "unseen", day)
                self.assertFalse(followed(day, bag, "turn_off_room_light"), day)
            else:
                self.assertTrue(followed(day, bag, "turn_off_room_light"), day)

    def test_cup_is_fetched_after_sitting_at_desk_except_day_three(self):
        for day in DAYS:
            sits = occurrences(day, "sit_at_desk", "study")
            self.assertEqual(len(sits), 1, day)
            self.assertEqual(followed(day, sits[0], "put_cup_next_to_self"), day != 3, day)

    def test_every_planted_candidate_passes_on_exactly_the_expected_nights(self):
        for rule in mr.RULES:
            for candidate in rule["candidates"]:
                passed = [night for night in DAYS if check(rule, candidate["event"], night)["passed"]]
                self.assertEqual(passed, list(candidate["expected_nights"]), (rule["id"], candidate["event"]))

    def test_desk_cup_base_rate_blocks_night_two_but_not_night_five(self):
        rule = next(rule for rule in mr.RULES if rule["id"] == "R8")
        night_two, night_five = check(rule, "sit_at_desk", 2), check(rule, "sit_at_desk", 5)
        self.assertGreater(night_two["p0"], 0.0317)
        self.assertLess(night_five["p0"], 0.125)


class AnswerKeyTests(unittest.TestCase):
    def test_rules_use_real_tasks_and_one_to_three_candidates(self):
        self.assertTrue(mr.RULES)
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
