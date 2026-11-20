"""Reuse verified baseline responses; user-authorized 150 -> 100 -> 50 reflection.

Every new call and any failed first attempt are preserved. No scene is rerendered.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pam.__main__ import main as prepare
from pam.inference import infer_bundle
from pam.memory_store import initialize_store, get_memory_for_day, commit_reflection
from pam.openrouter import load_openrouter_config
from pam.reflection_experiment import CASE_IDS, _frame_fingerprint


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def proof(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def run(baseline_dir: Path, output: Path, profile: Path):
    baseline_dir, output = baseline_dir.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    old_report = read(baseline_dir / "report.json")
    report = {"schema_version": 1, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
              "source_day": old_report["source_day"], "effective_day": old_report["effective_day"],
              "output_dir": str(output), "baseline_reference": proof(baseline_dir / "report.json"),
              "reused_baseline_calls": 3, "planned_api_calls": 4, "maximum_new_api_calls": 5,
              "api_requests_attempted": 0, "model_responses_received": 0, "valid_results": 0,
              "action_executed": False, "stages": [], "comparisons": None,
              "paper_reflector_frame_count": 200, "requested_reflector_frame_counts": [150, 100, 50],
              "fallback_authorized_by_user": True, "evaluation_labels_sent_to_models": False,
              "current_stage": "preflight", "source_inputs": old_report["source_inputs"]}

    def event(stage, status):
        report["current_stage"] = stage
        save(output / "report.json", report)
        item = {"time": datetime.now(timezone.utc).isoformat(), "stage": stage, "status": status,
                "new_api_requests": report["api_requests_attempted"]}
        with (output / "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item) + "\n")
        print(json.dumps(item), flush=True)

    def call(stage_id, phase, bundle_path, config_path):
        bundle = read(bundle_path)
        stage = {"id": stage_id, "phase": phase, "status": "calling_model",
                 "prepared_bundle": str(bundle_path), "frames": _frame_fingerprint(bundle)}
        report["stages"].append(stage)
        result_dir = output / stage_id / "inference"
        result_dir.mkdir(parents=True, exist_ok=False)
        event(stage_id, "calling_model")
        if report["api_requests_attempted"] >= report["maximum_new_api_calls"]:
            raise ValueError("The user-authorized new-call maximum is exhausted.")
        state = {"api_request_attempted": False, "model_response_received": False}
        try:
            result = infer_bundle(bundle_path, config_path, result_dir, run_state=state)
        finally:
            report["api_requests_attempted"] += int(state["api_request_attempted"])
            report["model_responses_received"] += int(state["model_response_received"])
            stage.update(state)
            save(output / "report.json", report)
        stage["status"] = result["status"]
        stage["result_path"] = str(result_dir / ("api_error.json" if result["status"] == "api_error" else "result.json"))
        if result["status"] == "valid":
            if not result.get("model_response_received") or result.get("action_executed") is not False:
                raise ValueError("Not a valid non-executing model response.")
            report["valid_results"] += 1
            if phase != "reflection":
                stage["task_index"] = result["prediction"]["task_index"]
                stage["selected_action_ko"] = result["selected_action_ko"]
        event(stage_id, stage["status"])
        return stage, result

    try:
        event("preflight", "verifying_reused_baseline")
        for item in old_report["source_inputs"].values():
            if proof(item["path"])["sha256"] != item["sha256"]:
                raise ValueError("A baseline source input changed; cannot reuse its results.")
        for item in old_report.get("fixed_model_inputs", {}).values():
            if proof(item["path"])["sha256"] != item["sha256"]:
                raise ValueError("Baseline model conditions changed.")
        baseline_stages = {}
        for case in CASE_IDS:
            stage = deepcopy(next(s for s in old_report["stages"] if s["id"] == "before_" + case))
            result = read(stage["result_path"])
            if result["status"] != "valid" or result["model_response_received"] is not True:
                raise ValueError("Only valid real baseline responses can be reused.")
            stage["reused_without_new_api_call"] = True
            baseline_stages[case] = stage
            report["stages"].append(stage)
        inputs = output / "inputs"
        inputs.mkdir()
        for source, target in (("summary", "summary.txt"), ("feedback", "feedback.txt"), ("expectations", "expectations.json")):
            (inputs / target).write_bytes(Path(old_report["source_inputs"][source]["path"]).read_bytes())
        config = load_openrouter_config(profile)
        original_config = read(baseline_dir / "inputs" / "openrouter.json")
        if {k: v for k, v in config.items() if k not in ("provenance", "reflector_frame_count")} != {
                k: v for k, v in original_config.items() if k != "provenance"}:
            raise ValueError("Only the requested reflector frame count may differ from the baseline profile.")
        store = output / "memory_store"
        initialize_store(store, Path(old_report["old_memory"]["memory_path"]), report["source_day"])
        old_memory, old_record = get_memory_for_day(store, report["source_day"])
        report.update(memory_store=str(store), old_memory=old_record)
        scenario = old_report["source_inputs"]["scenario"]["path"]
        training = old_report["source_inputs"]["training"]["path"]
        report["maximum_new_api_calls"] = 6
        for count in (150, 100, 50):
            identifier = "reflection" if count == 150 else f"reflection_{count}"
            config["reflector_frame_count"] = count
            config_path = inputs / f"openrouter_{count}.json"
            save(config_path, config)
            prepared = output / identifier / "prepared"
            if prepare(["prepare-reflector", "--observations", training, "--scenario", scenario,
                        "--memory-kind", "fsm", "--operation", "update", "--memory-store", str(store),
                        "--day", report["source_day"], "--summary", str(inputs / "summary.txt"),
                        "--feedback", str(inputs / "feedback.txt"), "--reflector-frame-count", str(count),
                        "--output", str(prepared)]) != 0:
                raise ValueError("Reflection preparation failed.")
            bundle_path = prepared / "input_bundle.json"
            stage, result = call(identifier, "reflection", bundle_path, config_path)
            if result["status"] == "valid":
                report["reflector_frame_count"] = count
                break
            if count != 50:
                next_count = 100 if count == 150 else 50
                report["fallback"] = {"from": count, "to": next_count, "cause_result": stage["result_path"],
                                      "authorized_by_user": True, "baseline_repeated": False}
                report.setdefault("fallback_history", []).append(deepcopy(report["fallback"]))
                report["planned_api_calls"] += 1
                event("fallback", f"user_authorized_{next_count}_frames")
        else:
            raise ValueError("150-, 100-, and 50-frame reflection attempts failed; no further retry.")
        new_record = commit_reflection(store, Path(stage["result_path"]), bundle_path,
                                       report["source_day"], report["effective_day"])
        new_memory, _ = get_memory_for_day(store, report["effective_day"])
        report.update(new_memory=new_record, memory_changed=old_memory != new_memory)
        save(output / "memory_diff.json", {"old_memory": old_memory, "new_memory": new_memory})
        expected = {case["id"]: case for case in read(inputs / "expectations.json")["cases"]}
        comparisons = []
        for case in CASE_IDS:
            before = baseline_stages[case]
            old_bundle = read(before["prepared_bundle"])
            prepared = output / ("after_" + case) / "prepared"
            if prepare(["prepare-predictor", "--observations", old_report["source_inputs"][case]["path"],
                        "--scenario", scenario, "--memory-kind", "fsm", "--memory-store", str(store),
                        "--day", report["effective_day"], "--at", old_bundle["frames"][-1]["timestamp"],
                        "--output", str(prepared)]) != 0:
                raise ValueError("After prediction preparation failed.")
            bundle_path = prepared / "input_bundle.json"
            if _frame_fingerprint(read(bundle_path)) != _frame_fingerprint(old_bundle):
                raise ValueError("Before and after images differ.")
            after, result = call("after_" + case, "after", bundle_path, config_path)
            if result["status"] != "valid":
                raise ValueError("An after response is invalid.")
            case_expected = expected[case]
            comparisons.append({"case_id": case, "label_ko": case_expected["label_ko"],
                                "expected_task_indices": case_expected["expected_task_indices"],
                                "before_task_index": before["task_index"], "after_task_index": after["task_index"],
                                "before_passed": before["task_index"] in case_expected["expected_task_indices"],
                                "after_passed": after["task_index"] in case_expected["expected_task_indices"],
                                "same_images": True, "before_result_path": before["result_path"],
                                "after_result_path": after["result_path"]})
        report.update(status="completed", comparisons=comparisons,
                      before_passed=sum(c["before_passed"] for c in comparisons),
                      after_passed=sum(c["after_passed"] for c in comparisons),
                      all_after_passed=all(c["after_passed"] for c in comparisons))
    except Exception as error:
        report.update(status="failed", failed_stage=report["current_stage"],
                      error_type=type(error).__name__, error=str(error))
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    event("experiment", report["status"])
    return report


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider-config", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.baseline_dir, args.output, args.provider_config)
    raise SystemExit(0 if result["status"] == "completed" else 2)
