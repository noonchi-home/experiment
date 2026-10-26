"""Verify scenario data and permitted paper adaptations; no model inference."""

import hashlib
import json
from pathlib import Path
import re
import unittest

from pam.contracts import validate_memory, validate_tasks


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = ROOT / "scenarios/morning"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def adapt_for_check(text, replacements):
    for replacement in replacements:
        text = text.replace(replacement["old"], replacement["new"])
    return text


class MorningScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = read_json(SCENARIO_DIR / "scenario.json")
        cls.tasks = read_json(SCENARIO_DIR / cls.scenario["tasks_file"])
        cls.fsm = read_json(SCENARIO_DIR / cls.scenario["memory_files"]["fsm"])
        cls.rules = read_json(SCENARIO_DIR / cls.scenario["memory_files"]["list"])
        cls.provenance = read_json(SCENARIO_DIR / "provenance.json")
        cls.source_map = read_json(ROOT / "prompts/source_map.json")

    def test_three_single_object_actions_and_display_labels_align(self):
        self.assertEqual(validate_tasks(self.tasks), [
            "Pick up the milk and place it next to the person.",
            "Pick up the cup and place it in the sink.",
            "Pick up the plate and place it in the sink.",
        ])
        self.assertEqual(self.scenario["action_labels_ko"], [
            "우유를 사용자 곁에 가져다놓기",
            "컵을 싱크대에 가져다놓기",
            "접시를 싱크대에 가져다놓기",
        ])
        for task in self.tasks:
            self.assertEqual(task.count("Pick up "), 1)
            self.assertRegex(task, r"^Pick up the (milk|cup|plate) and place it (next to the person|in the sink)\.$")

    def test_both_memory_forms_use_the_paper_schema_and_identical_rules(self):
        self.assertIs(validate_memory(self.fsm, "fsm"), self.fsm)
        self.assertIs(validate_memory(self.rules, "list"), self.rules)
        flattened = [rule for state in self.fsm["states"] for rule in state["rules"]]
        self.assertEqual(flattened, self.rules["rules"])
        self.assertEqual([rule["action"] for rule in flattened], self.tasks)
        self.assertEqual(len(self.fsm["states"]), 5)
        final_state = self.fsm["states"][-1]
        self.assertEqual(final_state["next"], [])
        self.assertEqual({rule["action"] for rule in final_state["rules"]}, set(self.tasks[1:]))
        # Two independent cleanup rules are allowed in the same phase; no action
        # combines the cup and plate, and their ordering is not a priority policy.
        self.assertIsNone(self.provenance["task_mapping"]["cup_plate_priority"])

    def test_manual_seed_is_explicit_without_claiming_five_observed_days(self):
        initial = self.provenance["initial_memory"]
        self.assertEqual(initial["origin"], "manual_seed_from_user_assumed_habit")
        self.assertIs(initial["learned_from_recorded_days"], False)
        self.assertIs(initial["model_generated"], False)
        self.assertIsNone(initial["prior_day_count"])
        mechanism = self.provenance["preserved_mechanism"]
        self.assertIs(mechanism["paper_prompt_files_modified"], False)
        self.assertIs(mechanism["strict_fsm_interpreter_added"], False)
        self.assertIs(mechanism["handwritten_action_selector_added"], False)
        self.assertIs(mechanism["memory_build_and_update_retained"], True)

    def test_exact_replacements_have_documented_sources_and_expected_scope(self):
        replacements = self.scenario["prompt_replacements"]
        self.assertEqual(len(replacements), 6)
        occurrence_counts = [0] * len(replacements)
        for name, source in self.source_map["prompts"].items():
            with self.subTest(prompt=name):
                raw = (ROOT / source["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])
                original = raw.decode("utf-8")
                for index, replacement in enumerate(replacements):
                    self.assertEqual(set(replacement), {"old", "new", "reason"})
                    self.assertTrue(replacement["reason"].strip())
                    self.assertNotEqual(replacement["old"], replacement["new"])
                    occurrence_counts[index] += original.count(replacement["old"])
                adapted = adapt_for_check(original, replacements)
                self.assertIn("a bedroom, a breakfast table, a kitchen sink, and a visible exit", adapted)
                self.assertNotIn("personal desk", adapted)
                self.assertNotIn("corner of the desk", adapted)
                self.assertNotIn("on the desk", adapted)
                self.assertNotIn("down at the desk", adapted)
                self.assertEqual(re.findall(r"\{([a-z][a-z0-9_]*)\}", original),
                                 re.findall(r"\{([a-z][a-z0-9_]*)\}", adapted))
                if name.startswith("reflector_"):
                    self.assertIn("`in the sink`", adapted)
                    self.assertIn("`Pick up <object> and place it <location>.`", adapted)
                # Output schemas and the semantic instruction that memory is a
                # reference are preserved exactly, including printed wrapping.
                marker = "## Output Requirements" if name.startswith("predictor_") else "# Output (JSON only"
                self.assertEqual(original.split(marker, 1)[1], adapted.split(marker, 1)[1])
                if name in {"predictor_list", "predictor_fsm"}:
                    self.assertIn("Treat the memory as a REFERENCE, not as a strict matcher.", adapted)
                    self.assertNotIn("built by reflecting on", adapted)
        self.assertEqual(occurrence_counts, [7, 7, 5, 1, 4, 2])

    def test_cleanup_requires_observed_departure_not_camera_absence(self):
        milk, cup, plate = self.rules["rules"]
        self.assertIn("getting out of bed", milk["trigger"])
        self.assertIn("regardless of the other foods", milk["trigger"])
        self.assertIn("rather than already beside the person", milk["trigger"])
        for rule in (cup, plate):
            self.assertIn("Breakfast has visibly ended", rule["trigger"])
            self.assertIn("cleared some meal items", rule["trigger"])
            self.assertIn("observed leaving home through the exit", rule["trigger"])
            self.assertIn("not held or touched", rule["trigger"])
            self.assertNotIn("forgot", rule["trigger"].lower())
        self.assertIn("absence from the camera view alone does not establish departure or forgetfulness",
                      self.fsm["states"][-1]["description"])


if __name__ == "__main__":
    unittest.main()
