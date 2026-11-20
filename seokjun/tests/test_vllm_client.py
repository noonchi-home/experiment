"""vLLM transport tests with a mocked streaming HTTP response; no server is contacted."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from pam.messages import read_json
from pam.routine_experiment import FAKE_MEMORY, fake_call, run_experiment
from pam.vllm_client import build_payload, infer_bundle_vllm


class _Stream:
    def __init__(self, chunks):
        self.lines = [("data: " + json.dumps(chunk) + "\n").encode() for chunk in chunks] + [b"data: [DONE]\n"]

    def __enter__(self):
        return iter(self.lines)

    def __exit__(self, *args):
        return False


def _chunks(content, reasoning="", finish="stop"):
    chunks = []
    if reasoning:
        chunks.append({"id": "r1", "model": "Qwen/Qwen3.5-27B", "choices": [{"delta": {"reasoning_content": reasoning}}]})
    half = len(content) // 2
    for piece in (content[:half], content[half:]):
        chunks.append({"id": "r1", "model": "Qwen/Qwen3.5-27B", "choices": [{"delta": {"content": piece}}]})
    chunks.append({"id": "r1", "model": "Qwen/Qwen3.5-27B", "choices": [{"delta": {}, "finish_reason": finish}]})
    chunks.append({"id": "r1", "model": "Qwen/Qwen3.5-27B", "choices": [], "usage": {"prompt_tokens": 10}})
    return chunks


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg is not installed")
class VllmClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / "videos").mkdir()
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=160x90:rate=24",
                        "-pix_fmt", "yuv420p", str(root / "videos" / "A1.mp4")], check=True)
        run_experiment(videos_dir=root / "videos", output_dir=root / "run", call=fake_call, rounds=("A1",),
                       width=64, height=36, reflect_last=True)
        cls.predictor = root / "run" / "A1" / "predictor" / "t0002" / "input_bundle.json"
        cls.reflector = root / "run" / "A1" / "reflection" / "input_bundle.json"
        cls.root = root

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def out(self, name):
        directory = self.root / name
        directory.mkdir()
        return directory

    def test_payload_sets_thinking_per_role_and_keeps_every_image(self):
        predictor = build_payload(read_json(self.predictor))
        self.assertEqual(predictor["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(sum(p["type"] == "image_url" for p in predictor["messages"][1]["content"]), 3)
        self.assertEqual(predictor["temperature"], 0.3)
        self.assertTrue(predictor["stream"])
        reflector = build_payload(read_json(self.reflector))
        self.assertEqual(reflector["chat_template_kwargs"], {"enable_thinking": True})
        self.assertEqual(sum(p["type"] == "image_url" for p in reflector["messages"][1]["content"]), 200)

    def test_valid_prediction_from_streamed_chunks(self):
        content = json.dumps({"observation": "A person reads.", "reasoning": "No rule fires.", "task_index": -1})
        with patch("pam.vllm_client.urlopen", return_value=_Stream(_chunks(content))):
            result = infer_bundle_vllm(self.predictor, self.out("p_ok"), base_url="http://x")
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["prediction"]["task_index"], -1)
        self.assertEqual(result["usage"], {"prompt_tokens": 10})

    def test_predictor_thinking_or_truncation_is_invalid_not_no_action(self):
        content = json.dumps({"observation": "x", "reasoning": "y", "task_index": 0})
        with patch("pam.vllm_client.urlopen", return_value=_Stream(_chunks(content, reasoning="thought"))):
            self.assertEqual(infer_bundle_vllm(self.predictor, self.out("p_think"), base_url="http://x")["status"], "invalid")
        with patch("pam.vllm_client.urlopen", return_value=_Stream(_chunks(content, finish="length"))):
            self.assertEqual(infer_bundle_vllm(self.predictor, self.out("p_len"), base_url="http://x")["status"], "invalid")

    def test_reflector_memory_is_strict_json_and_saved(self):
        with patch("pam.vllm_client.urlopen", return_value=_Stream(_chunks(json.dumps(FAKE_MEMORY), reasoning="plan"))):
            result = infer_bundle_vllm(self.reflector, self.out("r_ok"), base_url="http://x")
        self.assertEqual(result["status"], "valid")
        self.assertEqual(read_json(self.root / "r_ok" / "memory.json"), FAKE_MEMORY)
        fenced = "```json\n" + json.dumps(FAKE_MEMORY) + "\n```"
        with patch("pam.vllm_client.urlopen", return_value=_Stream(_chunks(fenced))):
            self.assertEqual(infer_bundle_vllm(self.reflector, self.out("r_fence"), base_url="http://x")["status"], "invalid")

    def test_connection_error_is_an_api_error(self):
        with patch("pam.vllm_client.urlopen", side_effect=URLError("down")):
            result = infer_bundle_vllm(self.predictor, self.out("p_err"), base_url="http://x")
        self.assertEqual(result["status"], "api_error")
        self.assertTrue((self.root / "p_err" / "api_error.json").is_file())

    def test_request_record_keeps_hashes_not_image_bytes(self):
        content = json.dumps({"observation": "x", "reasoning": "y", "task_index": -1})
        with patch("pam.vllm_client.urlopen", return_value=_Stream(_chunks(content))):
            infer_bundle_vllm(self.predictor, self.out("p_rec"), base_url="http://x")
        text = (self.root / "p_rec" / "request_record.json").read_text(encoding="utf-8")
        self.assertNotIn("base64,", text)
        self.assertIn("sha256", text)


if __name__ == "__main__":
    unittest.main()
