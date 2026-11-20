"""Night scoring, matching step: candidates to answer-key events (no live calls).

Run from this folder: python -m unittest test_night_scoring
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import night_scoring as ns
from pam.contracts import ContractError

CUP_AWAY = "Pick up the cup and place it in the dishwasher."
CUP_NEAR = "Pick up the cup and place it next to the person."
KEY = {"events": {
    "finish_drinking": {"ko": "물을 다 마신다", "task": None,
                        "phrases": ["The person drinks the last of the water and puts the cup down."]},
    "look_at_phone": {"ko": "휴대폰을 본다", "task": None, "phrases": ["The person looks at their phone."]},
    "sit_at_desk": {"ko": "책상에 앉는다", "task": None, "phrases": ["The person sits down at the desk."]},
}}
NIGHT1 = {"initial_state": "breakfast", "states": [
    {"id": "breakfast", "description": "Person eats breakfast.",
     "rules": [{"triggers": ["Person finishes the water", "Person looks at the phone"], "action": CUP_AWAY}],
     "next": [{"to": "study", "on": "Person sits at the desk"}]},
    {"id": "study", "description": "Person studies at the desk.",
     "rules": [{"triggers": ["Person finishes the water"], "action": CUP_AWAY}], "next": []}]}
NIGHT2 = {"initial_state": "breakfast", "states": [
    NIGHT1["states"][0],
    {"id": "study", "description": "Person studies at the desk.",
     "rules": [{"triggers": ["Person finishes the water"], "action": CUP_AWAY},
               {"triggers": ["Person sits down at the desk"], "action": CUP_NEAR}], "next": []}]}
ANSWERS = {"Person finishes the water": "finish_drinking", "Person looks at the phone": "look_at_phone",
           "Person sits down at the desk": None}


class FakeMatcher:
    """Answers like the LLM would, from ANSWERS; remembers every bundle it was given."""

    def __init__(self, answers=None):
        self.answers = ANSWERS if answers is None else answers
        self.bundles = []

    def __call__(self, bundle, work):
        self.bundles.append(bundle)
        return {"matches": [{"index": number, "event": self.answers[text]}
                            for number, text in enumerate(bundle["asked_candidates"], start=1)]}


def refuse(bundle, work):
    raise AssertionError("The matcher was asked although nothing new had to be matched.")


class MatchTableTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run_dir = Path(temp.name)

    def _night(self, night, memory):
        folder = self.run_dir / f"night-{night}"
        folder.mkdir()
        (folder / "reflector_fsm.json").write_text(json.dumps(memory), encoding="utf-8")

    def _saved(self, night):
        path = self.run_dir / "scoring" / f"matches-night-{night}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_first_night_asks_each_candidate_once_and_saves_the_table(self):
        self._night(1, NIGHT1)
        matcher = FakeMatcher()
        table = ns.match_table(1, self.run_dir, KEY, matcher)
        self.assertEqual(table, {"Person finishes the water": "finish_drinking",
                                 "Person looks at the phone": "look_at_phone"})
        self.assertEqual([b["asked_candidates"] for b in matcher.bundles],
                         [["Person finishes the water", "Person looks at the phone"]])
        self.assertEqual(matcher.bundles[0]["event_ids"], ["finish_drinking", "look_at_phone", "sit_at_desk"])
        self.assertIn("sit_at_desk: The person sits down at the desk.",
                      matcher.bundles[0]["messages"][1]["content"][0]["text"])
        self.assertEqual(self._saved(1), {"night": 1, "matches": [
            {"candidate": "Person finishes the water", "event": "finish_drinking"},
            {"candidate": "Person looks at the phone", "event": "look_at_phone"}]})

    def test_later_night_asks_only_new_candidates(self):
        self._night(1, NIGHT1)
        self._night(2, NIGHT2)
        matcher = FakeMatcher()
        table = ns.match_table(2, self.run_dir, KEY, matcher)
        self.assertEqual([b["asked_candidates"] for b in matcher.bundles],
                         [["Person finishes the water", "Person looks at the phone"],
                          ["Person sits down at the desk"]])
        self.assertIsNone(table["Person sits down at the desk"])
        self.assertEqual(self._saved(2), {"night": 2, "matches": [
            {"candidate": "Person sits down at the desk", "event": None}]})

    def test_saved_night_is_read_back_without_asking_again(self):
        self._night(1, NIGHT1)
        first = ns.match_table(1, self.run_dir, KEY, FakeMatcher())
        self.assertEqual(ns.match_table(1, self.run_dir, KEY, refuse), first)

    def test_night_without_new_candidates_is_saved_empty_without_asking(self):
        self._night(1, NIGHT1)
        self._night(2, NIGHT1)
        ns.match_table(1, self.run_dir, KEY, FakeMatcher())
        ns.match_table(2, self.run_dir, KEY, refuse)
        self.assertEqual(self._saved(2), {"night": 2, "matches": []})

    def test_answer_with_an_unlisted_event_is_refused_and_nothing_is_saved(self):
        self._night(1, NIGHT1)
        wrong = FakeMatcher({**ANSWERS, "Person finishes the water": "finish_the_water"})
        with self.assertRaises(ContractError):
            ns.match_table(1, self.run_dir, KEY, wrong)
        self.assertFalse((self.run_dir / "scoring" / "matches-night-1.json").exists())


def segment(start, end, event, state):
    return {"start": start, "end": end, "event": event, "state": state, "role": "background", "case": None}


DAY = [segment("07:30:00", "07:40:00", "eat_breakfast", "breakfast"),
       segment("07:40:00", "07:40:04", "finish_drinking", "breakfast"),
       segment("07:40:04", "07:41:00", "look_at_phone", "breakfast"),
       segment("07:41:00", "07:43:00", "eat_breakfast", "breakfast"),
       segment("07:43:00", "07:43:04", "pick_up_empty_cup", "breakfast"),
       segment("07:43:04", "07:43:10", "put_cup_in_dishwasher", "breakfast"),
       segment("07:43:10", "10:00:00", "type_on_laptop", "study"),
       segment("10:00:00", "10:00:04", "finish_drinking", "study"),
       segment("10:00:04", "11:00:00", "type_on_laptop", "study")]
SCORE_KEY = {
    "line_seconds": 2, "tasks": [CUP_NEAR, CUP_AWAY],
    "events": {name: {"ko": name, "task": 1 if name == "put_cup_in_dishwasher" else None, "phrases": [name]}
               for name in ("eat_breakfast", "finish_drinking", "look_at_phone", "pick_up_empty_cup",
                            "put_cup_in_dishwasher", "type_on_laptop")},
    "rules": [{"id": "R1", "state": "breakfast", "task": 1,
               "candidates": [{"event": "finish_drinking", "expected_nights": [2]},
                              {"event": "look_at_phone", "expected_nights": []}],
               "forbidden": ["pick_up_empty_cup"]}],
    "days": [{"day": 1, "segments": DAY}, {"day": 2, "segments": DAY}],
}
WATER, CUP_UP = "Person finishes the water", "Person picks up the empty cup"
SCORE_MATCHES = {WATER: "finish_drinking", CUP_UP: "pick_up_empty_cup"}


def result(state, candidate, n, k, passed, action=CUP_AWAY):
    return {"state": state, "action": action, "candidate": candidate, "n": n, "k": k, "unknown": 0,
            "rate": k / n if n else 0.0, "base_rate": 0.0, "p0": 0.01, "p_value": 0.5, "passed": passed}


class CompareNightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run_dir = Path(temp.name)

    def _write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def _night(self, night, results, marks):
        folder = self.run_dir / f"night-{night}"
        self._write(folder / "check_results.json", results)
        self._write(folder / "marks" / f"day{night}.json", {"day": night, **marks})

    def _two_nights(self, meal_water=("07:40:00",)):
        for night in (1, 2):
            self._night(night, [result("morning_meal", WATER, night, night, night == 2),
                                result("morning_meal", CUP_UP, night, night, night == 2),
                                result("desk_work", WATER, night, 0, False)],
                        {"candidates": [{"state": "morning_meal", "candidate": WATER, "times": list(meal_water)},
                                        {"state": "morning_meal", "candidate": CUP_UP, "times": ["07:43:00"]},
                                        {"state": "desk_work", "candidate": WATER, "times": ["10:00:00"]}],
                         "actions": [{"action": CUP_AWAY, "times": ["07:43:04"]}], "unseen": []})

    def _rows(self):
        return {(row["state"], row["candidate"]): row
                for row in ns.compare_night(2, self.run_dir, SCORE_KEY, SCORE_MATCHES)}

    def test_each_candidate_is_compared_with_the_expected_night_in_the_state_of_its_found_times(self):
        self._two_nights()
        row = self._rows()[("morning_meal", WATER)]
        self.assertEqual((row["event"], row["answer_state"], row["kind"]), ("finish_drinking", "breakfast", "심어 둔 후보"))
        self.assertEqual((row["expected"], row["passed"], row["verdict"]), (True, True, "같음"))
        self.assertEqual(row["times"], {"right": 2, "missed": 0, "wrong": 0})

    def test_part_of_the_action_and_the_same_event_in_another_state_must_not_pass(self):
        self._two_nights()
        rows = self._rows()
        self.assertEqual((rows[("morning_meal", CUP_UP)]["kind"], rows[("morning_meal", CUP_UP)]["verdict"]),
                         ("행동의 일부", "다름"))
        self.assertEqual((rows[("desk_work", WATER)]["kind"], rows[("desk_work", WATER)]["answer_state"],
                          rows[("desk_work", WATER)]["verdict"]), ("다른 상태", "study", "같음"))

    def test_a_planted_candidate_never_proposed_is_listed(self):
        self._two_nights()
        missing = [row for row in ns.compare_night(2, self.run_dir, SCORE_KEY, SCORE_MATCHES)
                   if row["kind"] == "후보로 안 나옴"]
        self.assertEqual([(row["answer_state"], row["event"], row["verdict"]) for row in missing],
                         [("breakfast", "look_at_phone", "같음")])

    def test_a_proposed_candidate_without_found_times_uses_its_planted_state_and_is_not_missing(self):
        self._two_nights()
        phone, book = "Person looks at the phone", "Person closes the book"
        for night in (1, 2):
            path = self.run_dir / f"night-{night}" / "check_results.json"
            results = json.loads(path.read_text(encoding="utf-8"))
            results += [result("morning_meal", phone, 0, 0, False), result("morning_meal", book, 0, 0, False, CUP_NEAR)]
            path.write_text(json.dumps(results), encoding="utf-8")
        key = {**SCORE_KEY,
               "events": {**SCORE_KEY["events"], "close_book": {"ko": "close_book", "task": None, "phrases": ["x"]}},
               "rules": [*SCORE_KEY["rules"], {"id": "R2", "state": "breakfast", "task": 0, "forbidden": [],
                                               "candidates": [{"event": "close_book", "expected_nights": []}]}]}
        rows = ns.compare_night(2, self.run_dir, key, {**SCORE_MATCHES, phone: "look_at_phone", book: "close_book"})
        by_candidate = {row["candidate"]: row for row in rows}
        self.assertEqual((by_candidate[phone]["kind"], by_candidate[phone]["answer_state"],
                          by_candidate[phone]["verdict"], by_candidate[phone]["times"]["missed"]),
                         ("시각 못 찾음", "breakfast", "같음", 2))
        self.assertEqual((by_candidate[book]["kind"], by_candidate[book]["verdict"]), ("아직 안 일어남", "같음"))
        self.assertEqual([row for row in rows if row["kind"] == "후보로 안 나옴"], [])

    def test_times_spread_over_two_states_get_no_verdict(self):
        self._two_nights(meal_water=("07:40:00", "10:00:00"))
        row = self._rows()[("morning_meal", WATER)]
        self.assertEqual((row["kind"], row["answer_state"], row["verdict"]), ("상태 섞임", ["breakfast", "study"], None))

    def test_found_times_are_checked_against_the_answer_key(self):
        self._two_nights(meal_water=("07:40:10", "09:00:00"))
        row = self._rows()[("morning_meal", WATER)]
        self.assertEqual(row["kind"], "상태 섞임")
        self._two_nights(meal_water=("07:40:12",))
        self.assertEqual(self._rows()[("morning_meal", WATER)]["times"], {"right": 2, "missed": 0, "wrong": 0})
        self._two_nights(meal_water=("07:39:40", "07:40:02"))
        self.assertEqual(self._rows()[("morning_meal", WATER)]["times"], {"right": 2, "missed": 0, "wrong": 2})


PREV = {"initial_state": "breakfast_time", "states": [
    {"id": "breakfast_time", "description": "Breakfast.",
     "rules": [{"triggers": [WATER, "Person looks at the phone", "Person stretches"], "action": CUP_AWAY},
               {"triggers": ["Person sits down"], "action": CUP_NEAR}], "next": []},
    {"id": "evening", "description": "Evening.",
     "rules": [{"triggers": ["Person closes the book"], "action": CUP_NEAR}], "next": []}]}
CUR = {"initial_state": "breakfast_time", "states": [
    {"id": "breakfast_time", "description": "Breakfast at the table.",
     "rules": [{"triggers": ["Person puts the plate in the sink"], "action": CUP_AWAY}], "next": []},
    {"id": "night_time", "description": "Evening.",
     "rules": [{"triggers": ["Person closes the book"], "action": CUP_NEAR}], "next": []}]}
PREV_RESULTS = [result("breakfast_time", WATER, 2, 2, True),
                result("breakfast_time", "Person looks at the phone", 3, 1, False),
                result("breakfast_time", "Person stretches", 1, 0, False),
                result("breakfast_time", "Person sits down", 1, 1, False, action=CUP_NEAR),
                result("evening", "Person closes the book", 1, 1, False, action=CUP_NEAR)]


class ChangeTests(unittest.TestCase):
    def test_every_change_from_the_night_before_is_listed(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            for night, memory in ((1, PREV), (2, CUR)):
                (run_dir / f"night-{night}").mkdir()
                (run_dir / f"night-{night}" / "reflector_fsm.json").write_text(json.dumps(memory), encoding="utf-8")
            (run_dir / "night-1" / "check_results.json").write_text(json.dumps(PREV_RESULTS), encoding="utf-8")
            self.assertEqual(ns.changes(1, run_dir), [])
            found = {(row["kind"], row.get("state"), row.get("candidate"), row.get("flag"))
                     for row in ns.changes(2, run_dir)}
        self.assertEqual(found, {
            ("사라진 상태", "evening", None, None),
            ("새 상태", "night_time", None, None),
            ("설명 바뀜", "breakfast_time", None, None),
            ("사라진 규칙", "breakfast_time", None, None),
            ("사라진 후보", "breakfast_time", WATER, "통과 중이던 후보가 사라짐"),
            ("사라진 후보", "breakfast_time", "Person looks at the phone", "규칙대로 바꿈"),
            ("사라진 후보", "breakfast_time", "Person stretches", "규칙 어김"),
            ("사라진 후보", "breakfast_time", "Person sits down", "규칙 어김"),
            ("사라진 후보", "evening", "Person closes the book", "규칙 어김"),
            ("새 후보", "breakfast_time", "Person puts the plate in the sink", None),
            ("새 후보", "night_time", "Person closes the book", None),
        })


class MatcherTests(unittest.TestCase):
    def test_answer_key_matcher_keeps_event_names_and_leaves_other_text_unmatched(self):
        bundle = {"asked_candidates": ["finish_drinking", "Person finishes the water"]}
        self.assertEqual(ns.answer_key_matcher(KEY)(bundle, Path("unused")),
                         {"matches": [{"index": 1, "event": "finish_drinking"}, {"index": 2, "event": None}]})

    def test_model_matcher_saves_the_bundle_and_returns_only_a_valid_answer(self):
        answer = {"matches": [{"index": 1, "event": "finish_drinking"}]}
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / "attempt-1"
            with patch("night_scoring.infer_text_bundle", return_value={"status": "valid", "output": answer}) as infer:
                self.assertEqual(ns.model_matcher(Path("config.json"))({"role": "matching"}, work), answer)
            self.assertTrue((work / "bundle.json").exists())
            self.assertEqual(infer.call_args[0][1], Path("config.json"))
            with patch("night_scoring.infer_text_bundle", return_value={"status": "invalid", "output": None}):
                with self.assertRaises(RuntimeError):
                    ns.model_matcher(Path("config.json"))({"role": "matching"}, Path(temp) / "attempt-2")


if __name__ == "__main__":
    unittest.main()
