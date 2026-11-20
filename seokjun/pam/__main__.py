"""Prepare paper/scenario inputs, or explicitly run a prepared OpenRouter request."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .contracts import ContractError, parse_prediction, validate_tasks
from .messages import (PROJECT_ROOT, build_predictor_messages, build_reflector_messages,
                       load_paper_config, read_json)
from .observations import (InsufficientObservations, ObservationNotReady, compose_observations,
                           load_observations, select_predictor_window, select_reflector_frames)
from .scenarios import load_scenario, load_scenario_tasks, scenario_file


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _file_record(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use a nonnegative integer pixel count.") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("Use a nonnegative integer pixel count.")
    return parsed


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="PAM 논문 입력 준비와 OpenRouter 모델 호출. 로봇 동작은 수행하지 않습니다.")
    commands = root.add_subparsers(dest="command", required=True)
    predictor = commands.add_parser("prepare-predictor", help="행동 판단에 보낼 사진 5장과 지시문 준비")
    reflector = commands.add_parser("prepare-reflector", help="기억 생성·갱신에 보낼 사진과 지시문 준비; 기본 200장")
    for command in (predictor, reflector):
        command.add_argument("--observations", type=Path, required=True, help="두 카메라 관찰 목록 JSON")
        command.add_argument("--memory", type=Path, help="논문 형식의 기억 JSON")
        command.add_argument("--memory-store", type=Path, help="날짜별 기억 버전과 자기반성 증거를 보존한 폴더")
        command.add_argument("--day", help="기억을 사용할 날짜 YYYY-MM-DD; --memory-store와 함께 사용")
        command.add_argument("--project-dir", type=Path, default=PROJECT_ROOT, help="논문 지시문·설정이 있는 프로젝트 폴더")
        command.add_argument("--scenario", type=Path, help="원문에서 바꿀 환경·행동·초기 기억 설정")
        command.add_argument("--output", type=Path, required=True, help="결과를 보존할 새 폴더")
    predictor.add_argument("--tasks", type=Path, help="가능한 행동 문장들의 JSON 배열; 상황 설정이 있으면 해당 목록 사용")
    predictor.add_argument("--memory-kind", choices=("none", "list", "fsm"), default="none")
    predictor.add_argument("--at", required=True, help="판단할 마지막 사진의 날짜·시각·시간대 (ISO 8601)")
    reflector.add_argument("--memory-kind", choices=("list", "fsm"), required=True)
    reflector.add_argument("--operation", choices=("build", "update"), required=True)
    reflector.add_argument("--summary", type=Path, help="시간순 사람·로봇 행동 요약 텍스트; 갱신에 필요")
    reflector.add_argument("--feedback", type=Path, help="있을 경우에만 제공하는 사용자 피드백 텍스트")
    reflector.add_argument("--vertical-padding-px", type=_nonnegative_int, default=0,
                           help="사진 위아래에 각각 추가할 검정 여백 픽셀 수; 기본 0, 논문 외 입력 크기 실험 옵션")
    reflector.add_argument("--reflector-frame-count", type=int, choices=(50, 100, 150, 200), default=200,
                           help="기억 생성·갱신에 사용할 시점 수; 논문 기본 200장, 사용자 지정 변경 50·100·150장")
    response = commands.add_parser("validate-response", help="제공된 응답 텍스트의 형식 검사; 모델 호출 아님")
    response.add_argument("--response", type=Path, required=True)
    response.add_argument("--tasks", type=Path, required=True)
    response.add_argument("--output", type=Path, required=True, help="검사 결과를 보존할 새 폴더")
    inference = commands.add_parser("infer-bundle", help="준비된 입력을 OpenRouter로 실제 한 번 호출")
    inference.add_argument("--bundle", type=Path, required=True, help="준비 결과 input_bundle.json")
    inference.add_argument("--provider-config", type=Path, default=PROJECT_ROOT / "config" / "openrouter.json")
    inference.add_argument("--output", type=Path, required=True, help="실제 응답과 사진 검토 결과를 보존할 새 폴더")
    return root


def _prepare(args: argparse.Namespace, output: Path) -> dict:
    observations = load_observations(args.observations)
    scenario = load_scenario(args.scenario) if args.scenario else None
    assignment = None
    if args.memory_store is not None:
        if args.memory is not None or not args.day:
            raise ContractError("Use --memory-store with --day and without --memory.")
        if args.memory_kind != "fsm" or (args.command == "prepare-reflector" and args.operation != "update"):
            raise ContractError("The daily memory store supports FSM prediction and end-of-day updates.")
        from .memory_store import get_memory_for_day
        _, assignment = get_memory_for_day(args.memory_store, args.day)
        args.memory = Path(assignment["memory_path"])
    elif args.day is not None:
        raise ContractError("--day requires --memory-store.")
    if scenario is not None:
        if args.command == "prepare-predictor":
            scenario_tasks = load_scenario_tasks(scenario)
            if args.tasks is not None and read_json(args.tasks) != scenario_tasks:
                raise ContractError("Explicit tasks differ from the selected scenario task list.")
            if args.tasks is None:
                args.tasks = scenario_file(scenario, "tasks_file")
        needs_memory = (args.command == "prepare-predictor" and args.memory_kind != "none") or (
            args.command == "prepare-reflector" and args.operation == "update")
        if needs_memory and args.memory is None:
            args.memory = scenario_file(scenario, "memory", args.memory_kind)
    if args.command == "prepare-predictor" and args.tasks is None:
        raise ContractError("Provide --tasks or a --scenario containing the task list.")
    memory = read_json(args.memory) if args.memory is not None else None
    if args.command == "prepare-predictor":
        at = datetime.fromisoformat(args.at.replace("Z", "+00:00"))
        selected = select_predictor_window(observations, at)
        if assignment is not None and any(frame.timestamp.date().isoformat() != args.day for frame in selected):
            raise ContractError("Selected observation dates differ from the frozen memory day.")
        frames = compose_observations(selected, output / "frames")
        request = build_predictor_messages(
            frames, read_json(args.tasks), memory_kind=args.memory_kind,
            memory=memory, project_dir=args.project_dir, scenario=scenario)
    else:
        selected = select_reflector_frames(observations, count=args.reflector_frame_count)
        if assignment is not None and any(frame.timestamp.date().isoformat() != args.day for frame in selected):
            raise ContractError("Reflection observations must belong to the selected memory day.")
        frames = compose_observations(
            selected, output / "frames", vertical_padding_px=args.vertical_padding_px)
        request = build_reflector_messages(
            frames, memory_kind=args.memory_kind, operation=args.operation, memory=memory,
            summary=args.summary.read_text(encoding="utf-8-sig") if args.summary else None,
            feedback=args.feedback.read_text(encoding="utf-8-sig") if args.feedback else None,
            project_dir=args.project_dir, scenario=scenario, frame_count=args.reflector_frame_count)
    for frame in frames:
        frame["sha256"] = hashlib.sha256(Path(frame["image_path"]).read_bytes()).hexdigest()
        frame["left_sha256"] = hashlib.sha256(Path(frame["left_image"]).read_bytes()).hexdigest()
        frame["right_sha256"] = hashlib.sha256(Path(frame["right_image"]).read_bytes()).hexdigest()
    input_files = {}
    for name in ("observations", "tasks", "memory", "summary", "feedback", "scenario"):
        path = getattr(args, name, None)
        if path is not None:
            input_files[name] = _file_record(path)
    source_map = read_json(args.project_dir / "prompts" / "source_map.json")
    padding = args.vertical_padding_px if args.command == "prepare-reflector" else 0
    image_adaptation = {
        "kind": "vertical_black_letterbox" if padding else "none",
        "vertical_padding_px": padding,
        "top_padding_px": padding, "bottom_padding_px": padding,
        "padding_color_rgb": [0, 0, 0], "source_rgb_pixels_preserved": True,
        "resized": False, "cropped": False, "paper_parameter": False,
        "note": (
            "Optional experimental API-input adaptation, not a parameter from the paper. "
            "Equal black margins are added above and below the left-right image pair; "
            "source RGB pixels, camera order, and timestamps are preserved without resizing or cropping. "
            "For a 768x288 source pair, 48 pixels on each side produce 768x384 (aspect ratio 2.0). "
            "Any provider token-count or context-fit benefit requires actual verification."
        ),
    }
    bundle = {
        "schema_version": 1, "status": "prepared", "execution_mode": "offline_preparation",
        "prepared_at": datetime.now(timezone.utc).isoformat(), "api_called": False,
        "model_result": None, "action_executed": False,
        "description": "Model input preparation only. No model judgment or robot execution occurred.",
        "source_pdf": source_map["source_pdf"], "inputs": input_files,
        "paper_config": load_paper_config(args.project_dir), "frames": frames,
        "memory_assignment": assignment, "image_adaptation": image_adaptation, **request,
    }
    (output / "system_prompt.txt").write_text(request["messages"][0]["content"], encoding="utf-8")
    review = [
        "PAM 논문 입력 준비 결과", "",
        "상태: 입력 준비 완료. 실제 Qwen 모델은 호출하지 않았습니다.",
        "행동 판단 결과와 로봇 실행 결과는 없습니다.",
        f"역할: {'행동 판단' if request['role'] == 'predictor' else '기억 생성·갱신'}",
        f"원문 지시문: {request['prompt_source']['id']}",
        f"모델: {request['model']}",
        f"사진 수: {len(frames)}개 시점. 각 사진은 같은 시각의 왼쪽·오른쪽 화면을 가로로 연결했습니다.",
        *([f"기억 입력 사진 수: 사용자 지시로 {request['frame_count']}개 시점을 선택했습니다. 논문의 원래 값은 200개이며 원문 설정 파일은 보존했습니다."]
          if request.get("frame_count_source") == "explicit_user_override" else []),
        f"추가 검정 여백: 위·아래 각각 {padding}픽셀. 원본 RGB 픽셀과 시각을 보존했습니다.",
        "검정 여백은 논문 설정이 아닌 입력 크기 실험 옵션이며, API의 실제 토큰 감소는 별도 확인이 필요합니다.",
        "", "입력 사진 시각:", *[frame["timestamp"] for frame in frames],
        "", "전체 입력과 출처는 input_bundle.json, 영어 지시문은 system_prompt.txt에 있습니다.",
        "image_file은 로컬 사진 참조 형식입니다. 이 파일을 그대로 외부 API에 보내는 형식은 아닙니다.",
    ]
    (output / "검토안내.txt").write_text("\n".join(review) + "\n", encoding="utf-8")
    return bundle


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    output = args.output.resolve()
    inference_state = {"api_request_attempted": False, "model_response_received": False}
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        print(json.dumps({"status": "input_error", "api_called": False,
                          "error": f"Choose a fresh output directory: {exc}"}, ensure_ascii=False))
        return 2
    try:
        if args.command == "infer-bundle":
            from .inference import infer_bundle
            result = infer_bundle(args.bundle, args.provider_config, output, run_state=inference_state)
            print(json.dumps({"status": result["status"],
                              "model_response_received": result["model_response_received"],
                              "selected_action_ko": result.get("selected_action_ko"),
                              "output": str(output)}, ensure_ascii=False))
            return 0 if result["status"] == "valid" else 2
        if args.command == "validate-response":
            tasks = validate_tasks(read_json(args.tasks))
            raw = args.response.read_text(encoding="utf-8")
            result = parse_prediction(raw, tasks)
            result.update({"api_called": False, "action_executed": False,
                           "execution_mode": "provided_response_format_check",
                           "response_source": _file_record(args.response), "semantic_accuracy_evaluated": False})
            _write_json(output / "response_check.json", result)
            print(json.dumps({"status": result["status"], "api_called": False,
                              "output": str(output)}, ensure_ascii=False))
            return 0 if result["status"] == "valid" else 2
        bundle = _prepare(args, output)
        _write_json(output / "input_bundle.json", bundle)
        print(json.dumps({"status": "prepared", "api_called": False,
                          "frames": len(bundle["frames"]), "output": str(output)}, ensure_ascii=False))
        return 0
    except (ContractError, ObservationNotReady, InsufficientObservations,
            OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        if args.command == "infer-bundle":
            error = {"status": "inference_error", **inference_state, "action_executed": False,
                     "error_type": type(exc).__name__, "error": str(exc)}
            try:
                _write_json(output / "inference_error.json", error)
            except OSError:
                error["error_record_saved"] = False
            print(json.dumps(error, ensure_ascii=False))
            return 2
        status = "observation_not_ready" if isinstance(exc, ObservationNotReady) else "input_error"
        error = {"status": status, "api_called": False, "model_result": None,
                 "action_executed": False, "error_type": type(exc).__name__, "error": str(exc)}
        _write_json(output / "preparation_error.json", error)
        print(json.dumps(error, ensure_ascii=False))
        return 3 if status == "observation_not_ready" else 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
