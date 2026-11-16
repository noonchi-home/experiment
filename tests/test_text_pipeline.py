"""Text version of the nightly steps: contracts, prompts, requests and inference (no live calls)."""

from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from pam.contracts import ContractError, validate_candidate_memory, validate_marks
from pam.inference import infer_text_bundle, inspect_text_completion
from pam.openrouter import MODEL, OpenRouterError, build_text_request, load_text_config, send_text_request
from pam.text_messages import build_marking_bundle, build_reflector_text_bundle, load_text_prompt
from pam.trigger_check import predictor_fsm

PROJECT = Path(__file__).resolve().parent.parent
TEXT_CONFIG = PROJECT / "config" / "openrouter_text.json"
FAKE_KEY = "test-only-fake-credential"
TASKS = ["Pick up the cup and place it in the dishwasher.", "Turn off the room light."]
MEMORY = {"initial_state": "breakfast", "states": [
    {"id": "breakfast", "description": "Person eats breakfast.",
     "rules": [{"triggers": ["Person finishes the water", "Person puts down the spoon"],
                "action": "Pick up the cup and place it in the dishwasher."}],
     "next": []}]}
ASKED = [("breakfast", "Person finishes the water")]
MARKS = {"candidates": [{"state": "breakfast", "candidate": "Person finishes the water", "times": ["07:49:40"]}],
         "actions": [{"action": TASKS[0], "times": ["07:53:00"]}],
         "unseen": [{"start": "12:30:04", "end": "17:00:00"}]}
RECORD = ["07:49:32 | The person drinks water from a cup.", "07:49:34 | The person sips water from the cup.",
          "07:49:36 | The person drinks water from a cup.", "07:49:38 | The person sips water from the cup.",
          "07:49:40 | The person drinks the last of the water and puts the cup down."]


class _Response(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status = status


def completion(content, *, finish="stop", model=MODEL, provider="Alibaba"):
    return {"id": "gen-test", "model": model, "provider": provider,
            "choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def marking_bundle():
    return {"role": "marking", "model": "Qwen3.5-27B", "status": "prepared",
            "execution_mode": "offline_preparation",
            "generation": {"temperature": 0.0, "enable_thinking": False},
            "asked_candidates": [list(pair) for pair in ASKED], "asked_actions": [TASKS[0]],
            "first_time": "07:00:00", "last_time": "22:59:58", "line_seconds": 2,
            "messages": [{"role": "system", "content": "Find times."},
                         {"role": "user", "content": [{"type": "text", "text": "Record ..."}]}]}


class TextContractTests(unittest.TestCase):
    def test_candidate_memory_accepts_one_to_three_different_triggers(self):
        self.assertIs(validate_candidate_memory(MEMORY), MEMORY)

    def test_candidate_memory_rejects_none_four_or_repeated_triggers(self):
        for triggers in ([], ["a", "b", "c", "d"], ["a", "a"]):
            memory = deepcopy(MEMORY)
            memory["states"][0]["rules"][0]["triggers"] = triggers
            with self.assertRaises(ContractError, msg=triggers):
                validate_candidate_memory(memory)

    def test_candidate_memory_rejects_the_paper_one_line_trigger(self):
        memory = deepcopy(MEMORY)
        memory["states"][0]["rules"][0] = {"trigger": "a or b", "action": TASKS[0]}
        with self.assertRaises(ContractError):
            validate_candidate_memory(memory)

    def test_marks_answer_every_asked_item_exactly_once(self):
        self.assertEqual(validate_marks(MARKS, ASKED, [TASKS[0]]), MARKS)
        missing = deepcopy(MARKS)
        missing["candidates"] = []
        doubled = deepcopy(MARKS)
        doubled["actions"] = doubled["actions"] * 2
        extra = deepcopy(MARKS)
        extra["candidates"].append({"state": "study", "candidate": "x", "times": []})
        clock = deepcopy(MARKS)
        clock["actions"][0]["times"] = ["7:53"]
        backwards = deepcopy(MARKS)
        backwards["unseen"] = [{"start": "17:00:00", "end": "12:30:04"}]
        for value in (missing, doubled, extra, clock, backwards):
            with self.assertRaises(ContractError, msg=value):
                validate_marks(value, ASKED, [TASKS[0]])

    def test_marked_times_must_be_lines_of_the_record(self):
        record = ("07:00:00", "22:59:58", 2)
        self.assertEqual(validate_marks(MARKS, ASKED, [TASKS[0]], within=record), MARKS)
        late = {**MARKS, "actions": [{"action": TASKS[0], "times": ["23:00:00"]}]}
        between = {**MARKS, "actions": [{"action": TASKS[0], "times": ["07:53:01"]}]}
        unseen = {**MARKS, "unseen": [{"start": "12:30:03", "end": "17:00:00"}]}
        for value in (late, between, unseen):
            with self.assertRaises(ContractError, msg=value):
                validate_marks(value, ASKED, [TASKS[0]], within=record)

    def test_predictor_fsm_refuses_more_than_three_candidates(self):
        memory = deepcopy(MEMORY)
        memory["states"][0]["rules"][0]["triggers"] = ["a", "b", "c", "d"]
        with self.assertRaises(ContractError):
            predictor_fsm(memory, set())


class TextBundleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)
        folder = self.project / "prompts" / "text"
        folder.mkdir(parents=True)
        for name in ("reflector_text_build", "reflector_text_update", "marking"):
            (folder / f"{name}.txt").write_text(f"Prompt for {name}.", encoding="utf-8")

    def _marking(self, state="breakfast"):
        return build_marking_bundle(RECORD, candidates=[{"state": state, "candidate": "Person finishes the water"}],
                                    actions=[TASKS[0]], states={"breakfast": "Person eats breakfast."},
                                    project_dir=self.project)

    def test_each_role_keeps_its_settings_and_sends_text_only(self):
        bundles = [build_reflector_text_bundle(RECORD, TASKS, operation="build", project_dir=self.project),
                   self._marking()]
        wanted = [("reflector_text", 0.3, True), ("marking", 0.0, False)]
        for bundle, (role, temperature, thinking) in zip(bundles, wanted):
            self.assertEqual(bundle["role"], role)
            self.assertEqual(bundle["model"], "Qwen3.5-27B")
            self.assertEqual(bundle["generation"], {"temperature": temperature, "enable_thinking": thinking})
            self.assertEqual(bundle["status"], "prepared")
            self.assertTrue(all(part["type"] == "text" for part in bundle["messages"][1]["content"]), role)

    def test_prompt_text_and_hash_are_recorded(self):
        text, source = load_text_prompt("marking", self.project)
        self.assertEqual(text, "Prompt for marking.")
        self.assertEqual(source["sha256"], hashlib.sha256(b"Prompt for marking.").hexdigest())

    def test_missing_or_unknown_prompt_is_refused(self):
        (self.project / "prompts" / "text" / "marking.txt").unlink()
        for prompt_id in ("marking", "predictor_fsm", "moments"):
            with self.assertRaises(ContractError, msg=prompt_id):
                load_text_prompt(prompt_id, self.project)

    def test_first_night_takes_no_memory_and_later_nights_need_memory_and_results(self):
        with self.assertRaises(ContractError):
            build_reflector_text_bundle(RECORD, TASKS, operation="build", memory=MEMORY, project_dir=self.project)
        with self.assertRaises(ContractError):
            build_reflector_text_bundle(RECORD, TASKS, operation="update", memory=MEMORY, project_dir=self.project)
        results = [{"state": "breakfast", "candidate": "Person finishes the water", "n": 1, "k": 1, "passed": False}]
        bundle = build_reflector_text_bundle(RECORD, TASKS, operation="update", memory=MEMORY, results=results,
                                             project_dir=self.project)
        text = bundle["messages"][1]["content"][0]["text"]
        self.assertIn("Today's record", text)
        self.assertIn("\n".join(RECORD), text)
        self.assertIn('"passed": false', text)
        self.assertEqual(bundle["prompt_source"]["id"], "reflector_text_update")

    def test_reflector_input_states_the_check_window_from_the_code(self):
        bundle = build_reflector_text_bundle(RECORD, TASKS, operation="build", project_dir=self.project)
        self.assertIn("within 5 minutes after the candidate", bundle["messages"][1]["content"][0]["text"])
        with patch("pam.text_messages.FOLLOW_SECONDS", 120):
            bundle = build_reflector_text_bundle(RECORD, TASKS, operation="build", project_dir=self.project)
        self.assertIn("within 2 minutes after the candidate", bundle["messages"][1]["content"][0]["text"])

    def test_real_text_prompts_are_all_present(self):
        for prompt_id in ("reflector_text_build", "reflector_text_update", "marking"):
            load_text_prompt(prompt_id)

    def test_marking_bundle_remembers_what_was_asked(self):
        bundle = self._marking()
        self.assertEqual(bundle["asked_candidates"], [["breakfast", "Person finishes the water"]])
        self.assertEqual(bundle["asked_actions"], [TASKS[0]])

    def test_marking_may_ask_for_candidates_only_but_not_for_nothing(self):
        states = {"breakfast": "Person eats breakfast."}
        bundle = build_marking_bundle(RECORD, candidates=[{"state": "breakfast", "candidate": "Person finishes the water"}],
                                      actions=[], states=states, project_dir=self.project)
        self.assertIn("Actions to find:\n(none)", bundle["messages"][1]["content"][0]["text"])
        with self.assertRaises(ContractError):
            build_marking_bundle(RECORD, candidates=[], actions=[], states=states, project_dir=self.project)

    def test_reflector_and_marking_read_the_record_itself(self):
        reflect = build_reflector_text_bundle(RECORD, TASKS, operation="build", project_dir=self.project)
        self.assertIn("Today's record (HH:MM:SS | sentence):\n" + "\n".join(RECORD),
                      reflect["messages"][1]["content"][0]["text"])
        mark = self._marking()
        self.assertIn("Record (HH:MM:SS | sentence):\n" + "\n".join(RECORD), mark["messages"][1]["content"][0]["text"])
        self.assertEqual((mark["first_time"], mark["last_time"], mark["line_seconds"]), ("07:49:32", "07:49:40", 2))
        for lines in ([], ["The person drinks water."], ["07:49:32 | a\nb"]):
            with self.assertRaises(ContractError, msg=lines):
                build_reflector_text_bundle(lines, TASKS, operation="build", project_dir=self.project)
            with self.assertRaises(ContractError, msg=lines):
                build_marking_bundle(lines, candidates=[], actions=[TASKS[0]], states={}, project_dir=self.project)

    def test_marking_refuses_a_candidate_in_an_unknown_state(self):
        with self.assertRaises(ContractError):
            self._marking(state="study")


class TextRequestTests(unittest.TestCase):
    def setUp(self):
        self.config = load_text_config(TEXT_CONFIG)
        self.bundle = marking_bundle()

    def test_request_is_text_only_with_the_role_limit(self):
        payload = build_text_request(self.bundle, self.config)
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["max_tokens"], self.config["max_tokens"]["marking"])
        self.assertEqual(payload["reasoning"], {"enabled": False})
        self.assertEqual(payload["temperature"], 0.0)
        self.assertEqual(payload["messages"][1]["content"], [{"type": "text", "text": "Record ..."}])
        self.assertEqual(payload["provider"]["order"], ["alibaba"])

    def test_images_wrong_thinking_paper_or_removed_roles_are_refused(self):
        with_image = deepcopy(self.bundle)
        with_image["messages"][1]["content"].append({"type": "image_file", "path": "x.png", "mime_type": "image/png"})
        thinking = deepcopy(self.bundle)
        thinking["generation"]["enable_thinking"] = True
        paper_role = deepcopy(self.bundle)
        paper_role["role"] = "reflector"
        removed_role = deepcopy(self.bundle)
        removed_role["role"] = "moments"
        for bundle in (with_image, thinking, paper_role, removed_role):
            with self.assertRaises(OpenRouterError):
                build_text_request(bundle, self.config)

    def test_text_config_needs_a_limit_for_exactly_the_text_roles(self):
        for limits in ({"reflector_text": 10}, {"marking": 10},
                       {"reflector_text": 10, "marking": 10, "moments": 10}):
            config = deepcopy(self.config)
            config["max_tokens"] = limits
            with self.assertRaises(OpenRouterError, msg=limits):
                build_text_request(self.bundle, config)

    def test_send_posts_once_without_images(self):
        opener = Mock()
        opener.open.return_value = _Response(json.dumps(completion('{"x": 1}')).encode("utf-8"))
        with patch("pam.openrouter.build_opener", return_value=opener):
            result = send_text_request(build_text_request(self.bundle, self.config), self.config,
                                       role="marking", api_key=FAKE_KEY)
        self.assertEqual(opener.open.call_count, 1)
        sent = json.loads(opener.open.call_args[0][0].data)
        self.assertNotIn("image_url", json.dumps(sent))
        self.assertEqual(result["response"]["choices"][0]["message"]["content"], '{"x": 1}')

    def test_send_refuses_a_payload_for_another_role(self):
        payload = build_text_request(self.bundle, self.config)
        with patch("pam.openrouter.build_opener") as opener:
            with self.assertRaises(OpenRouterError):
                send_text_request(payload, self.config, role="reflector_text", api_key=FAKE_KEY)
            opener.assert_not_called()


class TextInferenceTests(unittest.TestCase):
    def test_each_role_output_is_checked(self):
        for bundle, output in (({"role": "reflector_text"}, MEMORY), (marking_bundle(), MARKS)):
            checked = inspect_text_completion(completion(json.dumps(output)), bundle)
            self.assertEqual(checked["status"], "valid", bundle["role"])
            self.assertEqual(checked["output"], output)

    def test_a_removed_role_is_not_accepted(self):
        bundle = {**marking_bundle(), "role": "moments"}
        self.assertEqual(inspect_text_completion(completion(json.dumps(MARKS)), bundle)["status"], "invalid")

    def test_a_marked_time_that_is_not_a_line_of_the_record_is_invalid(self):
        odd = {**MARKS, "actions": [{"action": TASKS[0], "times": ["07:53:01"]}]}
        self.assertEqual(inspect_text_completion(completion(json.dumps(odd)), marking_bundle())["status"], "invalid")

    def test_truncated_fenced_wrong_shape_or_wrong_model_is_invalid(self):
        good = json.dumps(MARKS)
        for response in (completion(good, finish="length"), completion("```json\n" + good + "\n```"),
                         completion(json.dumps(MEMORY)), completion(good, model="other/model")):
            self.assertEqual(inspect_text_completion(response, marking_bundle())["status"], "invalid")

    def test_infer_writes_the_checked_result_without_the_key(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            bundle_path = folder / "bundle.json"
            bundle_path.write_text(json.dumps(marking_bundle()), encoding="utf-8")
            output = folder / "out"
            output.mkdir()
            opener = Mock()
            opener.open.return_value = _Response(json.dumps(completion(json.dumps(MARKS))).encode("utf-8"))
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": FAKE_KEY}), \
                    patch("pam.openrouter.build_opener", return_value=opener):
                result = infer_text_bundle(bundle_path, TEXT_CONFIG, output)
            self.assertEqual(result["status"], "valid")
            self.assertEqual(result["output"], MARKS)
            self.assertEqual(json.loads((output / "result.json").read_text(encoding="utf-8"))["status"], "valid")
            self.assertTrue((output / "request_record.json").exists())
            self.assertTrue((output / "api_response.raw.json").exists())
            written = "".join(path.read_text(encoding="utf-8") for path in output.iterdir())
            self.assertNotIn(FAKE_KEY, written)

    def test_infer_without_a_key_makes_no_call(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            bundle_path = folder / "bundle.json"
            bundle_path.write_text(json.dumps(marking_bundle()), encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), patch("pam.openrouter.build_opener") as opener:
                with self.assertRaises(OpenRouterError):
                    infer_text_bundle(bundle_path, TEXT_CONFIG, folder)
                opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
