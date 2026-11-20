"""Local synthetic artifact tests, not live API results or learned memories."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pam.memory_store import (
    MemoryStoreError, commit_reflection, get_memory_for_day, initialize_store,
)


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _proof(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "memory_store"
        self.seed_path = self.root / "original_seed.json"
        self.source_day, self.next_day = "2026-10-24", "2026-10-25"
        self.seed = {"initial_state": "fixture", "states": [
            {"id": "fixture", "description": "Initial schema fixture.", "rules": [], "next": []}]}
        _write(self.seed_path, self.seed)
        self.seed_bytes = self.seed_path.read_bytes()
        initialize_store(self.store, self.seed_path, self.source_day)
        _, seed_record = get_memory_for_day(self.store, self.source_day)
        self.seed_copy = Path(seed_record["memory_path"])

        self.run = self.root / "mock_artifacts"
        self.run.mkdir()
        self.bundle_path = self.run / "input_bundle.json"
        self.result_path = self.run / "result.json"
        self.summary = self.run / "summary.txt"
        self.summary.write_text("Synthetic test only; no robot action occurred.\n", encoding="utf-8")
        self.observations = self.run / "observations.json"
        _write(self.observations, {"purpose": "Memory storage unit-test metadata fixture"})
        self.memory = deepcopy(self.seed)
        self.memory["states"][0]["description"] = "A different response fixture for the following day."
        self.raw_memory = json.dumps(self.memory, indent=3) + "\n"
        self.provider = {"order": ["alibaba"], "allow_fallbacks": False, "require_parameters": True}
        self.bundle = {
            "status": "prepared", "execution_mode": "offline_preparation", "role": "reflector",
            "operation": "update", "memory_kind": "fsm", "model": "Qwen3.5-27B",
            "action_executed": False, "generation": {"temperature": 0.3, "enable_thinking": True},
            "frames": [{"timestamp": "2026-10-24T12:00:00+09:00", "test_frame_index": index} for index in range(200)],
            "inputs": {"memory": _proof(self.seed_copy), "summary": _proof(self.summary),
                       "observations": _proof(self.observations)},
        }
        self.result = {
            "status": "valid", "role": "reflector", "api_request_attempted": True,
            "model_response_received": True, "action_executed": False, "finish_reason": "stop",
            "requested_model": "qwen/qwen3.5-27b", "response_model": "qwen/qwen3.5-27b",
            "memory_automatically_applied": False, "errors": [], "reasoning_requested": {"enabled": True},
            "response_id": "mock-response-for-local-tests", "provider": "Alibaba",
            "memory": self.memory, "raw_response": self.raw_memory,
        }
        self.api_response = {
            "id": self.result["response_id"], "model": self.result["response_model"], "provider": "Alibaba",
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": self.raw_memory}}],
        }
        self._save_artifacts()

    def _save_artifacts(self):
        _write(self.bundle_path, self.bundle)
        _write(self.result_path, self.result)
        _write(self.run / "api_response.raw.json", self.api_response)
        _write(self.run / "input_reference.json", {**_proof(self.bundle_path), "action_executed": False,
                                                   "provider_config": {"provider": self.provider}})
        _write(self.run / "request_record.json", {
            "model": "qwen/qwen3.5-27b", "temperature": 0.3,
            "reasoning": {"enabled": True}, "provider": self.provider,
        })

    def _commit(self):
        return commit_reflection(self.store, self.result_path, self.bundle_path, self.source_day, self.next_day)

    def test_seed_copy_is_exact_and_original_file_is_not_modified(self):
        memory, record = get_memory_for_day(self.store, self.source_day)
        self.assertEqual(memory, self.seed)
        self.assertEqual(record["origin"], "provided_seed")
        self.assertEqual(self.seed_copy.read_bytes(), self.seed_bytes)
        self.assertEqual(self.seed_path.read_bytes(), self.seed_bytes)
        self.assertEqual(record["sha256"], hashlib.sha256(self.seed_bytes).hexdigest())

    def test_commit_freezes_next_day_without_changing_source_day(self):
        record = self._commit()
        old_memory, old_record = get_memory_for_day(self.store, self.source_day)
        new_memory, new_record = get_memory_for_day(self.store, self.next_day)
        self.assertEqual(old_memory, self.seed)
        self.assertEqual(new_memory, self.memory)
        self.assertEqual(old_record["version_id"], "000_seed")
        self.assertEqual(new_record, record)
        self.assertEqual(Path(record["memory_path"]).read_bytes(), self.raw_memory.encode("utf-8"))
        self.assertEqual(self.seed_copy.read_bytes(), self.seed_bytes)
        self.assertEqual(self.seed_path.read_bytes(), self.seed_bytes)

    def test_explicit_150_frame_experiment_is_committed_with_its_deviation_recorded(self):
        self.bundle.update(frame_count=150, frame_count_source="explicit_user_override")
        self.bundle["frames"] = self.bundle["frames"][:150]
        self._save_artifacts()
        reference_path = self.run / "input_reference.json"
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        reference["provider_config"]["reflector_frame_count"] = 150
        _write(reference_path, reference)
        record = self._commit()
        self.assertEqual(record["evidence"]["reflector_frame_count"], 150)
        self.assertEqual(record["evidence"]["paper_reflector_frame_count"], 200)
        self.assertEqual(record["evidence"]["frame_count_source"], "explicit_user_override")
        self.assertEqual(Path(record["memory_path"]).read_bytes(), self.raw_memory.encode("utf-8"))

    def test_undeclared_reduction_to_150_is_rejected(self):
        self.bundle["frames"] = self.bundle["frames"][:150]
        self._save_artifacts()
        with self.assertRaises(MemoryStoreError):
            self._commit()

    def test_150_frame_bundle_with_200_frame_provider_evidence_is_rejected(self):
        self.bundle.update(frame_count=150, frame_count_source="explicit_user_override")
        self.bundle["frames"] = self.bundle["frames"][:150]
        self._save_artifacts()
        with self.assertRaisesRegex(MemoryStoreError, "provider profile"):
            self._commit()

    def test_proof_snapshots_preserve_original_bytes_and_optional_feedback(self):
        feedback = self.run / "feedback.txt"
        feedback.write_text("Synthetic feedback fixture, not a user instruction.\n", encoding="utf-8")
        self.bundle["inputs"]["feedback"] = _proof(feedback)
        self._save_artifacts()
        raw_before = (self.run / "api_response.raw.json").read_bytes()
        record = self._commit()
        evidence = record["evidence"]
        self.assertEqual(evidence["response_id"], self.result["response_id"])
        self.assertEqual(evidence["provider"], "Alibaba")
        self.assertEqual((self.store / evidence["artifacts"]["raw_api_response"]["snapshot"]).read_bytes(), raw_before)
        self.assertEqual((self.store / evidence["inputs"]["feedback"]["snapshot"]).read_bytes(), feedback.read_bytes())
        feedback.write_text("Changed original file after commit", encoding="utf-8")
        self.assertNotEqual((self.store / evidence["inputs"]["feedback"]["snapshot"]).read_bytes(), feedback.read_bytes())

    def test_absent_feedback_is_not_invented(self):
        record = self._commit()
        self.assertNotIn("feedback", record["evidence"]["inputs"])

    def test_unknown_day_does_not_silently_reuse_seed(self):
        before = (self.store / "manifest.json").read_bytes()
        for day in ("2026-10-23", self.next_day, "2026-10-26"):
            with self.subTest(day=day), self.assertRaises(MemoryStoreError):
                get_memory_for_day(self.store, day)
        self.assertEqual((self.store / "manifest.json").read_bytes(), before)

    def test_reinitialization_and_repeated_commit_do_not_reset_assignments(self):
        with self.assertRaises(MemoryStoreError):
            initialize_store(self.store, self.seed_path, self.next_day)
        self._commit()
        before = (self.store / "manifest.json").read_bytes()
        with self.assertRaises(MemoryStoreError):
            self._commit()
        self.assertEqual((self.store / "manifest.json").read_bytes(), before)

    def test_effective_day_must_be_exactly_the_following_calendar_day(self):
        for day in (self.source_day, "2026-10-23", "2026-10-26", "2026-11-24", "20261025"):
            with self.subTest(day=day), self.assertRaises(MemoryStoreError):
                commit_reflection(self.store, self.result_path, self.bundle_path, self.source_day, day)
        with self.assertRaises(MemoryStoreError):
            commit_reflection(self.store, self.result_path, self.bundle_path, "2026-10-25", "2026-10-26")

    def test_invalid_predictor_unexecuted_or_not_actual_results_are_rejected(self):
        changes = {"status": "invalid", "role": "predictor", "api_request_attempted": False,
                   "model_response_received": False, "action_executed": True, "finish_reason": "length",
                   "requested_model": "other/model", "response_model": "other/model",
                   "memory_automatically_applied": True, "reasoning_requested": {"enabled": False}}
        original = deepcopy(self.result)
        for key, value in changes.items():
            self.result = {**deepcopy(original), key: value}
            self._save_artifacts()
            with self.subTest(key=key), self.assertRaises(MemoryStoreError):
                self._commit()
        self.assertFalse((self.store / "evidence").exists())

    def test_wrong_operation_and_incomplete_observation_bundle_are_rejected(self):
        original = deepcopy(self.bundle)
        for key, value in (("operation", "build"), ("memory_kind", "list"), ("frames", [])):
            self.bundle = {**deepcopy(original), key: value}
            self._save_artifacts()
            with self.subTest(key=key), self.assertRaises(MemoryStoreError):
                self._commit()

    def test_source_memory_path_or_hash_mismatch_is_rejected(self):
        another = self.root / "another_seed.json"
        another.write_bytes(self.seed_bytes)
        self.bundle["inputs"]["memory"] = _proof(another)
        self._save_artifacts()
        with self.assertRaises(MemoryStoreError):
            self._commit()
        self.bundle["inputs"]["memory"] = _proof(self.seed_copy)
        self.bundle["inputs"]["memory"]["sha256"] = "0" * 64
        self._save_artifacts()
        with self.assertRaises(MemoryStoreError):
            self._commit()

    def test_changed_input_summary_and_bundle_reference_are_rejected(self):
        self.summary.write_text("Changed after preparation", encoding="utf-8")
        with self.assertRaises(MemoryStoreError):
            self._commit()
        self.bundle["inputs"]["summary"] = _proof(self.summary)
        self._save_artifacts()
        reference_path = self.run / "input_reference.json"
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        reference["sha256"] = "0" * 64
        _write(reference_path, reference)
        with self.assertRaises(MemoryStoreError):
            self._commit()

    def test_hand_modified_memory_or_raw_text_cannot_be_committed(self):
        self.result["memory"] = deepcopy(self.seed)
        self._save_artifacts()
        with self.assertRaises(MemoryStoreError):
            self._commit()
        self.result["memory"] = self.memory
        self.result["raw_response"] = self.raw_memory + " "
        self._save_artifacts()
        with self.assertRaises(MemoryStoreError):
            self._commit()

    def test_response_id_provider_or_raw_model_mismatch_is_rejected(self):
        original = deepcopy(self.api_response)
        for key, value in (("id", "a-different-response"), ("provider", "Other"), ("model", "other/model")):
            self.api_response = {**deepcopy(original), key: value}
            self._save_artifacts()
            with self.subTest(key=key), self.assertRaises(MemoryStoreError):
                self._commit()

    def test_version_tampering_is_detected_and_returned_objects_are_not_live(self):
        memory, record = get_memory_for_day(self.store, self.source_day)
        memory["states"][0]["description"] = "caller mutation"
        record["effective_day"] = self.next_day
        self.assertEqual(get_memory_for_day(self.store, self.source_day)[0], self.seed)
        self.seed_copy.write_bytes(self.seed_bytes + b" ")
        with self.assertRaises(MemoryStoreError):
            get_memory_for_day(self.store, self.source_day)

    def test_provenance_snapshot_tampering_is_detected(self):
        record = self._commit()
        snapshot = self.store / record["evidence"]["artifacts"]["raw_api_response"]["snapshot"]
        snapshot.write_bytes(snapshot.read_bytes() + b" ")
        with self.assertRaises(MemoryStoreError):
            get_memory_for_day(self.store, self.next_day)

    def test_integer_one_does_not_replace_boolean_thinking_flag(self):
        self.result["reasoning_requested"] = {"enabled": 1}
        self._save_artifacts()
        with self.assertRaises(MemoryStoreError):
            self._commit()

    def test_failed_manifest_publish_preserves_existing_day(self):
        before = (self.store / "manifest.json").read_bytes()
        with patch("pam.memory_store.os.replace", side_effect=OSError("simulated publication failure")):
            with self.assertRaises(MemoryStoreError):
                self._commit()
        self.assertEqual((self.store / "manifest.json").read_bytes(), before)
        self.assertEqual(get_memory_for_day(self.store, self.source_day)[0], self.seed)
        with self.assertRaises(MemoryStoreError):
            get_memory_for_day(self.store, self.next_day)


if __name__ == "__main__":
    unittest.main()
