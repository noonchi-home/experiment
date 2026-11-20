"""Seven-call before/reflection/after experiment with no retry or manual repair.

The baseline applies the previous day's memory to held-out next-day images as a
counterfactual comparison. It does not change the store's actual day assignment.
Expectation labels are used only after model calls, never in model messages.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from .__main__ import main as prepare_main
from .contracts import ContractError
from .inference import infer_bundle
from .memory_store import commit_reflection, get_memory_for_day, initialize_store
from .messages import PROJECT_ROOT, read_json
from .observations import load_observations, select_predictor_window, select_reflector_frames
from .openrouter import load_openrouter_config
from .scenarios import load_scenario, load_scenario_tasks, scenario_file


CASE_IDS = ("wakeup", "seated_without_milk", "seated_with_milk")


class ReflectionExperimentError(ValueError):
    """The experiment cannot proceed without changing its declared conditions."""


def _save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _proof(path: Path) -> dict:
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _expectations(path: Path, task_count: int) -> dict:
    data = read_json(path)
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list) or len(cases) != 3:
        raise ReflectionExperimentError("Evaluation must define exactly the three held-out cases.")
    result = {}
    for case in cases:
        if (not isinstance(case, dict) or case.get("id") not in CASE_IDS
                or case["id"] in result or not isinstance(case.get("label_ko"), str)
                or not case["label_ko"].strip()):
            raise ReflectionExperimentError("Evaluation case identifiers or labels are invalid.")
        expected = case.get("expected_task_indices")
        if (not isinstance(expected, list) or not expected
                or any(type(index) is not int or not -1 <= index < task_count for index in expected)
                or len(set(expected)) != len(expected)):
            raise ReflectionExperimentError("Expected actions must be distinct valid task indices.")
        result[case["id"]] = case
    return result


def _frame_fingerprint(bundle: dict) -> list[dict]:
    return [{key: frame[key] for key in ("timestamp", "sha256", "left_sha256", "right_sha256")}
            for frame in bundle["frames"]]


def run_experiment(*, dataset_dir: Path, scenario_path: Path, summary_path: Path,
                   feedback_path: Path, expectations_path: Path, provider_config: Path,
                   output_dir: Path, source_day: str = "2026-10-24",
                   effective_day: str = "2026-10-25", reflection_vertical_padding_px: int = 0,
                   reflector_frame_count: int = 200) -> dict:
    """Run three old-memory predictions, one update, and three new predictions.

    A fresh output directory is mandatory. A failed preparation, API result, or
    memory commit ends this run immediately and leaves a failure report. Calling
    this function authorizes actual inference; importing the module does not.
    """
    output = Path(output_dir).resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError:
        raise ReflectionExperimentError("Choose a new experiment output directory; existing runs are never resumed.") from None
    dataset = Path(dataset_dir).resolve()
    report = {
        "schema_version": 1, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
        "source_day": source_day, "effective_day": effective_day, "output_dir": str(output),
        "planned_api_calls": 7, "calls_started": 0, "api_requests_attempted": 0,
        "model_responses_received": 0, "valid_results": 0, "action_executed": False,
        "automatic_retries": 0, "current_stage": "preflight", "stages": [],
        "baseline_mode": "Counterfactual previous-day memory on the same held-out next-day images",
        "evaluation_labels_sent_to_models": False, "comparisons": None,
        "reflection_vertical_padding_px": reflection_vertical_padding_px,
        "reflector_frame_count": reflector_frame_count,
        "paper_reflector_frame_count": 200,
        "reflector_frame_count_source": "explicit_user_override" if reflector_frame_count != 200 else "paper",
    }

    def persist():
        _save(output / "report.json", report)

    def event(stage: str, status: str):
        record = {"time": datetime.now(timezone.utc).isoformat(), "stage": stage, "status": status,
                  "api_requests_attempted": report["api_requests_attempted"],
                  "planned_api_calls": report["planned_api_calls"]}
        with (output / "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(json.dumps(record, ensure_ascii=False), flush=True)
        persist()

    def prepare_job(stage_id: str, phase: str, case_id: str | None, memory_record: dict) -> tuple[dict, Path]:
        report["current_stage"] = stage_id + ":prepare"
        for record in report["fixed_model_inputs"].values():
            if _proof(Path(record["path"]))["sha256"] != record["sha256"]:
                raise ReflectionExperimentError("A fixed scenario, task, prompt, or configuration changed during the comparison.")
        stage = {"id": stage_id, "phase": phase, "case_id": case_id, "status": "preparing",
                 "memory_version_id": memory_record["version_id"],
                 "memory_sha256": memory_record["sha256"], "memory_path": memory_record["memory_path"],
                 "api_request_attempted": False, "model_response_received": False}
        report["stages"].append(stage)
        prepared = output / stage_id / "prepared"
        args = ["prepare-reflector" if phase == "reflection" else "prepare-predictor",
                "--observations", str(training_path if phase == "reflection" else observation_paths[case_id]),
                "--scenario", str(scenario_path), "--memory-kind", "fsm", "--output", str(prepared)]
        if phase == "before":
            args += ["--memory", memory_record["memory_path"]]
            stage["counterfactual_memory_application"] = True
        else:
            args += ["--memory-store", str(store), "--day", source_day if phase == "reflection" else effective_day]
        if phase == "reflection":
            args += ["--operation", "update", "--summary", str(frozen_summary), "--feedback", str(frozen_feedback)]
            args += ["--vertical-padding-px", str(reflection_vertical_padding_px)]
            args += ["--reflector-frame-count", str(reflector_frame_count)]
        else:
            args += ["--at", final_times[case_id]]
        event(stage_id, "preparing_inputs")
        if prepare_main(args) != 0:
            stage["status"] = "preparation_failed"
            stage["preparation_error_path"] = str(prepared / "preparation_error.json")
            raise ReflectionExperimentError(f"Input preparation failed for {stage_id}; no retry was attempted.")
        bundle_path = prepared / "input_bundle.json"
        bundle = read_json(bundle_path)
        for record in report["fixed_model_inputs"].values():
            if _proof(Path(record["path"]))["sha256"] != record["sha256"]:
                raise ReflectionExperimentError("A fixed model input changed while preparing this call.")
        if (bundle["inputs"]["memory"]["path"] != memory_record["memory_path"]
                or bundle["inputs"]["memory"]["sha256"] != memory_record["sha256"]):
            raise ReflectionExperimentError("Prepared memory differs from the selected frozen version.")
        stage["prepared_bundle"] = str(bundle_path)
        stage["frames"] = _frame_fingerprint(bundle)
        if phase == "after" and stage["frames"] != before_frames[case_id]:
            raise ReflectionExperimentError("Held-out images changed between before and after predictions.")
        if phase == "before":
            before_frames[case_id] = stage["frames"]
        stage["status"] = "prepared"
        return stage, bundle_path

    def invoke(stage: dict, bundle_path: Path) -> dict:
        report["current_stage"] = stage["id"] + ":inference"
        inference_dir = output / stage["id"] / "inference"
        inference_dir.mkdir(exist_ok=False)
        stage["inference_output"] = str(inference_dir)
        stage["status"] = "calling_model"
        stage["network_attempt_status"] = "unknown_until_return"
        report["calls_started"] += 1
        if report["calls_started"] > 7:
            raise ReflectionExperimentError("The declared seven-call limit would be exceeded.")
        state = {"api_request_attempted": False, "model_response_received": False}
        event(stage["id"], "calling_model")
        try:
            result = infer_bundle(bundle_path, frozen_provider, inference_dir, run_state=state)
        except Exception:
            stage["status"] = "inference_exception"
            raise
        else:
            state["api_request_attempted"] = result.get("api_request_attempted") is True
            state["model_response_received"] = result.get("model_response_received") is True
            stage["status"] = result.get("status", "invalid")
            stage["result_path"] = str(inference_dir / ("api_error.json" if result.get("status") == "api_error" else "result.json"))
            if (inference_dir / "api_response.raw.json").is_file():
                stage["raw_response_path"] = str(inference_dir / "api_response.raw.json")
        finally:
            stage["api_request_attempted"] = state["api_request_attempted"] is True
            stage["model_response_received"] = state["model_response_received"] is True
            stage["network_attempt_status"] = "attempted" if stage["api_request_attempted"] else "not_attempted"
            report["api_requests_attempted"] += int(stage["api_request_attempted"])
            report["model_responses_received"] += int(stage["model_response_received"])
            persist()
        if (result.get("status") != "valid" or not stage["api_request_attempted"]
                or not stage["model_response_received"] or result.get("action_executed") is not False):
            raise ReflectionExperimentError(f"Model result for {stage['id']} is not a valid actual response; later calls were stopped.")
        report["valid_results"] += 1
        stage["response_id"] = result.get("response_id")
        if stage["phase"] != "reflection":
            stage["task_index"] = result["prediction"]["task_index"]
            stage["selected_action_ko"] = result.get("selected_action_ko")
        event(stage["id"], "valid_response_received")
        return result

    try:
        persist()
        if type(reflection_vertical_padding_px) is not int or reflection_vertical_padding_px < 0:
            raise ReflectionExperimentError("Reflection padding must be a nonnegative integer.")
        if type(reflector_frame_count) is not int or reflector_frame_count not in (50, 100, 150, 200):
            raise ReflectionExperimentError("Reflector uses paper 200 or user-requested 50/100/150 temporal frames.")
        source_date, next_date = date.fromisoformat(source_day), date.fromisoformat(effective_day)
        if (source_date.isoformat() != source_day or next_date.isoformat() != effective_day
                or next_date != source_date + timedelta(days=1)):
            raise ReflectionExperimentError("Use a source day and the immediately following calendar day.")
        scenario_path = Path(scenario_path).resolve()
        scenario = load_scenario(scenario_path)
        tasks = load_scenario_tasks(scenario)
        expected = _expectations(Path(expectations_path), len(tasks))
        seed = scenario_file(scenario, "memory", "fsm")
        provider = load_openrouter_config(Path(provider_config))
        if provider.get("reflector_frame_count", 200) != reflector_frame_count:
            raise ReflectionExperimentError("The provider profile and selected reflector frame count differ.")
        for path in (summary_path, feedback_path):
            if not Path(path).read_text(encoding="utf-8-sig").strip():
                raise ReflectionExperimentError("Reflection summary and feedback must be nonempty text.")
        training_path = dataset / "training_observations.json"
        training = select_reflector_frames(load_observations(training_path), count=reflector_frame_count)
        if any(observation.timestamp.date() != source_date for observation in training):
            raise ReflectionExperimentError("Training observations must belong to the source day.")
        observation_paths = {case_id: dataset / f"{case_id}_observations.json" for case_id in CASE_IDS}
        final_times = {}
        for case_id, path in observation_paths.items():
            observations = load_observations(path)
            at = observations[-1].timestamp
            selected = select_predictor_window(observations, at)
            if any(observation.timestamp.date() != next_date for observation in selected):
                raise ReflectionExperimentError("Held-out observations must belong to the effective day.")
            final_times[case_id] = at.isoformat()
        source_paths = {"scenario": scenario_path, "tasks": scenario_file(scenario, "tasks_file"),
                        "seed": seed, "summary": Path(summary_path),
                        "feedback": Path(feedback_path), "expectations": Path(expectations_path),
                        "provider_config": Path(provider_config), "training": training_path,
                        **observation_paths}
        report["source_inputs"] = {name: _proof(path) for name, path in source_paths.items()}
        frozen_inputs = output / "inputs"
        frozen_inputs.mkdir()
        frozen_provider = frozen_inputs / "openrouter.json"
        frozen_summary = frozen_inputs / "summary.txt"
        frozen_feedback = frozen_inputs / "feedback.txt"
        for source, target in ((provider_config, frozen_provider), (summary_path, frozen_summary),
                               (feedback_path, frozen_feedback), (expectations_path, frozen_inputs / "expectations.json")):
            target.write_bytes(Path(source).read_bytes())
        fixed_paths = {"scenario": scenario_path, "tasks": source_paths["tasks"],
                       "paper_config": PROJECT_ROOT / "config" / "paper.json",
                       "prompt_sources": PROJECT_ROOT / "prompts" / "source_map.json",
                       "provider": frozen_provider, "summary": frozen_summary, "feedback": frozen_feedback}
        fixed_paths.update({"prompt_" + path.stem: path for path in (PROJECT_ROOT / "prompts" / "paper").glob("*.txt")})
        report["fixed_model_inputs"] = {name: _proof(path) for name, path in fixed_paths.items()}
        store = output / "memory_store"
        initialize_store(store, seed, source_day)
        old_memory, old_record = get_memory_for_day(store, source_day)
        report["memory_store"] = str(store)
        report["old_memory"] = old_record
        before_frames = {}
        event("preflight", "ready")

        for case_id in CASE_IDS:
            stage, bundle_path = prepare_job(f"before_{case_id}", "before", case_id, old_record)
            invoke(stage, bundle_path)
        stage, reflection_bundle = prepare_job("reflection", "reflection", None, old_record)
        invoke(stage, reflection_bundle)
        report["current_stage"] = "commit_reflection"
        event("commit_reflection", "validating_evidence")
        new_record = commit_reflection(store, Path(stage["result_path"]), reflection_bundle, source_day, effective_day)
        report["new_memory"] = new_record
        new_memory, assigned_record = get_memory_for_day(store, effective_day)
        frozen_old, still_old = get_memory_for_day(store, source_day)
        if (frozen_old != old_memory or still_old["sha256"] != old_record["sha256"]
                or assigned_record["sha256"] != new_record["sha256"]):
            raise ReflectionExperimentError("The day assignment changed unexpectedly during reflection.")
        _save(output / "memory_diff.json", {"old_memory": old_memory, "new_memory": new_memory})
        report["memory_changed"] = old_memory != new_memory
        report["memory_diff_path"] = str(output / "memory_diff.json")
        event("commit_reflection", "next_day_memory_assigned")
        for case_id in CASE_IDS:
            stage, bundle_path = prepare_job(f"after_{case_id}", "after", case_id, assigned_record)
            invoke(stage, bundle_path)

        report["current_stage"] = "evaluation"
        comparisons = []
        for case_id in CASE_IDS:
            before = next(item for item in report["stages"] if item["id"] == f"before_{case_id}")
            after = next(item for item in report["stages"] if item["id"] == f"after_{case_id}")
            case = expected[case_id]
            comparisons.append({"case_id": case_id, "label_ko": case["label_ko"],
                                "expected_task_indices": case["expected_task_indices"],
                                "before_task_index": before["task_index"], "after_task_index": after["task_index"],
                                "before_passed": before["task_index"] in case["expected_task_indices"],
                                "after_passed": after["task_index"] in case["expected_task_indices"],
                                "same_images": before["frames"] == after["frames"],
                                "before_result_path": before["result_path"], "after_result_path": after["result_path"]})
        if _proof(seed)["sha256"] != report["source_inputs"]["seed"]["sha256"]:
            raise ReflectionExperimentError("The original scenario seed changed during the experiment.")
        report["comparisons"] = comparisons
        report["before_passed"] = sum(item["before_passed"] for item in comparisons)
        report["after_passed"] = sum(item["after_passed"] for item in comparisons)
        report["all_after_passed"] = all(item["after_passed"] for item in comparisons)
        report["status"] = "completed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        event("experiment", "completed")
    except Exception as error:
        report["status"] = "failed"
        report["failed_stage"] = report["current_stage"]
        report["error_type"] = type(error).__name__
        report["error"] = str(error)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        event(report["current_stage"], "failed_no_retry")
    return report
