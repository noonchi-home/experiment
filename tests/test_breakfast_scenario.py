"""Regression checks for the user's current seated-start scenario, not model accuracy."""
from pathlib import Path
import unittest

from pam.scenarios import load_scenario, load_scenario_memory, load_scenario_tasks

ROOT = Path(__file__).resolve().parents[1]


class BreakfastScenarioTests(unittest.TestCase):
    def test_current_start_and_milk_condition_exclude_retired_wakeup_cue(self):
        scenario = load_scenario(ROOT / "scenarios/breakfast/scenario.json")
        memory = load_scenario_memory(scenario, "fsm")
        self.assertEqual(memory["initial_state"], "meal_preparation")
        self.assertEqual(len(memory["states"]), 4)
        self.assertNotIn("bed", str(memory).lower())
        self.assertNotIn("wakes", str(memory).lower())
        rule = memory["states"][0]["rules"][0]
        self.assertIn("seated at the breakfast table", rule["trigger"])
        self.assertIn("milk bottle is not on the table", rule["trigger"])
        self.assertIn("not holding or touching", rule["trigger"])
        self.assertEqual(rule["action"], load_scenario_tasks(scenario)[0])

    def test_fsm_and_list_have_same_assistance_actions_without_new_priorities(self):
        scenario = load_scenario(ROOT / "scenarios/breakfast/scenario.json")
        memory = load_scenario_memory(scenario, "fsm")
        flattened = [rule for state in memory["states"] for rule in state["rules"]]
        self.assertEqual(flattened, load_scenario_memory(scenario, "list")["rules"])
        self.assertEqual([r["action"] for r in flattened], load_scenario_tasks(scenario))
        for rule in flattened[1:]:
            self.assertIn("observed leaving home through the exit", rule["trigger"])
            self.assertIn("not held or touched", rule["trigger"])


if __name__ == "__main__":
    unittest.main()
