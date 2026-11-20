"""Exercise orchestration with real preparation and mocked inference/commit.

Colored local fixtures are processing inputs only. All model calls are mocked;
memory_store's separate tests cover raw API provenance checks at commit time.
"""

from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from pam.memory_store import MemoryStoreError, get_memory_for_day
from pam.reflection_experiment import CASE_IDS, ReflectionExperimentError, run_experiment


PROJECT = Path(__file__).resolve().parent.parent


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ReflectionExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = self.root / "processing_data"
        self.dataset.mkdir()
        self.left, self.right = self.dataset / "left.png", self.dataset / "right.png"
        Image.new("RGB", (4, 3), "red").save(self.left)
        Image.new("RGB", (5, 3), "blue").save(self.right)
        self._observations("training", "2026-10-24T07:00:00+09:00", 201)
        for hour, case_id in enumerate(CASE_IDS, 7):
            self._observations(case_id, f"2026-10-25T{hour:02}:00:00+09:00", 11)
        self.summary = self.root / "summary.txt"
        self.feedback = self.root / "feedback.txt"
        self.summary.write_text("Local processing fixture: no real person or robot acted.\n", encoding="utf-8")
        self.feedback.write_text("Synthetic feedback used only to test workflow wiring.\n", encoding="utf-8")
        self.expectations = self.root / "expectations.json"
        _write(self.expectations, {"purpose": "Held-out only", "cases": [
            {"id": case_id, "label_ko": "EVALUATION_ONLY_SENTINEL_" + case_id,
             "expected_task_indices": [index]}
            for case_id, index in zip(CASE_IDS, (-1, 0, -1))]})
        self.output = self.root / "experiment"
        self.provider_config = PROJECT / "config" / "openrouter.json"
        self.scenario_dir = self.root / "scenario"
        shutil.copytree(PROJECT / "scenarios" / "morning", self.scenario_dir)
        self.calls = []
        self.commit_count = 0
        self.fail_call = None
        self.raise_call = None
        self.fail_commit = False
        self.mutate_images_at_commit = False
        self.new_memory = None
        self.mutate_tasks_after_first = False
        self.mutate_scenario_after_first = False

    def _observations(self, name, start, count):
        start = datetime.fromisoformat(start)
        records = [{"timestamp": (start + timedelta(seconds=index)).isoformat(),
                    "left_image": "left.png", "right_image": "right.png"} for index in range(count)]
        _write(self.dataset / f"{name}_observations.json", {"observations": records})

    def _infer(self, bundle_path, config_path, output, *, run_state):
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        stage_id = output.parent.name
        self.calls.append({"stage_id": stage_id, "bundle": bundle, "config": str(config_path)})
        ordinal = len(self.calls)
        run_state.update({"api_request_attempted": True, "model_response_received": True})
        if ordinal == self.raise_call:
            raise OSError("simulated artifact write failure after receiving a response")
        result = {"status": "valid", "api_request_attempted": True, "model_response_received": True,
                  "action_executed": False, "response_id": f"mock-local-response-{ordinal}",
                  "role": bundle["role"]}
        if bundle["role"] == "reflector":
            memory = json.loads(Path(bundle["inputs"]["memory"]["path"]).read_text(encoding="utf-8"))
            self.new_memory = deepcopy(memory)
            self.new_memory["states"][0]["description"] += " Mock reflected memory fixture."
            result.update({"memory": self.new_memory, "raw_response": json.dumps(self.new_memory)})
        else:
            action = {"before_wakeup": 0, "before_seated_without_milk": 0, "before_seated_with_milk": -1,
                      "after_wakeup": -1, "after_seated_without_milk": 0, "after_seated_with_milk": -1}[stage_id]
            result.update({"prediction": {"observation": "Processing fixture.", "reasoning": "Mock output.", "task_index": action},
                           "selected_action_ko": "모의 행동", "selected_action": None if action == -1 else bundle["tasks"][action]})
        if ordinal == self.fail_call:
            result.update({"status": "invalid", "prediction": None, "memory": None, "errors": ["Mock invalid response."]})
        _write(output / "result.json", result)
        _write(output / "api_response.raw.json", {"mock_test_only": True, "result": result})
        if ordinal == 1 and self.mutate_tasks_after_first:
            path = self.scenario_dir / "tasks.json"
            tasks = json.loads(path.read_text(encoding="utf-8"))
            tasks.reverse()
            _write(path, tasks)
        if ordinal == 1 and self.mutate_scenario_after_first:
            path = self.scenario_dir / "scenario.json"
            path.write_bytes(path.read_bytes() + b"\n")
        return result

    def _commit(self, store, result_path, bundle_path, source_day, effective_day):
        self.commit_count += 1
        if self.fail_commit:
            raise MemoryStoreError("simulated reflection evidence mismatch")
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(self.calls[-1]["stage_id"], "reflection")
        source_memory, source_record = get_memory_for_day(store, source_day)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result["memory"], self.new_memory)
        version = store / "versions" / "001_test_fixture.json"
        _write(version, self.new_memory)
        identifier = "001_test_fixture"
        record = {"version_id": identifier, "file": "versions/001_test_fixture.json",
                  "sha256": hashlib.sha256(version.read_bytes()).hexdigest(), "effective_day": effective_day,
                  "source_day": source_day, "origin": "unit_test_fixture_only", "evidence": {}}
        manifest_path = store / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["versions"][identifier] = record
        manifest["assignments"][effective_day] = identifier
        _write(manifest_path, manifest)
        self.assertEqual(get_memory_for_day(store, source_day), (source_memory, source_record))
        if self.mutate_images_at_commit:
            Image.new("RGB", (4, 3), "green").save(self.left)
        return {**record, "memory_path": str(version.resolve())}

    def _run(self, **options):
        with patch("pam.reflection_experiment.infer_bundle", side_effect=self._infer), \
                patch("pam.reflection_experiment.commit_reflection", side_effect=self._commit), \
                redirect_stdout(io.StringIO()):
            return run_experiment(
                dataset_dir=self.dataset, scenario_path=self.scenario_dir / "scenario.json",
                summary_path=self.summary, feedback_path=self.feedback, expectations_path=self.expectations,
                provider_config=self.provider_config, output_dir=self.output, **options)

    def test_exact_seven_call_order_and_only_new_memory_used_after_commit(self):
        report = self._run()
        self.assertEqual(report["status"], "completed", report.get("error"))
        self.assertEqual([call["stage_id"] for call in self.calls], [
            "before_wakeup", "before_seated_without_milk", "before_seated_with_milk", "reflection",
            "after_wakeup", "after_seated_without_milk", "after_seated_with_milk"])
        self.assertEqual(report["api_requests_attempted"], 7)
        self.assertEqual(report["model_responses_received"], 7)
        self.assertEqual(report["valid_results"], 7)
        self.assertEqual(self.commit_count, 1)
        old = report["old_memory"]["memory_path"]
        new = report["new_memory"]["memory_path"]
        self.assertNotEqual(old, new)
        self.assertTrue(all(call["bundle"]["inputs"]["memory"]["path"] == old for call in self.calls[:4]))
        self.assertTrue(all(call["bundle"]["inputs"]["memory"]["path"] == new for call in self.calls[4:]))
        _, day_one = get_memory_for_day(Path(report["memory_store"]), "2026-10-24")
        self.assertEqual(day_one["memory_path"], old)
        self.assertEqual(report["before_passed"], 2)
        self.assertEqual(report["after_passed"], 3)
        self.assertTrue(report["all_after_passed"])
        self.assertTrue(all(case["same_images"] for case in report["comparisons"]))

    def test_evaluation_labels_are_absent_from_every_model_message(self):
        report = self._run()
        self.assertEqual(report["status"], "completed")
        for call in self.calls:
            messages = json.dumps(call["bundle"]["messages"], ensure_ascii=False)
            self.assertNotIn("EVALUATION_ONLY_SENTINEL", messages)
            self.assertNotIn(str(self.expectations), messages)
            self.assertNotIn("expectations", call["bundle"]["inputs"])
        diff = json.loads((self.output / "memory_diff.json").read_text(encoding="utf-8"))
        self.assertEqual(set(diff), {"old_memory", "new_memory"})
        self.assertEqual(diff["new_memory"], self.new_memory)

    def test_invalid_model_result_stops_all_later_calls_and_commit(self):
        self.fail_call = 2
        report = self._run()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["api_requests_attempted"], 2)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.commit_count, 0)
        self.assertIsNone(report["comparisons"])
        self.assertIn("before_seated_without_milk", report["failed_stage"])
        persisted = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["api_requests_attempted"], 2)

    def test_failure_after_response_preserves_attempt_and_response_counts(self):
        self.raise_call = 2
        report = self._run()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["api_requests_attempted"], 2)
        self.assertEqual(report["model_responses_received"], 2)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.commit_count, 0)

    def test_commit_failure_stops_before_next_day_predictions(self):
        self.fail_commit = True
        report = self._run()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failed_stage"], "commit_reflection")
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(report["api_requests_attempted"], 4)
        with self.assertRaises(MemoryStoreError):
            get_memory_for_day(Path(report["memory_store"]), "2026-10-25")

    def test_changed_heldout_image_stops_before_any_after_call(self):
        self.mutate_images_at_commit = True
        report = self._run()
        self.assertEqual(report["status"], "failed")
        self.assertIn("images changed", report["error"])
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(report["api_requests_attempted"], 4)

    def test_missing_input_is_detected_before_any_billable_call(self):
        (self.dataset / "seated_with_milk_observations.json").unlink()
        report = self._run()
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failed_stage"], "preflight")
        self.assertEqual(report["api_requests_attempted"], 0)
        self.assertEqual(self.calls, [])

    def test_changed_action_order_stops_before_next_call(self):
        self.mutate_tasks_after_first = True
        report = self._run()
        self.assertEqual(report["status"], "failed")
        self.assertIn("fixed scenario", report["error"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(report["api_requests_attempted"], 1)

    def test_letterbox_is_applied_only_to_reflection_without_changing_predictor_pairs(self):
        report = self._run(reflection_vertical_padding_px=48)
        self.assertEqual(report["status"], "completed", report.get("error"))
        self.assertEqual(len(self.calls), 7)
        for call in self.calls:
            bundle = call["bundle"]
            expected = 48 if bundle["role"] == "reflector" else 0
            self.assertEqual(bundle["image_adaptation"]["vertical_padding_px"], expected)
            self.assertTrue(all(frame["height"] == 3 + 2 * expected for frame in bundle["frames"]))
        self.assertTrue(all(case["same_images"] for case in report["comparisons"]))

    def test_user_requested_150_frames_preserves_all_three_comparison_pairs(self):
        config = json.loads(self.provider_config.read_text(encoding="utf-8"))
        config["reflector_frame_count"] = 150
        self.provider_config = self.root / "provider_150.json"
        _write(self.provider_config, config)
        report = self._run(reflector_frame_count=150)
        self.assertEqual(report["status"], "completed", report.get("error"))
        self.assertEqual(report["reflector_frame_count_source"], "explicit_user_override")
        reflector = next(call["bundle"] for call in self.calls if call["bundle"]["role"] == "reflector")
        self.assertEqual(len(reflector["frames"]), 150)
        self.assertEqual(reflector["frame_count"], 150)
        self.assertEqual(reflector["frame_count_source"], "explicit_user_override")
        self.assertTrue(all(case["same_images"] for case in report["comparisons"]))

    def test_changed_scenario_stops_before_next_call(self):
        self.mutate_scenario_after_first = True
        report = self._run()
        self.assertEqual(report["status"], "failed")
        self.assertIn("fixed scenario", report["error"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(report["api_requests_attempted"], 1)

    def test_existing_output_directory_cannot_resume_or_repeat_calls(self):
        self.assertEqual(self._run()["status"], "completed")
        report_bytes = (self.output / "report.json").read_bytes()
        with self.assertRaises(ReflectionExperimentError):
            self._run()
        self.assertEqual(len(self.calls), 7)
        self.assertEqual((self.output / "report.json").read_bytes(), report_bytes)


if __name__ == "__main__":
    unittest.main()
