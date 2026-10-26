"""Integration tests with colored fixtures and mocked replies, never real API calls."""

import contextlib
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pam.__main__ import main
from pam.contracts import ContractError
from pam.inference import _request_record, _verify_prepared_images, infer_bundle, inspect_completion
from pam.messages import PROJECT_ROOT, load_prompt, read_json
from pam.scenarios import adapt_prompt, load_scenario, load_scenario_memory, load_scenario_tasks
from pam.openrouter import build_request, load_openrouter_config
from tools.make_processing_fixture import create_fixture


class ScenarioInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.fixture = cls.root / "fixture"
        create_fixture(cls.fixture, count=9)
        cls.scenario_path = PROJECT_ROOT / "scenarios/morning/scenario.json"
        cls.scenario = load_scenario(cls.scenario_path)
        cls.prepared = cls.root / "prepared"
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["prepare-predictor", "--observations", str(cls.fixture / "observations.json"),
                         "--scenario", str(cls.scenario_path), "--memory-kind", "fsm",
                         "--at", "2026-10-24T07:00:08+09:00", "--output", str(cls.prepared)])
        if code:
            raise AssertionError(read_json(cls.prepared / "preparation_error.json"))
        cls.bundle_path = cls.prepared / "input_bundle.json"
        cls.bundle = read_json(cls.bundle_path)
        cls.provider = PROJECT_ROOT / "config/openrouter.json"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def fake_completion(self, task=0, finish="stop", content=None):
        if content is None:
            content = json.dumps({"observation": "Fixture observation.",
                                  "reasoning": "Fixture explanation, not a real model judgment.",
                                  "task_index": task})
        return {"id": "mock-test-only", "model": "qwen/qwen3.5-27b", "provider": "Alibaba",
                "choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

    def test_request_record_preserves_explicit_image_detail_and_original_hashes(self):
        config = load_openrouter_config(self.provider)
        config["image_detail"] = {"predictor": "high", "reflector": "low"}
        payload = build_request(self.bundle, config)
        original = copy.deepcopy(payload)
        recorded = _request_record(payload)
        image_records = [part["image_url"] for part in recorded["messages"][1]["content"] if part["type"] == "image_url"]
        self.assertEqual(len(image_records), 5)
        for record, frame in zip(image_records, self.bundle["frames"]):
            raw = Path(frame["image_path"]).read_bytes()
            self.assertEqual(record["detail"], "high")
            self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(record["bytes"], len(raw))
            self.assertNotIn("url", record)
        self.assertEqual(payload, original)
        del config["image_detail"]
        default_record = _request_record(build_request(self.bundle, config))
        self.assertTrue(all("detail" not in part["image_url"] for part in default_record["messages"][1]["content"]
                            if part["type"] == "image_url"))

    def test_prepared_reflector_150_needs_explicit_override_and_all_original_images(self):
        source_frame = copy.deepcopy(self.bundle["frames"][0])
        image_part = next(copy.deepcopy(part) for part in self.bundle["messages"][1]["content"]
                          if part["type"] == "image_file")
        bundle = {"status": "prepared", "execution_mode": "offline_preparation", "role": "reflector",
                  "frame_count": 150, "frame_count_source": "explicit_user_override",
                  "frames": [copy.deepcopy(source_frame) for _ in range(150)],
                  "messages": [{"role": "system", "content": "Processing fixture"},
                               {"role": "user", "content": [copy.deepcopy(image_part) for _ in range(150)]}]}
        _verify_prepared_images(bundle)
        undeclared = copy.deepcopy(bundle)
        del undeclared["frame_count_source"]
        with self.assertRaises(ContractError):
            _verify_prepared_images(undeclared)
        missing = copy.deepcopy(bundle)
        missing["frames"].pop()
        with self.assertRaises(ContractError):
            _verify_prepared_images(missing)
        hundred = copy.deepcopy(bundle)
        hundred["frame_count"] = 100
        hundred["frames"] = hundred["frames"][:100]
        hundred["messages"][1]["content"] = hundred["messages"][1]["content"][:100]
        _verify_prepared_images(hundred)
        del hundred["frame_count_source"]
        with self.assertRaises(ContractError):
            _verify_prepared_images(hundred)
        default = copy.deepcopy(bundle)
        del default["frame_count"]
        del default["frame_count_source"]
        default["frames"] += [copy.deepcopy(source_frame) for _ in range(50)]
        default["messages"][1]["content"] += [copy.deepcopy(image_part) for _ in range(50)]
        _verify_prepared_images(default)

    def test_scenario_uses_three_actions_and_seed_memory(self):
        self.assertEqual(len(load_scenario_tasks(self.scenario)), 3)
        self.assertEqual(len(self.bundle["tasks"]), 3)
        self.assertEqual(self.bundle["memory_kind"], "fsm")
        self.assertIn("initial_state", load_scenario_memory(self.scenario, "fsm"))
        self.assertEqual(len(self.bundle["scenario"]["action_labels_ko"]), 3)
        self.assertIn("scenario", self.bundle["inputs"])
        self.assertIn("memory", self.bundle["inputs"])
        self.assertIsNone(self.bundle["model_result"])

    def test_scenario_preserves_paper_templates_and_logs_changes(self):
        for prompt_id in ("predictor_no_memory", "predictor_list", "predictor_fsm",
                          "reflector_list_build", "reflector_list_update",
                          "reflector_fsm_build", "reflector_fsm_update"):
            original, source = load_prompt(prompt_id)
            adapted, provenance = adapt_prompt(original, self.scenario)
            self.assertNotEqual(adapted, original)
            self.assertEqual(load_prompt(prompt_id)[0], original)
            self.assertTrue(provenance["applied_changes"])
            self.assertNotIn("selected_action_ko", adapted)

    def test_prepare_no_memory_scenario_does_not_load_seed(self):
        output = self.root / "no_memory"
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["prepare-predictor", "--observations", str(self.fixture / "observations.json"),
                         "--scenario", str(self.scenario_path), "--memory-kind", "none",
                         "--at", "2026-10-24T07:00:08+09:00", "--output", str(output)])
        self.assertEqual(code, 0)
        bundle = read_json(output / "input_bundle.json")
        self.assertNotIn("memory", bundle["inputs"])
        self.assertNotIn("## Memory", bundle["messages"][0]["content"])

    def test_mock_inference_preserves_response_and_never_executes_action(self):
        response = self.fake_completion(1)
        raw = json.dumps(response)
        output = self.root / "mock_result"
        output.mkdir()
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-only-placeholder"}), patch(
            "pam.inference.send_request", return_value={"response": response, "raw_response": raw,
                                                        "elapsed_seconds": 0.25, "http_status": 200}) as send:
            result = infer_bundle(self.bundle_path, self.provider, output)
        send.assert_called_once()
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["selected_action_ko"], self.scenario["action_labels_ko"][1])
        self.assertFalse(result["action_executed"])
        self.assertFalse(result["semantic_accuracy_evaluated"])
        self.assertEqual((output / "api_response.raw.json").read_text(encoding="utf-8"), raw)
        self.assertTrue((output / "결과.html").is_file())
        recorded = read_json(output / "request_record.json")
        self.assertEqual(recorded["reasoning"], {"enabled": False})
        self.assertEqual(sum(p["type"] == "image_url" for p in recorded["messages"][1]["content"]), 5)
        for path in output.iterdir():
            self.assertNotIn("test-only-placeholder", path.read_text(encoding="utf-8"))

    def test_truncated_and_malformed_completions_are_not_wait(self):
        for response in (self.fake_completion(-1, finish="length"), self.fake_completion(3),
                         self.fake_completion(content="not JSON")):
            checked = inspect_completion(response, self.bundle)
            self.assertEqual(checked["status"], "invalid")
            self.assertIsNone(checked.get("prediction"))
        wait = inspect_completion(self.fake_completion(-1), self.bundle)
        self.assertEqual(wait["status"], "valid")
        self.assertEqual(wait["prediction"]["task_index"], -1)

    def test_unexpected_response_model_is_invalid(self):
        response = self.fake_completion()
        response["model"] = "unexpected/another-model"
        self.assertEqual(inspect_completion(response, self.bundle)["status"], "invalid")

    def test_error_after_response_preserves_actual_call_state(self):
        response = self.fake_completion()
        output = self.root / "post_response_error"
        stream = io.StringIO()
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-only-placeholder"}), patch(
            "pam.inference.send_request", return_value={"response": response, "raw_response": json.dumps(response),
                                                        "elapsed_seconds": 0.25, "http_status": 200}), patch(
            "pam.inference._write_review", side_effect=OSError("Mock disk failure")), contextlib.redirect_stdout(stream):
            code = main(["infer-bundle", "--bundle", str(self.bundle_path), "--output", str(output)])
        error = json.loads(stream.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(error["status"], "inference_error")
        self.assertTrue(error["api_request_attempted"])
        self.assertTrue(error["model_response_received"])

    def test_unexpected_provider_or_predictor_thinking_is_invalid(self):
        for name, modify in (
            ("provider", lambda r: r.update(provider="Other provider")),
            ("thinking", lambda r: r["usage"].update(completion_tokens_details={"reasoning_tokens": 20})),
        ):
            response = self.fake_completion()
            modify(response)
            output = self.root / ("unexpected_" + name)
            output.mkdir()
            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-only-placeholder"}), patch(
                "pam.inference.send_request", return_value={"response": response, "raw_response": json.dumps(response),
                                                            "elapsed_seconds": 0.25, "http_status": 200}):
                result = infer_bundle(self.bundle_path, self.provider, output)
            self.assertEqual(result["status"], "invalid")
            self.assertIsNone(result["prediction"])

    def test_reflector_output_validation_preserves_memory_without_applying_it(self):
        bundle = {"role": "reflector", "memory_kind": "fsm"}
        memory = load_scenario_memory(self.scenario, "fsm")
        response = self.fake_completion(content=json.dumps(memory))
        checked = inspect_completion(response, bundle)
        self.assertEqual(checked["memory"], memory)
        self.assertFalse(checked["memory_automatically_applied"])
        duplicate = self.fake_completion(content='{"rules":[],"rules":[]}')
        self.assertEqual(inspect_completion(duplicate, {"role": "reflector", "memory_kind": "list"})["status"], "invalid")

    def test_changed_prepared_image_is_rejected_before_api_call(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["frames"][0]["sha256"] = "0" * 64
        path = self.root / "tampered_bundle.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        output = self.root / "tampered_result"
        output.mkdir()
        with patch("pam.inference.send_request") as send, self.assertRaises(ContractError):
            infer_bundle(path, self.provider, output)
        send.assert_not_called()

    def test_missing_key_makes_no_api_call(self):
        output = self.root / "no_key_result"
        output.mkdir()
        with patch.dict("os.environ", {}, clear=True), patch("pam.inference.send_request") as send:
            with self.assertRaisesRegex(ValueError, "no API call"):
                infer_bundle(self.bundle_path, self.provider, output)
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
