"""Night scoring, matching step: candidates to answer-key events (no live calls).

Run from this folder: python -m unittest test_night_scoring
"""

import json
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
