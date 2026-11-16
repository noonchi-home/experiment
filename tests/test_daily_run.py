"""One-night-at-a-time runner with stub steps and a mocked model (no live calls)."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pam.daily_run import Steps, model_steps, run_night

CUP = "Pick up the cup and place it in the dishwasher."
WATER = "Person finishes the water"
SPOON = "Person puts down the spoon"


def write_record(path: Path) -> Path:
    # 07:00:00 ... 07:59:58, one line every 2 seconds; the stub steps ignore the wording.
    lines = [f"07:{minute:02d}:{second:02d} | The person is at the table."
             for minute in range(60) for second in range(0, 60, 2)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def memory(*candidates):
    return {"initial_state": "breakfast", "states": [
        {"id": "breakfast", "description": "Person eats breakfast.",
         "rules": [{"triggers": list(candidates), "action": CUP}], "next": []}]}


class StubSteps:
    """Every day: water finished at 07:10, spoon down at 07:30, cup into the dishwasher at 07:13."""

    def __init__(self, nights_with_spoon=()):
        self.calls = {"reflect": [], "mark": []}
        self.nights_with_spoon = set(nights_with_spoon)
        self.fail_mark = False

    def steps(self):
        return Steps(self.reflect, self.mark)

    def reflect(self, night, lines, prior, results, work):
        assert lines[0].startswith("07:00:00 | ")      # the reflector reads the record itself
        self.calls["reflect"].append((night, prior is None, results is None))
        return memory(WATER, SPOON) if night in self.nights_with_spoon else memory(WATER)

    def mark(self, day, lines, candidates, actions, states, work):
        assert len(lines) == 1800                       # so does marking, for the day it marks
        if self.fail_mark:
            raise RuntimeError("marking failed")
        self.calls["mark"].append((day, [c["candidate"] for c in candidates], list(actions)))
        times = {WATER: ["07:10:00"], SPOON: ["07:30:00"]}
        return {"candidates": [{**c, "times": times[c["candidate"]]} for c in candidates],
                "actions": [{"action": action, "times": ["07:13:00"]} for action in actions],
                "unseen": []}


class RunNightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.records = {day: write_record(self.folder / f"day{day}.txt") for day in (1, 2)}
        self.run_dir = self.folder / "run"

    def read(self, night, name):
        return json.loads((self.run_dir / f"night-{night}" / name).read_text(encoding="utf-8"))

    def test_two_followed_days_make_a_rule_on_night_two(self):
        stub = StubSteps()
        run_night(1, self.records, self.run_dir, stub.steps())
        first = self.read(1, "check_results.json")
        self.assertEqual([(r["candidate"], r["n"], r["k"], r["passed"]) for r in first], [(WATER, 1, 1, False)])
        self.assertEqual(self.read(1, "predictor_fsm.json")["states"][0]["rules"], [])
        run_night(2, self.records, self.run_dir, stub.steps())
        second = self.read(2, "check_results.json")
        self.assertEqual([(r["n"], r["k"], r["passed"]) for r in second], [(2, 2, True)])
        self.assertEqual(self.read(2, "predictor_fsm.json")["states"][0]["rules"], [{"trigger": WATER, "action": CUP}])
        self.assertEqual(stub.calls["reflect"], [(1, True, True), (2, False, False)])

    def test_finished_nights_are_loaded_not_run_again(self):
        stub = StubSteps()
        run_night(2, self.records, self.run_dir, stub.steps())
        saved = (self.run_dir / "night-1" / "check_results.json").read_text(encoding="utf-8")
        before = {name: list(calls) for name, calls in stub.calls.items()}
        summary = run_night(2, self.records, self.run_dir, stub.steps())
        self.assertEqual(stub.calls, before)
        self.assertEqual(summary["night"], 2)
        self.assertEqual((self.run_dir / "night-1" / "check_results.json").read_text(encoding="utf-8"), saved)

    def test_only_new_candidates_are_marked_on_past_days(self):
        stub = StubSteps(nights_with_spoon={2})
        run_night(2, self.records, self.run_dir, stub.steps())
        self.assertEqual(stub.calls["mark"], [(1, [WATER], [CUP]), (1, [SPOON], []), (2, [WATER, SPOON], [CUP])])
        spoon = [r for r in self.read(2, "check_results.json") if r["candidate"] == SPOON][0]
        self.assertEqual((spoon["n"], spoon["k"]), (2, 0))

    def test_a_failed_step_leaves_the_night_unfinished_and_resumes(self):
        stub = StubSteps()
        stub.fail_mark = True
        with self.assertRaises(RuntimeError):
            run_night(1, self.records, self.run_dir, stub.steps())
        self.assertFalse((self.run_dir / "night-1" / "done.json").exists())
        self.assertTrue((self.run_dir / "night-1" / "reflector_fsm.json").exists())
        stub.fail_mark = False
        run_night(1, self.records, self.run_dir, stub.steps())
        self.assertEqual(len(stub.calls["reflect"]), 1)
        self.assertTrue((self.run_dir / "night-1" / "done.json").exists())


class ModelStepTests(unittest.TestCase):
    def test_the_model_reads_the_record_itself(self):
        sent = []

        def fake_infer(bundle_path, config_path, output):
            bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
            sent.append(bundle)
            if bundle["role"] == "reflector_text":
                return {"status": "valid", "output": memory(WATER)}
            return {"status": "valid", "output": {"candidates": [], "actions": [{"action": CUP, "times": []}],
                                                  "unseen": []}}

        with tempfile.TemporaryDirectory() as temp, patch("pam.daily_run.infer_text_bundle", side_effect=fake_infer):
            lines = write_record(Path(temp) / "day1.txt").read_text(encoding="utf-8").splitlines()
            steps = model_steps([CUP], Path("unused.json"))
            steps.reflect(1, lines, None, None, Path(temp) / "reflect")
            steps.mark(1, lines, [], [CUP], {"breakfast": "Person eats breakfast."}, Path(temp) / "mark")
        self.assertEqual([bundle["role"] for bundle in sent], ["reflector_text", "marking"])
        for bundle in sent:
            self.assertIn("\n".join(lines), bundle["messages"][1]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
