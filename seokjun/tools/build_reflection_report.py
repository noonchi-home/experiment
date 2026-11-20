"""Build a local Korean HTML review from saved PAM experiment artifacts.

This tool only reads files and writes HTML. It never calls a model or modifies
images, memories, predictions, or the experiment's machine-readable report.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
from pathlib import Path
from urllib.parse import quote


CASES = {
    "wakeup": "잠에서 깨어 일어났지만 식탁에 앉지 않은 장면",
    "seated_without_milk": "아침 식탁에 앉았고 우유가 아직 없는 장면",
    "seated_with_milk": "아침 식탁에 앉았고 우유가 이미 있는 장면",
}


def _h(value: object) -> str:
    return html.escape(str(value), quote=True)


def _load(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, ValueError):
        return None


def _local(value: object, base: Path) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        path = Path(value)
        return (path if path.is_absolute() else base / path).resolve()
    except (OSError, ValueError):
        return None


def _number(value: object, *, digits: int = 3) -> str | None:
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    return str(value) if type(value) is int else f"{value:.{digits}f}"


def _stage_label(identifier: object) -> str:
    text = str(identifier or "")
    name, _, substage = text.partition(":")
    fixed = {"preflight": "입력 자료 사전 확인", "reflection": "하루 기록과 피드백으로 기억 갱신",
             "commit_reflection": "새 기억을 다음 날에 배정", "evaluation": "기대 행동과 결과 비교"}
    label = fixed.get(name)
    if label is None and name.startswith("reflection_"):
        label = "하루 기록과 피드백으로 기억 갱신 · 입력 " + name[len("reflection_"):] + "개 시점"
    if label is None:
        for prefix, phrase in (("before_", "기억 갱신 전"), ("after_", "기억 갱신 후")):
            if name.startswith(prefix):
                label = phrase + " · " + CASES.get(name[len(prefix):], name[len(prefix):])
                break
    if label is None:
        label = "기록된 단계: " + text
    if substage:
        label += " · " + {"prepare": "입력 준비", "inference": "모델 호출"}.get(substage, substage)
    return label


def _status(result: dict | None) -> str:
    if result is None:
        return "미완료 — 결과 파일 없음"
    return {"valid": "형식 검사 통과", "invalid": "유효하지 않은 응답", "api_error": "API 호출 오류",
            "failed": "실패", "input_error": "입력 오류"}.get(result.get("status"), "완료 여부 미확인")


def _prediction_index(result: dict | None) -> int | None:
    if not isinstance(result, dict) or result.get("status") != "valid":
        return None
    prediction = result.get("prediction")
    index = prediction.get("task_index") if isinstance(prediction, dict) else None
    return index if type(index) is int else None


def _action(index: int | None, labels: list, tasks: list) -> str:
    if index is None:
        return "판단 결과 미완료 또는 오류"
    if index == -1:
        return "대기 — 지금은 아무 행동도 하지 않기"
    if 0 <= index < len(labels) and isinstance(labels[index], str):
        return labels[index]
    if 0 <= index < len(tasks) and isinstance(tasks[index], str):
        return f"행동 {index}: {tasks[index]}"
    return f"행동 {index} — 행동 설명을 읽지 못했습니다"


def build_report(experiment_dir: Path, output_path: Path | None = None) -> Path:
    root = Path(experiment_dir).resolve()
    report = _load(root / "report.json")
    if report is None:
        raise ValueError("실험 폴더의 report.json을 읽을 수 없습니다.")
    output = Path(output_path).resolve() if output_path is not None else root / "결과모음.html"
    if output.suffix.casefold() not in {".html", ".htm"}:
        raise ValueError("출력 파일은 .html 또는 .htm이어야 합니다.")

    def relative(path: Path | None) -> str | None:
        if path is None or not path.is_file():
            return None
        try:
            return quote(os.path.relpath(path, output.parent).replace("\\", "/"), safe="/")
        except (OSError, ValueError):
            return None

    def link(path: Path | None, label: str) -> str:
        target = relative(path)
        return (f'<a href="{_h(target)}">{_h(label)}</a>' if target is not None
                else f'<span class="muted">{_h(label)}: 파일 없음</span>')

    stages = {stage["id"]: stage for stage in report.get("stages", [])
              if isinstance(stage, dict) and isinstance(stage.get("id"), str)}
    reflection_ids = [identifier for identifier, stage in stages.items() if stage.get("phase") == "reflection"]
    if not reflection_ids:
        reflection_ids = ["reflection"]
    jobs = {}
    for stage_id in [*("before_" + case for case in CASES), *reflection_ids, *("after_" + case for case in CASES)]:
        stage = stages.get(stage_id, {})
        bundle_path = _local(stage.get("prepared_bundle"), root) or root / stage_id / "prepared" / "input_bundle.json"
        result_path = _local(stage.get("result_path"), root) or root / stage_id / "inference" / "result.json"
        if not result_path.is_file() and (root / stage_id / "inference" / "api_error.json").is_file():
            result_path = root / stage_id / "inference" / "api_error.json"
        jobs[stage_id] = {"bundle_path": bundle_path, "bundle": _load(bundle_path),
                          "result_path": result_path, "result": _load(result_path), "stage": stage}
    valid_reflections = [identifier for identifier in reflection_ids
                         if (jobs[identifier]["result"] or {}).get("status") == "valid"]
    selected_reflection_id = valid_reflections[-1] if valid_reflections else reflection_ids[-1]
    reflection = jobs[selected_reflection_id]

    labels, tasks = [], []
    for job in jobs.values():
        bundle = job["bundle"] or {}
        scenario = bundle.get("scenario") or {}
        if isinstance(scenario, dict) and isinstance(scenario.get("action_labels_ko"), list):
            labels = scenario["action_labels_ko"]
        if isinstance(bundle.get("tasks"), list):
            tasks = bundle["tasks"]
        if labels and tasks:
            break
    if not labels:
        source = (report.get("source_inputs") or {}).get("scenario") or {}
        scenario_path = _local(source.get("path"), root) if isinstance(source, dict) else None
        scenario = _load(scenario_path) if scenario_path is not None else None
        if scenario and isinstance(scenario.get("action_labels_ko"), list):
            labels = scenario["action_labels_ko"]

    expected_data = _load(root / "inputs" / "expectations.json") or {}
    expected = {case["id"]: case for case in expected_data.get("cases", [])
                if isinstance(case, dict) and case.get("id") in CASES}
    comparisons = {case["case_id"]: case for case in (report.get("comparisons") or [])
                   if isinstance(case, dict) and case.get("case_id") in CASES}

    def expected_indices(case_id: str) -> list[int]:
        value = comparisons.get(case_id, {}).get("expected_task_indices",
                                                  expected.get(case_id, {}).get("expected_task_indices", []))
        return [item for item in value if type(item) is int] if isinstance(value, list) else []

    def matches(result: dict | None, indices: list[int], prefix: str) -> str:
        index = _prediction_index(result)
        if index is None or not indices:
            return f'<span class="muted">{_h(prefix)}: 미완료 또는 비교 불가</span>'
        passed = index in indices
        return f'<span class="{"pass" if passed else "fail"}">{_h(prefix)}: {"일치" if passed else "불일치"}</span>'

    completed = report.get("status") == "completed"
    interrupted = report.get("status") == "interrupted_by_user_change"
    state_label = ("실험 실행 완료" if completed else "사용자 조건 변경으로 중단" if interrupted
                   else "실험 미완료 — 기록된 범위까지만 확인")
    headline = "기억 갱신 전후, 같은 장면에서 어떤 행동을 골랐나"
    body = [f'<header><p class="eyebrow">PAM · 절차 기억을 이용한 아침 행동 판단 실험</p><h1>{_h(headline)}</h1>',
            '<p>로봇을 움직이는 대신, 모델이 고른 행동을 글로 비교합니다.</p>',
            f'<p class="badge {"pass-bg" if completed else "fail-bg"}">{_h(state_label)}</p></header>']
    if not completed:
        stage = _stage_label(report.get("failed_stage") or report.get("current_stage"))
        body.append(f'<section class="notice"><h2>중단·미완료 상태</h2><p>{_h(stage)} 단계까지 기록되었습니다. '
                    '뒤 단계의 빈 결과는 대기 행동이나 성공으로 해석하지 않습니다.</p>')
        if interrupted:
            body.append('<p class="fail"><strong>모델 서버 처리와 비용 미확정 1건</strong></p>'
                        '<p>사용자가 입력 조건을 변경하여 실행을 중단했습니다. 진행 중이던 요청의 서버 처리와 비용은 아직 확인되지 않았습니다.</p>')
        if report.get("error") is not None:
            body.append(f'<details><summary>오류 원문 확인</summary><pre>{_h(report["error"])}</pre></details>')
        body.append('</section>')

    reflection_bundle = reflection["bundle"] or {}
    reflection_frames = reflection_bundle.get("frames")
    actual_count = len(reflection_frames) if isinstance(reflection_frames, list) else None
    declared_count = (reflection_bundle.get("frame_count", report.get("reflector_frame_count"))
                      if selected_reflection_id != "reflection" else report.get("reflector_frame_count"))
    if declared_count in (50, 100, 150):
        body.append('<section class="notice"><h2>사용자가 변경한 자기반성 입력 수</h2>'
                    f'<p><strong>표시하는 자기반성 입력은 사용자 지시로 {_h(declared_count)}개 시점입니다. 논문의 원래 조건은 200개 시점입니다.</strong></p>'
                    '<p>한 시점은 같은 시각의 왼쪽·오른쪽 카메라 사진을 가로로 합친 입력 한 장을 뜻합니다.</p>')
        if actual_count == declared_count:
            body.append(f'<p class="pass">해당 시도 설정 {_h(declared_count)}개와 실제 준비된 자기반성 입력 목록 {_h(actual_count)}개가 일치합니다.</p>')
        elif actual_count is None:
            body.append('<p class="muted">준비된 자기반성 입력 목록을 읽지 못해, 실제 시점 수와의 일치 여부는 아직 확인하지 못했습니다.</p>')
        else:
            body.append(f'<p class="fail">입력 기록 불일치: 해당 시도 설정은 {_h(declared_count)}개이지만, 준비된 입력 목록은 {_h(actual_count)}개입니다.</p>')
        if len(reflection_ids) > 1:
            selection_note = ("유효한 결과 중 마지막 결과를 표시하며, 앞선 실패도 아래에 남겼습니다."
                              if valid_reflections else "유효한 결과가 없어 마지막 시도의 오류를 표시하며, 앞선 실패도 아래에 남겼습니다.")
            body.append('<p>기억 갱신 시도를 둘 이상 보존했습니다. ' + _h(selection_note) + '</p>')
        body.append('</section>')

    metrics = [("계획한 모델 호출", report.get("planned_api_calls")),
               ("실제로 요청을 시도한 횟수", report.get("api_requests_attempted")),
               ("모델 응답을 받은 횟수", report.get("model_responses_received")),
               ("형식 검사를 통과한 결과", report.get("valid_results"))]
    body.append('<dl class="metrics">' + ''.join(f'<div><dt>{_h(label)}</dt><dd>{_h(value if value is not None else "미기록")}</dd></div>'
                                                 for label, value in metrics) + '</dl>')
    body.append('<section><h2>세 장면의 행동 비교</h2><p>기억 갱신 전에는 다음 날 장면을 이전 기억으로 평가했습니다. '
                '갱신 후에는 같은 사진에 새 기억을 적용했습니다. 기대 행동은 모델에 전달하지 않은 사후 비교 기준입니다.</p>'
                '<div class="table-wrap"><table><thead><tr><th>장면</th><th>기대 행동</th><th>기억 갱신 전</th>'
                '<th>기억 갱신 후</th><th>기대와의 일치</th></tr></thead><tbody>')
    for case_id, default_label in CASES.items():
        label = comparisons.get(case_id, {}).get("label_ko") or expected.get(case_id, {}).get("label_ko") or default_label
        before, after = jobs["before_" + case_id]["result"], jobs["after_" + case_id]["result"]
        indices = expected_indices(case_id)
        expect_text = " 또는 ".join(_action(index, labels, tasks) for index in indices) or "기대 행동 미기록"
        body.append(f'<tr><th>{_h(label)}</th><td>{_h(expect_text)}</td>'
                    f'<td>{_h(_action(_prediction_index(before), labels, tasks))}</td>'
                    f'<td>{_h(_action(_prediction_index(after), labels, tasks))}</td>'
                    f'<td>{matches(before, indices, "전")}<br>{matches(after, indices, "후")}</td></tr>')
    body.append('</tbody></table></div><p class="muted">일치는 이 세 장면의 기대 행동과 선택 번호가 맞았다는 뜻입니다. '
                '넓은 환경에서의 성능이나 행동의 적절성을 입증하는 값은 아닙니다.</p></section>')

    def frames_html(job: dict, heading: str) -> str:
        bundle = job["bundle"] or {}
        frames = bundle.get("frames") or []
        if not isinstance(frames, list) or not frames:
            return f'<p class="muted">{_h(heading)}: 준비된 사진 목록이 없습니다.</p>'
        figures = []
        for number, frame in enumerate(frames, 1):
            if not isinstance(frame, dict):
                continue
            path = _local(frame.get("image_path"), job["bundle_path"].parent)
            target = relative(path)
            caption = f"{number}번째 카메라 한 쌍 · {frame.get('timestamp', '시각 미기록')}"
            picture = (f'<a href="{_h(target)}"><img loading="lazy" src="{_h(target)}" '
                       f'alt="{_h(caption)}"></a>' if target else '<p class="muted">사진 파일을 읽지 못했습니다.</p>')
            figures.append(f'<figure>{picture}<figcaption>{_h(caption)}</figcaption></figure>')
        return f'<h3>{_h(heading)} · {_h(len(frames))}쌍</h3><p class="muted">각 사진은 같은 시점의 왼쪽·오른쪽 시야를 가로로 붙인 입력입니다.</p><div class="frames">' + ''.join(figures) + '</div>'

    def result_html(job: dict, label: str) -> str:
        result = job["result"] or {}
        prediction = result.get("prediction") if result.get("status") == "valid" else None
        prediction = prediction if isinstance(prediction, dict) else {}
        details = [f'<article class="result"><h3>{_h(label)}</h3><p>{_h(_status(job["result"]))}</p>',
                   f'<p class="action">{_h(_action(_prediction_index(job["result"]), labels, tasks))}</p>']
        for key, title in (("observation", "모델이 본 장면 — 응답 원문"), ("reasoning", "짧은 판단 근거 — 응답 원문")):
            details.append(f'<h4>{_h(title)}</h4><pre>{_h(prediction.get(key, "유효한 판단 내용이 없습니다."))}</pre>')
        details.append('<p>' + link(job["result_path"], "검사한 결과 JSON") + ' · '
                       + link(job["result_path"].parent / "api_response.raw.json", "API 응답 전체 원문") + ' · '
                       + link(job["bundle_path"], "보낸 입력과 출처") + '</p></article>')
        return ''.join(details)

    for case_id, label in CASES.items():
        before_job, after_job = jobs["before_" + case_id], jobs["after_" + case_id]
        body.append(f'<section><h2>{_h(label)}</h2><div class="results">'
                    + result_html(before_job, "기억 갱신 전") + result_html(after_job, "기억 갱신 후") + '</div>')
        before_frames = (before_job["bundle"] or {}).get("frames") or []
        after_frames = (after_job["bundle"] or {}).get("frames") or []
        comparable = (isinstance(before_frames, list) and isinstance(after_frames, list)
                      and len(before_frames) == 5 and len(after_frames) == 5)
        same = comparable and all(isinstance(first, dict) and isinstance(second, dict)
                                  and first.get("sha256") and first.get("sha256") == second.get("sha256")
                                  and first.get("timestamp") == second.get("timestamp")
                                  for first, second in zip(before_frames, after_frames))
        if same:
            body.append('<p class="pass">갱신 전후 사진의 확인값과 시각이 같습니다.</p>'
                        + frames_html(before_job, "갱신 전후에 공통으로 보낸 사진"))
        else:
            body.append('<p class="muted">전후 사진의 동일성을 확인하지 못했으므로, 준비된 입력을 각각 표시합니다.</p>'
                        + frames_html(before_job, "갱신 전에 준비한 사진"))
            if after_frames:
                body.append(frames_html(after_job, "갱신 후에 준비한 사진"))
        body.append('</section>')

    diff = _load(root / "memory_diff.json") or {}
    body.append('<section><h2>절차 기억의 갱신 내용</h2><p>아래 기억은 상태·조건·행동을 담은 실제 저장 JSON입니다. '
                '표시를 위해 규칙을 고치거나 기대한 규칙으로 바꾸지 않았습니다.</p>')
    for key, label in (("old_memory", "갱신 전 — 수동으로 제공한 기존 습관"), ("new_memory", "갱신 후 — 모델이 생성하고 다음 날에 배정한 기억")):
        record = report.get(key) or {}
        path = _local(record.get("memory_path"), root) if isinstance(record, dict) else None
        raw, note = None, "저장 파일 원문"
        if path is not None:
            try:
                raw = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                pass
        if raw is None and isinstance(diff.get(key), dict):
            raw = json.dumps(diff[key], ensure_ascii=False, indent=2)
            note = "memory_diff.json에 저장된 값의 JSON 표시"
        if raw is None:
            body.append(f'<p class="muted">{_h(label)}: 아직 저장된 기억이 없습니다.</p>')
        else:
            body.append(f'<details><summary>{_h(label)}</summary><p>{_h(note)} · {link(path, "기억 파일 열기")}</p>'
                        f'<pre>{_h(raw)}</pre></details>')
    body.append('<p>표시하는 기억 갱신: ' + _h(_stage_label(selected_reflection_id)) + '</p>'
                '<p>하루 기록을 반영한 기억 갱신 상태: ' + _h(_status(reflection["result"])) + '</p><p>'
                + link(reflection["result_path"], "기억 갱신 결과 JSON") + ' · '
                + link(reflection["result_path"].parent / "api_response.raw.json", "기억 갱신 API 응답 원문") + ' · '
                + link(reflection["bundle_path"], "기억 갱신에 보낸 입력") + '</p>')
    other_attempts = [identifier for identifier in reflection_ids if identifier != selected_reflection_id]
    if other_attempts:
        body.append('<h3>함께 보존한 다른 기억 갱신 시도</h3><ul>')
        for identifier in other_attempts:
            attempt = jobs[identifier]
            frames = (attempt["bundle"] or {}).get("frames")
            count = str(len(frames)) if isinstance(frames, list) else "미기록"
            body.append(f'<li>{_h(_stage_label(identifier))} · 입력 {_h(count)}개 시점 · {_h(_status(attempt["result"]))} · '
                        + link(attempt["result_path"], "이 시도의 결과·오류 기록") + '</li>')
        body.append('</ul>')
    body.append('</section>')

    body.append('<section><h2>실제 호출 기록</h2><p>아래 값은 저장된 응답과 준비된 입력에서 읽었습니다. 없는 값은 추정하지 않았습니다. '
                '사진 수는 두 카메라를 합친 시점 수이며, 모델의 처리 시간이 논문의 매초 실행 주기를 보장하지는 않습니다.</p>'
                '<div class="table-wrap"><table><thead><tr><th>단계</th><th>상태</th><th>응답 모델 · 제공자</th>'
                '<th>사진 수</th><th>걸린 시간</th><th>사용량</th></tr></thead><tbody>')
    predictor_latencies = []
    for stage_id, job in jobs.items():
        result, bundle = job["result"] or {}, job["bundle"] or {}
        elapsed = _number(result.get("elapsed_seconds"))
        if stage_id not in reflection_ids and elapsed is not None:
            predictor_latencies.append(float(result["elapsed_seconds"]))
        usage = result.get("usage")
        usage_parts = []
        if isinstance(usage, dict):
            for key, label in (("prompt_tokens", "입력 토큰"), ("completion_tokens", "출력 토큰"), ("total_tokens", "전체 토큰"), ("cost", "응답에 기록된 비용(USD)")):
                number = _number(usage.get(key), digits=6)
                if number is not None:
                    usage_parts.append(label + ": " + number)
            thinking = usage.get("completion_tokens_details") or {}
            number = _number(thinking.get("reasoning_tokens")) if isinstance(thinking, dict) else None
            if number is not None:
                usage_parts.append("긴 추론 토큰: " + number)
        frames = bundle.get("frames")
        frame_count = str(len(frames)) if isinstance(frames, list) else "미기록"
        model = result.get("response_model") or "응답 모델 미기록"
        provider = result.get("provider") or "제공자 미기록"
        body.append(f'<tr><th>{_h(_stage_label(stage_id))}</th><td>{_h(_status(job["result"]))}</td>'
                    f'<td>{_h(model)}<br>{_h(provider)}</td><td>{_h(frame_count)}</td>'
                    f'<td>{_h(elapsed + "초" if elapsed is not None else "미기록")}</td>'
                    f'<td>{"<br>".join(_h(item) for item in usage_parts) or "미기록"}</td></tr>')
    body.append('</tbody></table></div></section>')

    over_one_second = sum(latency > 1 for latency in predictor_latencies)
    cadence = (f"시간이 기록된 행동 판단 요청 {len(predictor_latencies)}회 중 {over_one_second}회가 1초를 넘었습니다. "
               "이 순차 실행은 논문의 1초마다 한 번 판단하는 속도 조건을 충족하지 못했습니다."
               if over_one_second else "이 실험은 장면별로 한 번씩 순차 호출했습니다. 연속으로 매초 판단하는 실행 성능은 검증하지 않았습니다.")
    limits = ["입력은 합성 3D 생활 장면입니다. 실제 가정에서 촬영한 연속 관찰 자료가 아닙니다.",
              "기억 갱신은 하루 관찰과 사용자 피드백을 함께 제공하는 조건입니다. 실제 갱신 완료 여부는 위 기록에서 확인하며, 피드백 없이 스스로 규칙을 발견한 실험으로 해석하지 않습니다.",
              "시작 기억은 사용자가 이미 습관이 있다고 가정하여 수동으로 제공한 자료입니다.",
              "로봇은 움직이지 않았고, 글로 제안한 행동을 실행 완료로 기록하지 않았습니다.",
              "세 조건을 기억 갱신 전후에 각각 한 번씩 호출하는 계획입니다. 미완료 단계는 위에 표시되며, 반복 시행이나 실제 환경 전체에 대한 성능 검증은 아닙니다.",
              cadence,
              "긴 추론 모드를 요청한 설정과 제공자의 내부 실행을 입증하는 것은 다릅니다. 공개된 응답·사용량 범위만 확인할 수 있습니다."]
    body.append('<section class="limits"><h2>이 결과를 읽을 때 함께 볼 조건</h2><ul>'
                + ''.join(f'<li>{_h(item)}</li>' for item in limits) + '</ul><p>'
                + link(root / "inputs" / "feedback.txt", "기억 갱신에 사용한 사용자 피드백") + ' · '
                + link(root / "inputs" / "summary.txt", "하루 행동 요약") + ' · '
                + link(root / "inputs" / "expectations.json", "모델에 보내지 않은 기대 행동") + '</p></section>')
    body.append('<footer>' + link(root / "report.json", "전체 실험 기록 JSON") + ' · '
                + link(root / "progress.jsonl", "단계별 진행 기록") + ' · '
                + link(root / "memory_diff.json", "기억 변경 전후 JSON") + '</footer>')

    css = """
    :root{color-scheme:light;font-family:Segoe UI,Malgun Gothic,system-ui,sans-serif;color:#172535;background:#f2f5f8}
    *{box-sizing:border-box}body{margin:0;line-height:1.65}main{max-width:1320px;margin:auto;padding:36px 24px 64px}
    header{padding:12px 4px 20px}h1{font-size:clamp(25px,3.2vw,38px);line-height:1.3;margin:8px 0 16px;max-width:950px}
    h2{font-size:23px;margin:0 0 18px}h3{font-size:18px;margin:20px 0 10px}h4{font-size:15px;margin:20px 0 8px}
    p{margin:10px 0}.eyebrow{font-size:14px;letter-spacing:.03em;color:#346378}section{background:white;border:1px solid #dce4ec;border-radius:16px;padding:26px;margin:22px 0}
    .metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:10px 0 22px}.metrics div{background:#e7edf4;border-radius:12px;padding:16px 20px}
    dt{font-size:14px;color:#46576a}dd{font-size:28px;font-weight:700;margin:4px 0 0}.badge{display:inline-block;border-radius:20px;padding:7px 16px;font-weight:600}
    .pass-bg{background:#e0f2e8;color:#175d3a}.fail-bg{background:#fff0de;color:#844510}.notice{border-left:6px solid #d78634}
    .table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:15px;text-align:left}th,td{padding:14px 13px;border-bottom:1px solid #dde5ed;vertical-align:top;min-width:120px}
    thead th{background:#edf2f7;font-weight:650}tbody th{font-weight:600;min-width:170px}.pass{color:#17673b;font-weight:600}.fail{color:#a2362d;font-weight:600}.muted{color:#647183;font-size:14px}
    .results{display:grid;grid-template-columns:1fr 1fr;gap:18px}.result{padding:0 20px 18px;border:1px solid #dce4ec;border-radius:12px;background:#fcfdff}.action{font-size:19px;font-weight:650}
    pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f4f8;border-radius:8px;padding:14px;font:14px/1.65 Consolas,Malgun Gothic,monospace;max-height:620px;overflow:auto}
    a{color:#175b93;text-underline-offset:3px}.frames{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.frames figure{margin:0;padding:8px;border:1px solid #dce4ec;border-radius:10px}
    img{width:100%;height:auto;display:block;border-radius:6px}figcaption{font-size:13px;color:#536174;padding:8px 4px 2px}details{border-top:1px solid #dce4ec;padding:16px 0}summary{cursor:pointer;font-weight:600}
    .limits{background:#edf3f8}.limits li{margin:10px 0}footer{color:#647183;font-size:14px;padding:12px 4px}
    @media(max-width:800px){main{padding:20px 12px 40px}section{padding:18px}.metrics{grid-template-columns:repeat(2,1fr)}.results,.frames{grid-template-columns:1fr}}
    """
    document = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>PAM 아침 실험 — 기억 갱신 전후 결과</title><style>' + css + '</style></head><body><main>'
                + ''.join(body) + '</main></body></html>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="저장된 PAM 실험 결과를 한국어 HTML로 모읍니다. API를 호출하지 않습니다.")
    parser.add_argument("--experiment-dir", type=Path, required=True, help="report.json이 들어 있는 실험 결과 폴더")
    parser.add_argument("--output", type=Path, help="출력 HTML 경로; 기본값은 실험 폴더의 결과모음.html")
    args = parser.parse_args(argv)
    try:
        path = build_report(args.experiment_dir, args.output)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "created", "html_path": str(path), "api_called": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
