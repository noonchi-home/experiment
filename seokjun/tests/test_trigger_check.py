"""Trigger candidate checks with small hand-worked examples (손으로 답을 아는 작은 예시).

Adopt(c -> a) iff k/n >= 0.75 and P(X >= k) < 0.001 with X ~ Binomial(n, p0),
p0 = max(other-time rate, 0.01). Times are seconds since midnight.
"""

from copy import deepcopy
import math
import unittest

from pam.contracts import validate_memory
from pam.trigger_check import binomial_tail, check_candidate, predictor_fsm


def t(text):
    hours, minutes, seconds = map(int, text.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def day(candidate=(), action=(), unseen=(), start="07:00:00", end="08:00:00"):
    return {"start": t(start), "end": t(end),
            "candidate": [t(moment) for moment in candidate],
            "action": [t(moment) for moment in action],
            "unseen": [(t(low), t(high)) for low, high in unseen]}


FOLLOWED = day(["07:10:00"], ["07:13:00"])
MISSED = day(["07:10:00"], [])


class BinomialTailTests(unittest.TestCase):
    def test_known_tail_probabilities(self):
        worked = [((2, 2, 0.01), 1e-4), ((6, 7, 0.01), 6.94e-12), ((4, 5, 0.2), 0.00672),
                  ((9, 10, 0.8), 0.3758096384), ((0, 3, 0.5), 1.0)]
        for (k, n, p), want in worked:
            self.assertTrue(math.isclose(binomial_tail(k, n, p), want, rel_tol=1e-6), (k, n, p))


class CheckCandidateTests(unittest.TestCase):
    def test_two_followed_days_pass_with_the_floor(self):
        result = check_candidate([FOLLOWED, FOLLOWED])
        self.assertEqual((result["n"], result["k"], result["unknown"]), (2, 2, 0))
        self.assertEqual(result["base_rate"], 0.0)
        self.assertEqual(result["p0"], 0.01)
        self.assertTrue(math.isclose(result["p_value"], 1e-4, rel_tol=1e-9))
        self.assertTrue(result["passed"])

    def test_one_day_is_not_enough(self):
        result = check_candidate([FOLLOWED])
        self.assertEqual(result["rate"], 1.0)
        self.assertTrue(math.isclose(result["p_value"], 0.01, rel_tol=1e-9))
        self.assertFalse(result["passed"])

    def test_five_minutes_counts_and_two_seconds_later_does_not(self):
        self.assertEqual(check_candidate([day(["07:10:00"], ["07:15:00"])])["k"], 1)
        self.assertEqual(check_candidate([day(["07:10:00"], ["07:15:02"])])["k"], 0)

    def test_action_before_the_candidate_does_not_count(self):
        result = check_candidate([day(["07:10:00"], ["07:09:00"])])
        self.assertEqual((result["n"], result["k"]), (1, 0))

    def test_unseen_window_without_action_is_left_out(self):
        gone = day(["12:30:00"], [], [("12:30:04", "17:00:00")], start="12:00:00", end="17:00:00")
        seen = day(["12:30:00"], ["12:32:00"], [("12:32:06", "17:00:00")], start="12:00:00", end="17:00:00")
        result = check_candidate([gone, seen])
        self.assertEqual((result["n"], result["k"], result["unknown"]), (1, 1, 1))

    def test_base_rate_comes_from_other_slots(self):
        # 12 slots; the two touching 07:00-07:05 are the candidate's; 2 of the other 10 hold an action.
        result = check_candidate([day(["07:00:00"], ["07:03:00", "07:21:00", "07:41:00"])])
        self.assertEqual((result["n"], result["k"]), (1, 1))
        self.assertTrue(math.isclose(result["base_rate"], 0.2))
        self.assertTrue(math.isclose(result["p0"], 0.2))
        self.assertTrue(math.isclose(result["p_value"], 0.2))
        self.assertFalse(result["passed"])

    def test_unseen_slots_are_left_out_of_the_base_rate(self):
        # Other slots left: 07:10, 07:15, 07:20, 07:25 (07:30-08:00 unseen); one holds an action.
        result = check_candidate([day(["07:00:00"], ["07:03:00", "07:12:00"], [("07:30:00", "08:00:00")])])
        self.assertTrue(math.isclose(result["base_rate"], 0.25))

    def test_seventy_five_percent_passes_and_two_out_of_three_does_not(self):
        four = check_candidate([FOLLOWED] * 3 + [MISSED])
        self.assertEqual(four["rate"], 0.75)
        self.assertTrue(four["passed"])
        three = check_candidate([FOLLOWED] * 2 + [MISSED])
        self.assertTrue(math.isclose(three["rate"], 2 / 3))
        self.assertFalse(three["passed"])

    def test_frequent_action_passes_only_on_night_seven(self):
        # Every day 2 of the 10 other slots hold the action (base 0.2); day 3 is not followed.
        week = [day(["07:00:00"], ([] if number == 3 else ["07:03:00"]) + ["07:21:00", "07:41:00"])
                for number in range(1, 8)]
        night6, night7 = check_candidate(week[:6]), check_candidate(week)
        self.assertTrue(math.isclose(night6["p_value"], 0.0016, rel_tol=1e-6))
        self.assertFalse(night6["passed"])
        self.assertTrue(math.isclose(night7["p_value"], 0.0003712, rel_tol=1e-6))
        self.assertTrue(night7["passed"])

    def test_only_the_last_candidate_before_the_action_counts(self):
        # Spoon down three times, then the bowl: only the last one is credited.
        result = check_candidate([day(["07:10:00", "07:11:00", "07:12:00"], ["07:14:00"])])
        self.assertEqual((result["n"], result["k"]), (3, 1))
        self.assertFalse(result["passed"])

    def test_repeats_each_followed_by_their_own_action_all_count(self):
        result = check_candidate([day(["07:10:00", "07:20:00", "07:30:00"], ["07:12:00", "07:22:00", "07:32:00"])])
        self.assertEqual((result["n"], result["k"]), (3, 3))

    def test_a_seen_repeat_settles_the_earlier_one_as_not_followed(self):
        # 12:30 is cut short by the repeat at 12:31 (both seen, no action between);
        # 12:31 then runs into the unseen stretch, so its outcome is unknown.
        repeat = day(["12:30:00", "12:31:00"], [], [("12:31:10", "17:00:00")], start="12:00:00", end="17:00:00")
        result = check_candidate([repeat])
        self.assertEqual((result["n"], result["k"], result["unknown"]), (1, 0, 1))

    def test_a_one_minute_window_counts_only_the_minute_after(self):
        # Action 90 s after the candidate: followed with 5 minutes, not with 1 minute.
        late = day(["07:10:00"], ["07:11:30"])
        self.assertEqual(check_candidate([late])["k"], 1)
        self.assertEqual(check_candidate([late], window=60)["k"], 0)
        self.assertEqual(check_candidate([day(["07:10:00"], ["07:10:59"])], window=60)["k"], 1)

    def test_a_one_minute_window_uses_one_minute_slots_for_the_base_rate(self):
        # 07:00-07:10 has 10 one-minute slots; the candidate at 07:00 touches 07:00 and 07:01.
        # Of the other 8, the slot 07:05 holds an action.
        result = check_candidate([day(["07:00:00"], ["07:00:30", "07:05:10"], end="07:10:00")], window=60)
        self.assertTrue(math.isclose(result["base_rate"], 1 / 8))

    def test_no_occurrence_never_passes(self):
        result = check_candidate([day([], ["07:13:00"])])
        self.assertEqual(result["n"], 0)
        self.assertFalse(result["passed"])


class PredictorFsmTests(unittest.TestCase):
    REFLECTED = {
        "initial_state": "breakfast",
        "states": [
            {"id": "breakfast", "description": "Person eats breakfast.",
             "rules": [{"triggers": ["Person finishes the water", "Person looks at the phone"],
                        "action": "Pick up the cup and place it in the dishwasher."},
                       {"triggers": ["Person sits down"],
                        "action": "Pick up the cup and place it next to the person."}],
             "next": [{"to": "study", "on": "Person sits at the desk"}]},
            {"id": "study", "description": "Person studies.",
             "rules": [{"triggers": ["Person closes the laptop", "Person stands up"],
                        "action": "Pick up the book and place it in the designated storage area."}],
             "next": []},
        ],
    }
    PASSED = {
        ("breakfast", "Pick up the cup and place it in the dishwasher.", "Person finishes the water"),
        ("study", "Pick up the book and place it in the designated storage area.", "Person closes the laptop"),
        ("study", "Pick up the book and place it in the designated storage area.", "Person stands up"),
    }

    def test_only_passing_candidates_are_joined_with_or(self):
        built = predictor_fsm(self.REFLECTED, self.PASSED)
        self.assertEqual(built, {
            "initial_state": "breakfast",
            "states": [
                {"id": "breakfast", "description": "Person eats breakfast.",
                 "rules": [{"trigger": "Person finishes the water",
                            "action": "Pick up the cup and place it in the dishwasher."}],
                 "next": [{"to": "study", "on": "Person sits at the desk"}]},
                {"id": "study", "description": "Person studies.",
                 "rules": [{"trigger": "Person closes the laptop or Person stands up",
                            "action": "Pick up the book and place it in the designated storage area."}],
                 "next": []},
            ],
        })
        validate_memory(built, "fsm")

    def test_reflector_fsm_is_left_unchanged(self):
        before = deepcopy(self.REFLECTED)
        predictor_fsm(self.REFLECTED, self.PASSED)
        self.assertEqual(self.REFLECTED, before)


if __name__ == "__main__":
    unittest.main()
