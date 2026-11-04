"""Offline tests for the user-selected predictor window (9 frames, 1 s apart)."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from pam.contracts import ContractError
from pam.messages import PROJECT_ROOT, build_predictor_messages, predictor_image_count, read_json
from pam.observations import compose_observations, load_observations, select_predictor_window
from pam.openrouter import OpenRouterError, build_request, load_openrouter_config, send_request
from tools.make_processing_fixture import create_fixture

FAKE_KEY = "test-only-fake-credential"


class _Response(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status = status


class PredictorWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        create_fixture(root / "fixture", count=20)
        observations = load_observations(root / "fixture" / "observations.json")
        cls.paper_frames = compose_observations(
            select_predictor_window(observations, datetime.fromisoformat("2026-10-24T07:00:08+09:00")),
            root / "paper")
        # One-second frames 0..9 s; the window slices below are taken from these.
        cls.second_frames = compose_observations(observations[:10], root / "seconds")
        cls.tasks = read_json(PROJECT_ROOT / "config" / "paper_tasks.json")
        cls.config = load_openrouter_config(PROJECT_ROOT / "config" / "openrouter.json")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_paper_window_is_unchanged_and_declared_as_paper(self):
        result = build_predictor_messages(self.paper_frames, self.tasks)
        self.assertEqual(result["frame_count"], 5)
        self.assertEqual(result["predictor_window"]["source"], "paper")
        self.assertIn("up to 5 frames", result["messages"][0]["content"])
        self.assertEqual(predictor_image_count(result), 5)

    def test_nine_one_second_frames_are_an_explicit_override(self):
        frames = self.second_frames[1:10]
        result = build_predictor_messages(frames, self.tasks, window_frames=9, stride_seconds=1)
        self.assertEqual(result["frame_count"], 9)
        self.assertEqual(result["predictor_window"],
                         {"max_frames": 9, "stride_seconds": 1, "supplied_frames": 9,
                          "source": "explicit_user_override",
                          "paper": {"max_frames": 5, "stride_seconds": 2}})
        self.assertIn("up to 9 frames", result["messages"][0]["content"])
        images = [part for part in result["messages"][1]["content"] if part["type"] == "image_file"]
        self.assertEqual([part["path"] for part in images], [frame["image_path"] for frame in frames])
        self.assertEqual(predictor_image_count(result), 9)

    def test_start_of_video_uses_only_the_frames_collected_so_far(self):
        result = build_predictor_messages(self.second_frames[:3], self.tasks, window_frames=9, stride_seconds=1)
        self.assertEqual(result["frame_count"], 3)
        self.assertEqual(result["predictor_window"]["supplied_frames"], 3)

    def test_override_rejects_too_many_frames_and_wrong_spacing(self):
        with self.assertRaises(ContractError):
            build_predictor_messages(self.second_frames[:10], self.tasks, window_frames=9, stride_seconds=1)
        with self.assertRaises(ContractError):
            build_predictor_messages(self.second_frames[0:9:2], self.tasks, window_frames=9, stride_seconds=1)
        with self.assertRaises(ContractError):
            build_predictor_messages(self.second_frames[:3], self.tasks, window_frames=1, stride_seconds=1)

    def test_undeclared_or_inconsistent_counts_are_rejected(self):
        result = build_predictor_messages(self.second_frames[1:10], self.tasks, window_frames=9, stride_seconds=1)
        for change in ({"predictor_window": None}, {"frame_count": 8},
                       {"predictor_window": {**result["predictor_window"], "source": "paper"}}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                predictor_image_count({**result, **change})

    def test_openrouter_encodes_and_validates_the_declared_count(self):
        bundle = build_predictor_messages(self.second_frames[1:10], self.tasks, window_frames=9, stride_seconds=1)
        payload = build_request(bundle, self.config)
        self.assertEqual(sum(part["type"] == "image_url" for part in payload["messages"][1]["content"]), 9)
        body = json.dumps({"id": "x", "model": "qwen/qwen3.5-27b", "choices": [
            {"finish_reason": "stop", "message": {"content": "{}"}}]}).encode()
        opener = Mock()
        opener.open.return_value = _Response(body)
        with patch("pam.openrouter.build_opener", return_value=opener):
            send_request(payload, self.config, api_key=FAKE_KEY, predictor_images=9)
            with self.assertRaises(OpenRouterError):
                send_request(payload, self.config, api_key=FAKE_KEY)
        with self.assertRaises(OpenRouterError):
            build_request({**bundle, "predictor_window": None}, self.config)


if __name__ == "__main__":
    unittest.main()
