"""Offline integration tests. Colored fixtures and handwritten JSON are not model results."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path

from pam.__main__ import main
from pam.contracts import ContractError
from pam.messages import (PROJECT_ROOT, build_predictor_messages, build_reflector_messages,
                          load_paper_config, read_json)
from pam.observations import (compose_observations, load_observations, select_predictor_window,
                              select_reflector_frames)
from tools.make_processing_fixture import create_fixture


class MessagesAndCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.fixture = cls.root / "fixture"
        create_fixture(cls.fixture)
        cls.observations = load_observations(cls.fixture / "observations.json")
        cls.predictor_frames = compose_observations(
            select_predictor_window(cls.observations, datetime.fromisoformat("2026-10-24T07:00:08+09:00")),
            cls.root / "predictor_images")
        cls.reflector_frames = compose_observations(select_reflector_frames(cls.observations),
                                                   cls.root / "reflector_images")
        cls.tasks = read_json(PROJECT_ROOT / "config" / "paper_tasks.json")
        cls.fsm = read_json(cls.fixture / "fsm_memory.json")
        cls.list_memory = {"rules": [{"trigger": "SENTINEL list cue", "action": cls.tasks[1]}]}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_cli(self, args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(args)
        return code, json.loads(stream.getvalue())

    def test_predictor_no_memory_and_paper_settings(self):
        result = build_predictor_messages(self.predictor_frames, self.tasks)
        self.assertEqual(result["prompt_source"]["id"], "predictor_no_memory")
        system, user = result["messages"]
        self.assertNotIn("## Memory", system["content"])
        self.assertIn("0: " + self.tasks[0], system["content"])
        self.assertIn("otherwise 0..5", system["content"])
        self.assertIn("2026-10-24T07:00:08+09:00", user["content"][0]["text"])
        self.assertEqual(len(user["content"][1:]), 5)
        self.assertEqual([part["path"] for part in user["content"][1:]],
                         [frame["image_path"] for frame in self.predictor_frames])
        self.assertEqual(result["generation"], {"temperature": 0.3, "enable_thinking": False})
        self.assertNotIn("task_index", result)  # No fabricated model decision.

    def test_no_memory_refuses_memory_instead_of_ignoring_it(self):
        with self.assertRaises(ContractError):
            build_predictor_messages(self.predictor_frames, self.tasks, memory=self.fsm)

    def test_list_and_fsm_use_their_own_paper_prompt(self):
        for kind, memory in (("list", self.list_memory), ("fsm", self.fsm)):
            with self.subTest(kind=kind):
                result = build_predictor_messages(self.predictor_frames, self.tasks,
                                                  memory_kind=kind, memory=memory)
                self.assertEqual(result["prompt_source"]["id"], f"predictor_{kind}")
                self.assertIn(json.dumps(memory, indent=2), result["messages"][0]["content"])
                with self.assertRaises(ContractError):
                    build_predictor_messages(self.predictor_frames, self.tasks,
                                              memory_kind=kind,
                                              memory=self.fsm if kind == "list" else self.list_memory)

    def test_json_braces_and_placeholder_like_input_remain_literal(self):
        memory = {"rules": [{"trigger": "A literal {tasks_block} cue", "action": self.tasks[0]}]}
        result = build_predictor_messages(self.predictor_frames, ["Literal {fsm_block} action"],
                                          memory_kind="list", memory=memory)
        self.assertIn("A literal {tasks_block} cue", result["messages"][0]["content"])
        self.assertIn("0: Literal {fsm_block} action", result["messages"][0]["content"])

    def test_bad_predictor_frame_count_and_stride_are_rejected(self):
        with self.assertRaises(ContractError):
            build_predictor_messages(self.predictor_frames[:-1], self.tasks)
        frames = [dict(frame) for frame in self.predictor_frames]
        frames[-1]["timestamp"] = "2026-10-24T07:00:09+09:00"
        with self.assertRaises(ContractError):
            build_predictor_messages(frames, self.tasks)

    def test_reflector_build_and_update_keep_inputs_distinct(self):
        for kind, memory in (("list", self.list_memory), ("fsm", self.fsm)):
            build = build_reflector_messages(self.reflector_frames, memory_kind=kind, operation="build")
            self.assertEqual(build["prompt_source"]["id"], f"reflector_{kind}_build")
            self.assertEqual(build["frame_count"], 200)
            self.assertEqual(build["frame_count_source"], "paper")
            self.assertEqual(len(build["messages"][1]["content"]), 201)
            self.assertEqual(sum(p["type"] == "image_file" for p in build["messages"][1]["content"]), 200)
            self.assertNotIn("Current memory:", str(build["messages"][1]))
            update = build_reflector_messages(self.reflector_frames, memory_kind=kind, operation="update",
                                              memory=memory, summary="Only a fixture summary.",
                                              feedback="Optional user feedback.")
            self.assertEqual(update["prompt_source"]["id"], f"reflector_{kind}_update")
            self.assertTrue(update["generation"]["enable_thinking"])
            text = update["messages"][1]["content"][-1]["text"]
            self.assertIn(json.dumps(memory, indent=2), text)
            self.assertIn("Summary:\nOnly a fixture summary.", text)
            self.assertIn("Human feedback:\nOptional user feedback.", text)

    def test_reflector_user_150_count_is_explicit_and_preserves_paper_prompt(self):
        standard = build_reflector_messages(self.reflector_frames, memory_kind="fsm", operation="build")
        changed = build_reflector_messages(self.reflector_frames[:150], memory_kind="fsm",
                                           operation="build", frame_count=150)
        self.assertEqual(changed["frame_count"], 150)
        self.assertEqual(changed["frame_count_source"], "explicit_user_override")
        self.assertEqual(sum(part["type"] == "image_file" for part in changed["messages"][1]["content"]), 150)
        self.assertEqual(changed["messages"][0], standard["messages"][0])
        self.assertEqual(load_paper_config()["reflector"]["frame_count"], 200)
        for bad_count in (149, 0, True, 150.0, None):
            with self.subTest(count=bad_count), self.assertRaises(ContractError):
                build_reflector_messages(self.reflector_frames[:150], memory_kind="fsm",
                                         operation="build", frame_count=bad_count)
        with self.assertRaises(ContractError):
            build_reflector_messages(self.reflector_frames[:150], memory_kind="fsm", operation="build")
        with self.assertRaises(ContractError):
            build_reflector_messages(self.reflector_frames, memory_kind="fsm", operation="build", frame_count=150)

    def test_reflector_user_100_count_and_cli_choice(self):
        from pam.__main__ import parser
        result = build_reflector_messages(self.reflector_frames[:100], memory_kind="fsm",
                                          operation="build", frame_count=100)
        self.assertEqual(result["frame_count"], 100)
        self.assertEqual(result["frame_count_source"], "explicit_user_override")
        self.assertEqual(sum(part["type"] == "image_file" for part in result["messages"][1]["content"]), 100)
        args = parser().parse_args(["prepare-reflector", "--observations", "observations.json",
                                   "--memory-kind", "fsm", "--operation", "build",
                                   "--reflector-frame-count", "100", "--output", "new-output"])
        self.assertEqual(args.reflector_frame_count, 100)
        selected = select_reflector_frames(self.observations, count=100)
        self.assertEqual(len(selected), 100)
        self.assertEqual(selected[0], self.observations[0])
        self.assertEqual(selected[-1], self.observations[-1])

    def test_reflector_user_50_count_and_cli_choice(self):
        from pam.__main__ import parser
        result = build_reflector_messages(self.reflector_frames[:50], memory_kind="fsm",
                                          operation="build", frame_count=50)
        self.assertEqual(result["frame_count"], 50)
        self.assertEqual(result["frame_count_source"], "explicit_user_override")
        self.assertEqual(sum(part["type"] == "image_file" for part in result["messages"][1]["content"]), 50)
        args = parser().parse_args(["prepare-reflector", "--observations", "observations.json",
                                   "--memory-kind", "fsm", "--operation", "build",
                                   "--reflector-frame-count", "50", "--output", "new-output"])
        self.assertEqual(args.reflector_frame_count, 50)
        selected = select_reflector_frames(self.observations, count=50)
        self.assertEqual(len(selected), 50)
        self.assertEqual(selected[0], self.observations[0])
        self.assertEqual(selected[-1], self.observations[-1])
        self.assertEqual(load_paper_config()["reflector"]["frame_count"], 200)

    def test_reflector_rejects_build_extras_and_missing_update_inputs(self):
        for extra in ({"memory": self.fsm}, {"summary": "not permitted"}, {"feedback": "not permitted"}):
            with self.assertRaises(ContractError):
                build_reflector_messages(self.reflector_frames, memory_kind="fsm", operation="build", **extra)
        for extra in ({}, {"memory": self.fsm}, {"summary": "missing memory"}):
            with self.assertRaises(ContractError):
                build_reflector_messages(self.reflector_frames, memory_kind="fsm", operation="update", **extra)
        result = build_reflector_messages(self.reflector_frames, memory_kind="fsm", operation="update",
                                          memory=self.fsm, summary="Fixture summary.")
        self.assertNotIn("Human feedback:", str(result["messages"][1]))
        with self.assertRaises(ContractError):
            build_reflector_messages(self.reflector_frames[:-1], memory_kind="fsm", operation="build")

    def test_cli_predictor_prepares_inspectable_bundle_and_refuses_overwrite(self):
        output = self.root / "cli_predictor"
        args = ["prepare-predictor", "--observations", str(self.fixture / "observations.json"),
                "--tasks", str(PROJECT_ROOT / "config" / "paper_tasks.json"),
                "--memory-kind", "fsm", "--memory", str(self.fixture / "fsm_memory.json"),
                "--at", "2026-10-24T07:00:08+09:00", "--output", str(output)]
        code, result = self.run_cli(args)
        self.assertEqual(code, 0, result)
        bundle = read_json(output / "input_bundle.json")
        self.assertFalse(bundle["api_called"])
        self.assertFalse(bundle["action_executed"])
        self.assertIsNone(bundle["model_result"])
        self.assertEqual(len(bundle["frames"]), 5)
        self.assertEqual([frame["timestamp"][17:19] for frame in bundle["frames"]], ["00", "02", "04", "06", "08"])
        self.assertTrue(all(len(frame["sha256"]) == 64 for frame in bundle["frames"]))
        self.assertTrue((output / "system_prompt.txt").is_file())
        self.assertTrue((output / "검토안내.txt").is_file())
        original = (output / "input_bundle.json").read_bytes()
        self.assertEqual(self.run_cli(args)[0], 2)
        self.assertEqual((output / "input_bundle.json").read_bytes(), original)

    def test_cli_reflector_build_and_update(self):
        for operation in ("build", "update"):
            output = self.root / ("cli_reflector_" + operation)
            args = ["prepare-reflector", "--observations", str(self.fixture / "observations.json"),
                    "--memory-kind", "fsm", "--operation", operation, "--output", str(output)]
            if operation == "update":
                args += ["--memory", str(self.fixture / "fsm_memory.json"),
                         "--summary", str(self.fixture / "summary.txt")]
            code, result = self.run_cli(args)
            self.assertEqual(code, 0, result)
            bundle = read_json(output / "input_bundle.json")
            self.assertEqual(len(bundle["frames"]), 200)
            self.assertEqual(bundle["frame_count"], 200)
            self.assertEqual(bundle["frame_count_source"], "paper")
            self.assertFalse(bundle["api_called"])
            self.assertEqual(bundle["operation"], operation)

    def test_cli_reflector_150_selects_whole_record_and_records_user_override(self):
        output = self.root / "cli_reflector_150"
        args = ["prepare-reflector", "--observations", str(self.fixture / "observations.json"),
                "--memory-kind", "fsm", "--operation", "update", "--memory", str(self.fixture / "fsm_memory.json"),
                "--summary", str(self.fixture / "summary.txt"), "--reflector-frame-count", "150", "--output", str(output)]
        code, result = self.run_cli(args)
        self.assertEqual(code, 0, result)
        bundle = read_json(output / "input_bundle.json")
        self.assertFalse(bundle["api_called"])
        self.assertEqual(len(bundle["frames"]), 150)
        self.assertEqual(bundle["frame_count"], 150)
        self.assertEqual(bundle["frame_count_source"], "explicit_user_override")
        self.assertEqual(bundle["paper_config"]["reflector"]["frame_count"], 200)
        self.assertEqual(bundle["frames"][0]["timestamp"], self.observations[0].timestamp.isoformat())
        self.assertEqual(bundle["frames"][-1]["timestamp"], self.observations[-1].timestamp.isoformat())
        self.assertTrue(all(frame["vertical_padding_px"] == 0 for frame in bundle["frames"]))
        self.assertIn("사용자 지시로 150개", (output / "검토안내.txt").read_text(encoding="utf-8"))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main([*args[:-4], "--reflector-frame-count", "149", "--output", str(self.root / "bad_count")])

    def test_cli_startup_not_ready_is_not_no_action(self):
        output = self.root / "cli_not_ready"
        code, result = self.run_cli([
            "prepare-predictor", "--observations", str(self.fixture / "observations.json"),
            "--tasks", str(PROJECT_ROOT / "config" / "paper_tasks.json"),
            "--at", "2026-10-24T07:00:07+09:00", "--output", str(output)])
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "observation_not_ready")
        self.assertIsNone(result["model_result"])
        self.assertNotIn("task_index", result)
        self.assertTrue((output / "preparation_error.json").is_file())
        self.assertFalse((output / "input_bundle.json").exists())

    def test_cli_invalid_response_is_preserved_and_not_converted_to_wait(self):
        raw = '{"observation":"Fixture only.","reasoning":"Fixture only.","task_index":99}'
        response = self.root / "provided_invalid_response.txt"
        response.write_text(raw, encoding="utf-8")
        output = self.root / "cli_invalid_response"
        code, result = self.run_cli([
            "validate-response", "--response", str(response),
            "--tasks", str(PROJECT_ROOT / "config" / "paper_tasks.json"), "--output", str(output)])
        self.assertEqual(code, 2)
        saved = read_json(output / "response_check.json")
        self.assertEqual(saved["raw_response"], raw)
        self.assertEqual(saved["status"], "invalid")
        self.assertIsNone(saved["prediction"])
        self.assertFalse(saved["api_called"])
        self.assertFalse(saved["semantic_accuracy_evaluated"])

    def test_input_json_duplicate_keys_are_rejected(self):
        path = self.root / "duplicate_keys.json"
        path.write_text('{"rules":[],"rules":[]}', encoding="utf-8")
        with self.assertRaises(ContractError):
            read_json(path)

    def test_malformed_configuration_reports_contract_error(self):
        for malformed_role in (None, [], "not an object"):
            with self.subTest(value=malformed_role), patch("pam.messages.read_json", return_value={
                "model": "Qwen3.5-27B", "predictor": malformed_role,
            }):
                with self.assertRaises(ContractError):
                    load_paper_config()


if __name__ == "__main__":
    unittest.main()
