"""Reconstruct saved requests from portable photos; no model or network calls."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pam.inference import _request_record, inspect_completion
from pam.messages import build_predictor_messages
from pam.observations import compose_observations, load_observations
from pam.openrouter import build_request, load_openrouter_config
from pam.scenarios import load_scenario, load_scenario_memory, load_scenario_tasks


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(example: Path) -> dict:
    example = example.resolve()
    evidence = read(example / "evidence.json")
    scenario = load_scenario(example / "scenario/scenario.json")
    config = load_openrouter_config(ROOT / "config/openrouter.json")
    checked = []
    with tempfile.TemporaryDirectory() as temporary:
        for case in evidence["cases"]:
            identifier = case["case"]
            observations = load_observations(example / f"{identifier}_observations.json")
            frames = compose_observations(observations, Path(temporary) / identifier)
            if len(frames) != 5 or len(case["frames"]) != 5:
                raise ValueError("Expected five temporal image pairs.")
            for frame, expected in zip(frames, case["frames"]):
                if (frame["timestamp"] != expected["timestamp"]
                        or digest(frame["image_path"]) != expected["combined_png_sha256"]
                        or digest(frame["left_image"]) != expected["left_sha256"]
                        or digest(frame["right_image"]) != expected["right_sha256"]):
                    raise ValueError(f"Photo or timestamp mismatch: {identifier}")
            bundle = build_predictor_messages(frames, load_scenario_tasks(scenario),
                                               memory_kind="fsm", memory=load_scenario_memory(scenario, "fsm"),
                                               scenario=scenario)
            recorded_request = read(example / identifier / "request_record.json")
            if _request_record(build_request(bundle, config)) != recorded_request:
                raise ValueError(f"Reconstructed request differs from saved actual request: {identifier}")
            result_path = example / identifier / "result.json"
            raw_path = example / identifier / "api_response.raw.json"
            if digest(result_path) != case["result_sha256"] or digest(raw_path) != case["raw_response_sha256"]:
                raise ValueError("A saved response changed.")
            raw, result = read(raw_path), read(result_path)
            parsed = inspect_completion(raw, bundle)
            if (parsed["status"] != "valid" or parsed["prediction"] != result["prediction"]
                    or parsed["raw_response"] != result["raw_response"]
                    or raw["id"] != case["response_id"] or result["response_id"] != raw["id"]
                    or raw["provider"] != evidence["provider"] or result["action_executed"] is not False):
                raise ValueError("Raw response and recorded outcome disagree.")
            actual = parsed["prediction"]["task_index"]
            if actual != case["actual_task_index"] or (actual == case["expected_task_index"]) != case["passed"]:
                raise ValueError("Outcome or evaluation label was altered.")
            checked.append({"case": identifier, "request_reconstructed": True,
                            "response_verified": True, "semantic_passed": case["passed"]})
    return {"verification": "passed", "api_calls": 0, "cases": checked,
            "note": "Local consistency checks, not a new inference or provider-signed authentication."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example", type=Path, default=ROOT / "examples/breakfast_2026-10-25")
    args = parser.parse_args()
    print(json.dumps(verify(args.example), ensure_ascii=False))
