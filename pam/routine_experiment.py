"""Four-day routine experiment (A1 -> A2 -> B1 -> B2) with the paper's FSM memory.

Per day (round):
  1. Extract one frame per second (predictor) and 200 uniform frames (reflector).
  2. Predictor every second with up to 9 frames 1 s apart (explicit user override of
     the paper's 5 frames 2 s apart; before 8 s only the frames collected so far).
     The first day has no memory; later days use the previous day's reflected memory.
  3. Day summary = the predictor's own per-second scene descriptions in order. The
     robot never acted in these videos, so the summary says so. No evaluator data.
  4. Reflector with the paper's 200 frames: build on the first day, update afterwards,
     without human feedback (none was given).
Memory is kept per round (not per calendar date). Labels are never read here.

Model calls go through one ``call(bundle_path, output_dir)`` function. The command
line uses a fake model (no network) unless ``--execute`` is given; ``--execute``
uses OpenRouter through pam.inference.infer_bundle and requires OPENROUTER_API_KEY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .contracts import ContractError, validate_memory
from .messages import PROJECT_ROOT, build_predictor_messages, build_reflector_messages, read_json
from .scenarios import load_scenario, load_scenario_tasks, scenario_file
from .video_frames import extract_frames, extract_reflector_frames

ROUNDS = ("A1", "A2", "B1", "B2")
WINDOW_FRAMES, STRIDE_SECONDS, REFLECTOR_FRAMES = 9, 1, 200
NOMINAL_START = "2026-11-04T22:00:00+09:00"
FAKE_MEMORY = {"initial_state": "fake", "states": [
    {"id": "fake", "description": "Fake-model placeholder for a dry run; not a model result.",
     "rules": [], "next": []}]}
FAKE_LIST_MEMORY = {"rules": []}
SUMMARY_HEADER = ("Robot: the robot did not physically act today; the person performed every action in the video.\n"
                  "Person: scene descriptions written by the robot's task predictor once per second, "
                  "in temporal order (t = seconds since the start of today's video).")

Call = Callable[[Path, Path], dict]


class RoutineExperimentError(ValueError):
    """The run cannot continue without changing its declared conditions."""


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fake_call(bundle_path: Path, output_dir: Path) -> dict:
    """Deterministic stand-in: always «no action», and an empty placeholder memory."""
    bundle = read_json(bundle_path)
    if bundle["role"] == "predictor":
        final = bundle["frames"][-1]["timestamp"]
        prediction = {"observation": f"Fake scene description for the frame at {final}.",
                      "reasoning": "Fake model: no decision was made.", "task_index": -1}
        result = {"status": "valid", "prediction": prediction, "selected_action": None,
                  "raw_response": json.dumps(prediction)}
    else:
        memory = FAKE_LIST_MEMORY if bundle["memory_kind"] == "list" else FAKE_MEMORY
        result = {"status": "valid", "memory": memory, "raw_response": json.dumps(memory)}
    result.update({"fake_model": True, "api_request_attempted": False, "action_executed": False})
    _save(output_dir / "result.json", result)
    return result


def openrouter_call(predictor_config: Path, reflector_config: Path) -> Call:
    from .inference import infer_bundle

    def call(bundle_path: Path, output_dir: Path) -> dict:
        role = read_json(bundle_path)["role"]
        return infer_bundle(bundle_path, predictor_config if role == "predictor" else reflector_config, output_dir)
    return call


def vllm_call(base_url: str, reflector_max_tokens: int = 16384) -> Call:
    from .vllm_client import infer_bundle_vllm
    limits = {"predictor": 2048, "reflector": reflector_max_tokens}

    def call(bundle_path: Path, output_dir: Path) -> dict:
        return infer_bundle_vllm(bundle_path, output_dir, base_url=base_url, max_tokens=limits)
    return call


def _frame_records(frames: list[dict], start: datetime) -> list[dict]:
    return [{"timestamp": (start + timedelta(seconds=frame["seconds"])).isoformat(),
             "seconds": frame["seconds"], "image_path": frame["image_path"],
             "sha256": _sha(Path(frame["image_path"]))} for frame in frames]


def _bundle(request: dict, frames: list[dict], inputs: dict) -> dict:
    return {"schema_version": 1, "status": "prepared", "execution_mode": "offline_preparation",
            "prepared_at": datetime.now(timezone.utc).isoformat(), "api_called": False,
            "model_result": None, "action_executed": False,
            "description": "Routine experiment input. Evaluation labels are not part of it.",
            "frames": frames, "inputs": inputs, **request}


def _run_call(call: Call, bundle: dict, directory: Path, resume: bool) -> dict:
    """Write the bundle and call once; with resume, reuse an identical earlier valid result."""
    bundle_path, result_path = directory / "input_bundle.json", directory / "result.json"
    if resume and result_path.is_file() and bundle_path.is_file():
        previous, result = read_json(bundle_path), read_json(result_path)
        same = {k: v for k, v in previous.items() if k != "prepared_at"} == \
               {k: v for k, v in bundle.items() if k != "prepared_at"}
        if same and result.get("status") == "valid":
            return {**result, "reused": True}
    if resume and directory.exists():
        # Keep the unusable earlier attempt for inspection; never overwrite it.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        directory.rename(directory.with_name(f"{directory.name}.superseded-{stamp}"))
    directory.mkdir(parents=True, exist_ok=False)
    _save(bundle_path, bundle)
    return call(bundle_path, directory)


def build_summary(predictions: list[dict]) -> str:
    lines = [SUMMARY_HEADER]
    for item in predictions:
        text = item.get("observation") or "(no valid scene description)"
        lines.append(f"t={item['t']}s: {text}")
    return "\n".join(lines) + "\n"


def run_round(*, name: str, index: int, video: Path, output: Path, scenario: dict, tasks: list[str],
              memory: dict | None, call: Call, reflect: bool, width: int, height: int,
              resume: bool, workers: int = 1, kind: str = "fsm") -> dict:
    root = output / name
    root.mkdir(parents=True, exist_ok=True)
    start = datetime.fromisoformat(NOMINAL_START) + timedelta(days=index)
    seconds_dir, reflector_dir = root / "frames_1fps", root / "frames_reflector"
    if resume and seconds_dir.is_dir() and reflector_dir.is_dir():
        seconds = [{"seconds": float(i), "image_path": str(p)}
                   for i, p in enumerate(sorted(seconds_dir.glob("frame_*.png")))]
        selected = read_json(root / "reflector_frames.json")
    else:
        seconds = extract_frames(video, seconds_dir, fps=1, width=width, height=height)
        selected = extract_reflector_frames(video, reflector_dir, count=REFLECTOR_FRAMES,
                                            width=width, height=height)
        _save(root / "reflector_frames.json", selected)
    frames = _frame_records(seconds, start)
    memory_kind = "none" if memory is None else kind
    inputs = {"video": {"path": str(Path(video).resolve()), "sha256": _sha(video)},
              "scenario": {"path": scenario["_config_path"], "sha256": scenario["_config_sha256"]}}
    if memory is not None:
        _save(root / "memory_used.json", memory)
        inputs["memory"] = {"path": str(root / "memory_used.json"), "sha256": _sha(root / "memory_used.json")}

    def predict(t: int) -> dict:
        window = frames[max(0, t - WINDOW_FRAMES + 1):t + 1]
        request = build_predictor_messages(
            window, tasks, memory_kind=memory_kind, memory=memory, scenario=scenario,
            window_frames=WINDOW_FRAMES, stride_seconds=STRIDE_SECONDS)
        return _run_call(call, _bundle(request, window, inputs), root / "predictor" / f"t{t:04d}", resume)

    # Memory is fixed during the day, so the per-second calls are independent of each other.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(predict, t) for t in range(len(frames))]
        results = []
        for t, future in enumerate(futures):
            results.append(future.result())
            if (t + 1) % 25 == 0 or t + 1 == len(futures):
                print(json.dumps({"round": name, "predictions_done": t + 1, "of": len(futures)}), flush=True)
    errors = [t for t, result in enumerate(results) if result.get("status") == "api_error"]
    if errors:
        raise RoutineExperimentError(f"{name}: API error at t={errors[:5]}s; the run stopped without retry.")
    predictions = []
    for t, result in enumerate(results):
        valid = result.get("status") == "valid"
        prediction = result.get("prediction") if valid else None
        predictions.append({"t": t, "status": "valid" if valid else "invalid",
                            "task_index": prediction["task_index"] if valid else None,
                            "observation": prediction["observation"] if valid else None,
                            "reasoning": prediction["reasoning"] if valid else None,
                            "errors": result.get("errors", [])})
    with (root / "predictions.jsonl").open("w", encoding="utf-8") as stream:
        for item in predictions:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")

    summary_path = root / "summary.txt"
    summary_path.write_text(build_summary(predictions), encoding="utf-8")
    record = {"round": name, "video": inputs["video"], "nominal_start": start.isoformat(),
              "frames_1fps": len(frames), "memory_kind": memory_kind,
              "memory_used_sha256": inputs.get("memory", {}).get("sha256"),
              "predictions": len(predictions),
              "invalid_predictions": sum(item["status"] != "valid" for item in predictions),
              "summary": {"path": str(summary_path), "sha256": _sha(summary_path)}}
    if not reflect:
        record["reflection"] = None
        return record

    reflector_frames = _frame_records(selected, start)
    operation = "build" if memory is None else "update"
    request = build_reflector_messages(
        reflector_frames, memory_kind=kind, operation=operation, memory=memory,
        summary=None if memory is None else summary_path.read_text(encoding="utf-8"),
        feedback=None, scenario=scenario, frame_count=REFLECTOR_FRAMES)
    reflection_inputs = dict(inputs)
    if memory is not None:
        reflection_inputs["summary"] = record["summary"]
    result = _run_call(call, _bundle(request, reflector_frames, reflection_inputs), root / "reflection", resume)
    if result.get("status") != "valid":
        raise RoutineExperimentError(f"{name}: the reflection result is not valid; the run stopped without retry.")
    new_memory = validate_memory(result["memory"], kind)
    _save(root / "memory_after.json", new_memory)
    record["reflection"] = {"operation": operation, "frames": len(reflector_frames),
                            "memory_after": str(root / "memory_after.json"),
                            "memory_after_sha256": _sha(root / "memory_after.json"),
                            "fake_model": bool(result.get("fake_model"))}
    record["memory_after"] = new_memory
    return record


def run_experiment(*, videos_dir: Path, output_dir: Path, call: Call, rounds=ROUNDS,
                   scenario_path: Path = PROJECT_ROOT / "scenarios" / "routine" / "scenario.json",
                   reflect_last: bool = False, width: int = 640, height: int = 360,
                   resume: bool = False, mode: str = "fake", workers: int = 1,
                   no_memory: bool = False, memory_kind: str = "fsm") -> dict:
    if memory_kind not in ("fsm", "list"):
        raise RoutineExperimentError("memory_kind must be fsm or list.")
    output = Path(output_dir).resolve()
    if output.exists() and not resume:
        raise RoutineExperimentError("Choose a new output directory, or pass resume to continue the same run.")
    output.mkdir(parents=True, exist_ok=True)
    scenario = load_scenario(scenario_path)
    tasks = load_scenario_tasks(scenario)
    report = {"schema_version": 1, "mode": mode, "status": "running",
              "condition": "no_memory" if no_memory else f"{memory_kind}_memory", "predictor_workers": workers,
              "started_at": datetime.now(timezone.utc).isoformat(), "rounds": [],
              "settings": {"predictor_window_frames": WINDOW_FRAMES, "predictor_stride_seconds": STRIDE_SECONDS,
                           "predictor_window_source": "explicit_user_override",
                           "reflector_frames": REFLECTOR_FRAMES, "reflector_frames_source": "paper",
                           "image_size": [width, height], "nominal_clock_start": NOMINAL_START,
                           "nominal_clock_note": "Wall-clock times shown to the model are nominal (one day per round), not filming times.",
                           "first_day_memory": None, "human_feedback": None,
                           "summary_source": "predictor per-second observations",
                           "tasks_file": str(scenario_file(scenario, "tasks_file")),
                           "scenario": {"path": scenario["_config_path"], "sha256": scenario["_config_sha256"]}},
              "evaluation_labels_sent_to_models": False}
    _save(output / "report.json", report)
    memory = None
    try:
        for index, name in enumerate(rounds):
            video = Path(videos_dir) / f"{name}.mp4"
            reflect = not no_memory and (index < len(rounds) - 1 or reflect_last)
            record = run_round(name=name, index=ROUNDS.index(name) if name in ROUNDS else index,
                               video=video, output=output, scenario=scenario,
                               tasks=tasks, memory=memory, call=call, reflect=reflect,
                               width=width, height=height, resume=resume, workers=workers,
                               kind=memory_kind)
            memory = record.pop("memory_after", memory)
            report["rounds"].append(record)
            _save(output / "report.json", report)
        report["status"] = "completed"
    except (ContractError, RoutineExperimentError, OSError, ValueError, KeyError) as error:
        report.update({"status": "failed", "error_type": type(error).__name__, "error": str(error)})
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    _save(output / "report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="4일 일과 실험. 기본은 가짜 모델(네트워크 없음); --execute일 때만 실제 Qwen 호출.")
    parser.add_argument("--videos", type=Path, required=True, help="A1.mp4·A2.mp4·B1.mp4·B2.mp4가 있는 폴더")
    parser.add_argument("--output", type=Path, required=True, help="결과를 남길 새 폴더")
    parser.add_argument("--rounds", default=",".join(ROUNDS), help="돌릴 회차, 쉼표로 구분 (기본 A1,A2,B1,B2)")
    parser.add_argument("--reflect-last", action="store_true", help="마지막 회차 뒤에도 자기반성 실행")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--resume", action="store_true", help="같은 폴더의 성공한 호출은 다시 하지 않음")
    parser.add_argument("--execute", action="store_true", help="실제 OpenRouter 호출 (돈이 듦)")
    parser.add_argument("--vllm-url", help="직접 올린 vLLM 서버 주소 (예: RunPod 중계 주소). 주면 그 서버로 실제 호출")
    parser.add_argument("--workers", type=int, default=1, help="행동 고르기 동시 호출 수 (하루 안에서는 기억이 고정이라 서로 독립)")
    parser.add_argument("--no-memory", action="store_true", help="비교 조건: 모든 날 기억 없이, 자기반성 없음")
    parser.add_argument("--memory-kind", choices=("fsm", "list"), default="fsm",
                        help="기억 형태: fsm(상태·전이, 논문 본 방식) 또는 list(조건→행동 목록, 논문 비교 조건)")
    parser.add_argument("--reflector-max-tokens", type=int, default=16384,
                        help="vLLM 자기반성 답 길이 한도 (논문 값 아님, 서버 길이 한도에 맞춘 안전장치)")
    parser.add_argument("--predictor-config", type=Path, default=PROJECT_ROOT / "config" / "openrouter.json")
    parser.add_argument("--reflector-config", type=Path, default=PROJECT_ROOT / "config" / "openrouter_reflection.json")
    args = parser.parse_args(argv)
    if args.vllm_url and args.execute:
        parser.error("Choose either --execute (OpenRouter) or --vllm-url, not both.")
    if args.vllm_url:
        call, mode = vllm_call(args.vllm_url, args.reflector_max_tokens), "vllm"
    elif args.execute:
        call, mode = openrouter_call(args.predictor_config, args.reflector_config), "openrouter"
    else:
        call, mode = fake_call, "fake"
    report = run_experiment(videos_dir=args.videos, output_dir=args.output, call=call,
                            rounds=tuple(args.rounds.split(",")), reflect_last=args.reflect_last,
                            width=args.width, height=args.height, resume=args.resume,
                            mode=mode, workers=args.workers, no_memory=args.no_memory,
                            memory_kind=args.memory_kind)
    print(json.dumps({"status": report["status"], "mode": report["mode"], "output": str(Path(args.output).resolve()),
                      "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
