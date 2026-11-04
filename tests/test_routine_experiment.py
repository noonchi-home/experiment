"""Offline end-to-end tests of the routine flow with a fake model on generated test patterns."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pam.messages import read_json
from pam.routine_experiment import FAKE_MEMORY, SUMMARY_HEADER, fake_call, run_experiment


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg is not installed")
class RoutineExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.videos = cls.root / "videos"
        cls.videos.mkdir()
        for name in ("A1", "A2"):
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc=duration=4:size=160x90:rate=24", "-pix_fmt", "yuv420p",
                            str(cls.videos / f"{name}.mp4")], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_fake(self, output, call=fake_call, **options):
        return run_experiment(videos_dir=self.videos, output_dir=output, call=call, rounds=("A1", "A2"),
                              width=64, height=36, **options)

    def test_two_rounds_build_then_use_memory(self):
        output = self.root / "run"
        report = self.run_fake(output)
        self.assertEqual(report["status"], "completed", report.get("error"))
        first, second = report["rounds"]
        self.assertEqual((first["memory_kind"], first["frames_1fps"], first["predictions"]), ("none", 4, 4))
        self.assertEqual(first["reflection"]["operation"], "build")
        self.assertEqual(first["reflection"]["frames"], 200)
        self.assertEqual(second["memory_kind"], "fsm")
        self.assertEqual(read_json(output / "A2" / "memory_used.json"), FAKE_MEMORY)
        self.assertIsNone(second["reflection"])
        self.assertFalse(report["evaluation_labels_sent_to_models"])

    def test_predictor_window_grows_to_nine_one_second_frames(self):
        output = self.root / "window"
        self.run_fake(output)
        counts = [read_json(output / "A1" / "predictor" / f"t{t:04d}" / "input_bundle.json")["frame_count"]
                  for t in range(4)]
        self.assertEqual(counts, [1, 2, 3, 4])
        bundle = read_json(output / "A2" / "predictor" / "t0003" / "input_bundle.json")
        system = bundle["messages"][0]["content"]
        self.assertEqual(bundle["predictor_window"]["source"], "explicit_user_override")
        self.assertIn("up to 9 frames", system)
        self.assertIn("single camera view", system)
        self.assertNotIn("two back-facing", system)
        self.assertIn(json.dumps(FAKE_MEMORY, ensure_ascii=False, indent=2), system)
        self.assertIn("Turn off the bedside lamp.", system)

    def test_update_receives_the_predictor_summary_and_no_feedback(self):
        output = self.root / "update"
        report = self.run_fake(output, reflect_last=True)
        self.assertEqual(report["rounds"][1]["reflection"]["operation"], "update")
        summary = (output / "A2" / "summary.txt").read_text(encoding="utf-8")
        self.assertTrue(summary.startswith(SUMMARY_HEADER))
        self.assertIn("t=0s: Fake scene description", summary)
        bundle = read_json(output / "A2" / "reflection" / "input_bundle.json")
        texts = [part["text"] for part in bundle["messages"][1]["content"] if part["type"] == "text"]
        self.assertIn(summary, texts[-1])
        self.assertNotIn("Human feedback", texts[-1])
        system = bundle["messages"][0]["content"]
        self.assertIn("`in the dishwasher`", system)
        self.assertIn("`Turn off the <object>.`", system)
        build = read_json(output / "A1" / "reflection" / "input_bundle.json")
        self.assertEqual(build["operation"], "build")
        self.assertNotIn("summary", build["inputs"])

    def test_resume_reuses_valid_results_without_new_calls(self):
        output = self.root / "resume"
        self.run_fake(output)
        calls = []

        def counting(bundle_path, directory):
            calls.append(bundle_path)
            return fake_call(bundle_path, directory)

        report = self.run_fake(output, call=counting, resume=True)
        self.assertEqual(report["status"], "completed", report.get("error"))
        self.assertEqual(calls, [])

    def test_api_error_stops_the_run(self):
        report = self.run_fake(self.root / "error", call=lambda bundle_path, directory: {"status": "api_error"})
        self.assertEqual(report["status"], "failed")
        self.assertIn("API error", report["error"])

    def test_bundles_pass_the_real_transport_checks_without_network(self):
        from pam.inference import _verify_prepared_images
        from pam.messages import PROJECT_ROOT
        from pam.openrouter import build_request, load_openrouter_config
        output = self.root / "transport"
        self.run_fake(output)
        predictor = read_json(output / "A2" / "predictor" / "t0003" / "input_bundle.json")
        reflector = read_json(output / "A1" / "reflection" / "input_bundle.json")
        _verify_prepared_images(predictor)
        _verify_prepared_images(reflector)
        payload = build_request(predictor, load_openrouter_config(PROJECT_ROOT / "config" / "openrouter.json"))
        self.assertEqual(sum(part["type"] == "image_url" for part in payload["messages"][1]["content"]), 4)
        self.assertEqual(payload["reasoning"], {"enabled": False})
        payload = build_request(reflector, load_openrouter_config(
            PROJECT_ROOT / "config" / "openrouter_reflection.json"))
        self.assertEqual(sum(part["type"] == "image_url" for part in payload["messages"][1]["content"]), 200)
        self.assertEqual(payload["reasoning"], {"enabled": True})

    def test_list_memory_condition_uses_the_list_prompts(self):
        from pam.routine_experiment import FAKE_LIST_MEMORY
        output = self.root / "list"
        report = self.run_fake(output, reflect_last=True, memory_kind="list")
        self.assertEqual(report["status"], "completed", report.get("error"))
        self.assertEqual(report["condition"], "list_memory")
        build = read_json(output / "A1" / "reflection" / "input_bundle.json")
        self.assertEqual(build["prompt_source"]["id"], "reflector_list_build")
        self.assertIn("`in the dishwasher`", build["messages"][0]["content"])
        predictor = read_json(output / "A2" / "predictor" / "t0003" / "input_bundle.json")
        self.assertEqual(predictor["prompt_source"]["id"], "predictor_list")
        self.assertEqual(read_json(output / "A2" / "memory_used.json"), FAKE_LIST_MEMORY)
        update = read_json(output / "A2" / "reflection" / "input_bundle.json")
        self.assertEqual(update["prompt_source"]["id"], "reflector_list_update")

    def test_existing_output_is_not_reused_without_resume(self):
        output = self.root / "exists"
        output.mkdir()
        with self.assertRaises(ValueError):
            self.run_fake(output)


if __name__ == "__main__":
    unittest.main()
