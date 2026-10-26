"""Explicitly run the seven-call PAM before/reflection/after experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Permit direct execution from any working directory without a second package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pam.reflection_experiment import ReflectionExperimentError, run_experiment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="기존 기억 판단 3회 → 실제 기억 갱신 1회 → 새 기억 판단 3회. 총 7회 API 호출하며 자동 재시도하지 않습니다.")
    parser.add_argument("--dataset-dir", required=True, type=Path, help="훈련·검증 사진 목록 네 개가 있는 폴더")
    parser.add_argument("--scenario", required=True, type=Path, help="상황·행동 목록·기존 기억 설정 JSON")
    parser.add_argument("--summary", required=True, type=Path, help="훈련일의 실제로 제공할 행동 요약")
    parser.add_argument("--feedback", required=True, type=Path, help="기억 갱신기에 제공할 사용자 피드백")
    parser.add_argument("--expectations", required=True, type=Path, help="모델에 보내지 않을 사후 평가용 기대 행동 JSON")
    parser.add_argument("--provider-config", required=True, type=Path, help="OpenRouter의 고정 모델·제공자·통신 제한 설정")
    parser.add_argument("--output", required=True, type=Path, help="아직 존재하지 않는 새 실험 결과 폴더")
    parser.add_argument("--source-day", default="2026-10-24", help="기존 기억을 고정하고 훈련 자료를 관찰한 날짜")
    parser.add_argument("--effective-day", default="2026-10-25", help="갱신 기억을 적용할 바로 다음 날짜")
    parser.add_argument("--reflection-vertical-padding-px", type=int, default=0,
                        help="기억 갱신 사진 위아래에 추가할 검정 여백. 원본 픽셀을 보존하는 API 입력 실험이며 논문 설정이 아닙니다.")
    parser.add_argument("--reflector-frame-count", type=int, choices=[50, 100, 150, 200], default=200,
                        help="자기반성 입력 시점 수. 논문 원래 값은 200이며 50·100·150은 사용자가 지정한 변경 조건입니다.")
    args = parser.parse_args(argv)
    try:
        report = run_experiment(
            dataset_dir=args.dataset_dir, scenario_path=args.scenario, summary_path=args.summary,
            feedback_path=args.feedback, expectations_path=args.expectations, provider_config=args.provider_config,
            output_dir=args.output, source_day=args.source_day, effective_day=args.effective_day,
            reflection_vertical_padding_px=args.reflection_vertical_padding_px,
            reflector_frame_count=args.reflector_frame_count)
    except ReflectionExperimentError as error:
        print(json.dumps({"status": "not_started", "error": str(error)}, ensure_ascii=False), flush=True)
        return 2
    print(json.dumps({"status": report["status"], "api_requests_attempted": report["api_requests_attempted"],
                      "all_after_passed": report.get("all_after_passed"),
                      "report_path": str(Path(args.output).resolve() / "report.json")}, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
