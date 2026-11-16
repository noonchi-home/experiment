"""Run one prepared bundle and preserve the actual response without executing actions."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .contracts import ContractError, parse_prediction, validate_candidate_memory, validate_marks, validate_memory
from .messages import predictor_image_count, read_json
from .openrouter import (MODEL, OpenRouterError, build_request, build_text_request, load_openrouter_config,
                         load_text_config, send_request, send_text_request)


def _save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _request_record(payload: dict) -> dict:
    """Keep exact request settings and text, plus image hashes instead of duplicated base64."""
    recorded = json.loads(json.dumps(payload))
    for part in recorded["messages"][1]["content"]:
        if part.get("type") == "image_url":
            image_url = part["image_url"]
            raw = base64.b64decode(image_url["url"].split(",", 1)[1], validate=True)
            part["image_url"] = {"encoding": "embedded PNG base64",
                                 "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            if "detail" in image_url:
                part["image_url"]["detail"] = image_url["detail"]
    return recorded


def _verify_prepared_images(bundle: dict) -> None:
    if bundle.get("status") != "prepared" or bundle.get("execution_mode") != "offline_preparation":
        raise ContractError("Inference requires a successfully prepared input bundle.")
    expected_count = predictor_image_count(bundle) if bundle.get("role") == "predictor" else None
    if bundle.get("role") == "reflector":
        expected_count = bundle.get("frame_count", 200)
        if type(expected_count) is not int or expected_count not in (50, 100, 150, 200):
            raise ContractError("Reflector frame count must be 50, 100, 150, or the paper default 200.")
        if expected_count != 200 and bundle.get("frame_count_source") != "explicit_user_override":
            raise ContractError("Reduced-frame reflection requires an explicit user override declaration.")
    elif bundle.get("role") != "predictor":
        raise ContractError("Prepared bundle role must be predictor or reflector.")
    frames = bundle.get("frames")
    if not isinstance(frames, list) or len(frames) != expected_count:
        raise ContractError("Prepared frame metadata is missing or has the wrong count.")
    parts = [part for part in bundle["messages"][1]["content"] if part.get("type") == "image_file"]
    if len(parts) != len(frames):
        raise ContractError("Prepared image metadata and message image counts differ.")
    for frame, part in zip(frames, parts):
        path = Path(frame["image_path"]).resolve()
        if path != Path(part["path"]).resolve():
            raise ContractError("The prepared image order has changed.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != frame["sha256"]:
            raise ContractError("A prepared image changed after preparation; prepare a new bundle.")


def inspect_completion(response: dict, bundle: dict) -> dict:
    """Validate visible JSON only; never treat truncation/errors as NO_ACT."""
    choice = response["choices"][0]
    message = choice.get("message")
    raw = message.get("content") if isinstance(message, dict) else None
    finish = choice.get("finish_reason")
    if response.get("model") != MODEL:
        return {"status": "invalid", "raw_response": raw, "prediction": None,
                "selected_action": None, "errors": ["Response model does not match qwen/qwen3.5-27b."]}
    if finish != "stop" or not isinstance(raw, str):
        return {"status": "invalid", "raw_response": raw, "prediction": None,
                "selected_action": None, "errors": [f"Incomplete text completion: finish_reason={finish!r}"]}
    if bundle["role"] == "predictor":
        return parse_prediction(raw, bundle["tasks"])
    # Reuse strict JSON handling without silently extracting a code-fenced block.
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ContractError("Memory response has duplicate JSON keys.")
            obj[key] = value
        return obj

    def reject_constant(value):
        raise ContractError(f"Memory response has invalid JSON constant: {value}")

    try:
        memory = json.loads(raw, object_pairs_hook=unique, parse_constant=reject_constant)
        validate_memory(memory, bundle["memory_kind"])
        return {"status": "valid", "raw_response": raw, "memory": memory,
                "memory_automatically_applied": False, "errors": []}
    except (ValueError, TypeError) as exc:
        return {"status": "invalid", "raw_response": raw, "memory": None, "errors": [str(exc)]}


def _write_review(output: Path, result: dict, bundle: dict) -> None:
    valid = result["status"] == "valid"
    action = result.get("selected_action_ko")
    if not valid:
        action = "판단 결과 오류 — 대기나 행동 선택으로 해석하지 않습니다."
    elif bundle["role"] == "reflector":
        action = "새 기억 JSON 생성 완료 — 기억을 적용할 날짜는 별도 저장 절차에서 지정합니다."
    prediction = result.get("prediction") or {}
    text = ["PAM 실제 모델 호출 결과", "", f"결과: {action}",
            "로봇은 움직이지 않았으며, 출력한 행동을 실행 완료로 기록하지 않았습니다.",
            f"요청한 모델: {result['requested_model']}",
            f"응답 모델: {result.get('response_model')}", f"응답 제공자: {result.get('provider')}",
            f"호출에 걸린 시간: {result['elapsed_seconds']:.3f}초", "",
            "모델의 관찰 문장(응답 원문):", prediction.get("observation", ""), "",
            "모델의 짧은 판단 근거(응답 원문):", prediction.get("reasoning", ""), "",
            "구조 검사 통과는 행동이 적절하다는 평가가 아닙니다. 입력 사진과 함께 확인하세요."]
    if valid and bundle["role"] == "reflector":
        text += ["", "모델이 반환한 새 기억(문구를 직접 수정하지 않음):", result["raw_response"]]
    (output / "결과.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    frames_html = "".join(
        f'<figure><figcaption>{html.escape(frame["timestamp"])}</figcaption>'
        f'<img src="{html.escape(Path(frame["image_path"]).as_uri(), quote=True)}" '
        'alt="같은 시점의 왼쪽·오른쪽 카메라 합성 사진"></figure>'
        for frame in bundle["frames"])
    content = ("<!doctype html><html lang='ko'><meta charset='utf-8'>"
               "<title>PAM 판단 결과</title><style>body{font:17px/1.6 system-ui;margin:32px auto;max-width:1100px;padding:0 20px}"
               "h1{font-size:28px}pre{white-space:pre-wrap}img{width:100%;height:auto}figure{margin:24px 0}"
               "figcaption{font-size:14px;color:#555}</style><h1>" + html.escape(action or "결과 확인")
               + "</h1><pre>" + html.escape("\n".join(text[2:])) + "</pre><h2>모델에게 보낸 사진</h2>"
               + frames_html + "</html>")
    (output / "결과.html").write_text(content, encoding="utf-8")


def infer_bundle(bundle_path: Path, config_path: Path, output: Path, *, run_state: dict | None = None) -> dict:
    """Use an already-created empty result directory. One call, no retries."""
    state = run_state if run_state is not None else {}
    state.update({"api_request_attempted": False, "model_response_received": False})
    bundle = read_json(bundle_path)
    _verify_prepared_images(bundle)
    config = load_openrouter_config(config_path)
    payload = build_request(bundle, config)
    _save(output / "request_record.json", _request_record(payload))
    _save(output / "input_reference.json", {
        "path": str(bundle_path.resolve()), "sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
        "provider_config": config, "action_executed": False,
    })
    if not os.environ.get(config["api_key_env"]):
        raise OpenRouterError("OPENROUTER_API_KEY is not set; no API call was made.")
    try:
        state["api_request_attempted"] = True
        predictor_images = predictor_image_count(bundle) if bundle["role"] == "predictor" else 5
        transport = send_request(payload, config, predictor_images=predictor_images)
    except OpenRouterError as exc:
        state["api_request_attempted"] = exc.elapsed_seconds is not None
        error = {"status": "api_error", "api_request_attempted": state["api_request_attempted"],
                 "model_response_received": False, "model_result": None, "action_executed": False,
                 "error": str(exc), "http_status": exc.http_status,
                 "elapsed_seconds": exc.elapsed_seconds, "error_code": exc.error_code,
                 "diagnostic": exc.diagnostic}
        _save(output / "api_error.json", error)
        return error
    state["model_response_received"] = True
    response = transport["response"]
    (output / "api_response.raw.json").write_text(transport["raw_response"], encoding="utf-8")
    checked = inspect_completion(response, bundle)
    if str(response.get("provider", "")).casefold() != config["provider"]["order"][0].casefold():
        checked = {"status": "invalid", "raw_response": checked.get("raw_response"), "prediction": None,
                   "selected_action": None, "errors": ["Response provider does not match the pinned provider."]}
    message = response["choices"][0].get("message") or {}
    usage = response.get("usage") or {}
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    separate_reasoning = bool(message.get("reasoning") or message.get("reasoning_details"))
    if bundle["role"] == "predictor" and (separate_reasoning or isinstance(reasoning_tokens, (int, float)) and reasoning_tokens > 0):
        checked = {"status": "invalid", "raw_response": checked.get("raw_response"), "prediction": None,
                   "selected_action": None, "errors": ["Predictor returned separate thinking despite reasoning.enabled=false."]}
    result = {**checked, "checked_at": datetime.now(timezone.utc).isoformat(),
              "api_request_attempted": True, "model_response_received": True,
              "action_executed": False, "semantic_accuracy_evaluated": False,
              "requested_model": payload["model"], "response_model": response.get("model"),
              "provider": response.get("provider"), "response_id": response.get("id"),
              "finish_reason": response["choices"][0].get("finish_reason"),
              "elapsed_seconds": transport["elapsed_seconds"], "usage": response.get("usage"),
              "reasoning_requested": payload["reasoning"], "role": bundle["role"],
              "thinking_observation": {"reported_reasoning_tokens": reasoning_tokens,
                                        "separate_reasoning_returned": separate_reasoning,
                                        "internal_execution_proven": False}}
    if checked["status"] == "valid" and bundle["role"] == "predictor":
        index = checked["prediction"]["task_index"]
        labels = (bundle.get("scenario") or {}).get("action_labels_ko")
        result["selected_action_ko"] = (
            "대기 — 지금은 아무 행동도 하지 않기" if index == -1
            else labels[index] if labels is not None else checked["selected_action"])
    _save(output / "result.json", result)
    if checked["status"] == "valid" and bundle["role"] == "reflector":
        (output / "memory.json").write_bytes(checked["raw_response"].encode("utf-8"))
    _write_review(output, result, bundle)
    return result


# Text version of the nightly steps (reflector_text, marking).

def _strict_json(raw: str):
    """Only a complete JSON value; duplicate keys and nonstandard constants are refused."""
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ContractError("Response has duplicate JSON keys.")
            obj[key] = value
        return obj

    def reject_constant(value):
        raise ContractError(f"Response has invalid JSON constant: {value}")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject_constant)


def inspect_text_completion(response: dict, bundle: dict) -> dict:
    """Right model, complete answer, strict JSON in the shape of the bundle's role."""
    choice = response["choices"][0]
    message = choice.get("message")
    raw = message.get("content") if isinstance(message, dict) else None
    finish = choice.get("finish_reason")
    if response.get("model") != MODEL:
        return {"status": "invalid", "raw_response": raw, "output": None,
                "errors": ["Response model does not match qwen/qwen3.5-27b."]}
    if finish != "stop" or not isinstance(raw, str):
        return {"status": "invalid", "raw_response": raw, "output": None,
                "errors": [f"Incomplete text completion: finish_reason={finish!r}"]}
    try:
        value = _strict_json(raw)
        role = bundle["role"]
        if role == "reflector_text":
            validate_candidate_memory(value)
        elif role == "marking":
            validate_marks(value, [tuple(pair) for pair in bundle["asked_candidates"]], bundle["asked_actions"],
                           within=(bundle["first_time"], bundle["last_time"], bundle["line_seconds"]))
        else:
            raise ContractError(f"Unknown text role: {role!r}")
    except (ValueError, TypeError, KeyError) as exc:
        return {"status": "invalid", "raw_response": raw, "output": None, "errors": [str(exc)]}
    return {"status": "valid", "raw_response": raw, "output": value, "errors": []}


def infer_text_bundle(bundle_path: Path, config_path: Path, output: Path) -> dict:
    """Text-step version of infer_bundle: one call, no retries, into an existing folder."""
    bundle = read_json(bundle_path)
    if bundle.get("status") != "prepared" or bundle.get("execution_mode") != "offline_preparation":
        raise ContractError("Inference requires a successfully prepared input bundle.")
    config = load_text_config(config_path)
    payload = build_text_request(bundle, config)
    _save(output / "request_record.json", payload)
    _save(output / "input_reference.json", {
        "path": str(bundle_path.resolve()), "sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
        "provider_config": config, "action_executed": False,
    })
    if not os.environ.get(config["api_key_env"]):
        raise OpenRouterError("OPENROUTER_API_KEY is not set; no API call was made.")
    try:
        transport = send_text_request(payload, config, role=bundle["role"])
    except OpenRouterError as exc:
        error = {"status": "api_error", "api_request_attempted": exc.elapsed_seconds is not None,
                 "model_response_received": False, "output": None, "action_executed": False,
                 "error": str(exc), "http_status": exc.http_status, "elapsed_seconds": exc.elapsed_seconds,
                 "error_code": exc.error_code, "diagnostic": exc.diagnostic}
        _save(output / "api_error.json", error)
        return error
    response = transport["response"]
    (output / "api_response.raw.json").write_text(transport["raw_response"], encoding="utf-8")
    checked = inspect_text_completion(response, bundle)
    if str(response.get("provider", "")).casefold() != config["provider"]["order"][0].casefold():
        checked = {"status": "invalid", "raw_response": checked.get("raw_response"), "output": None,
                   "errors": ["Response provider does not match the pinned provider."]}
    message = response["choices"][0].get("message") or {}
    usage = response.get("usage") or {}
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    separate_reasoning = bool(message.get("reasoning") or message.get("reasoning_details"))
    if not bundle["generation"]["enable_thinking"] and (
            separate_reasoning or isinstance(reasoning_tokens, (int, float)) and reasoning_tokens > 0):
        checked = {"status": "invalid", "raw_response": checked.get("raw_response"), "output": None,
                   "errors": ["Thinking was returned although it was turned off for this step."]}
    result = {**checked, "checked_at": datetime.now(timezone.utc).isoformat(), "role": bundle["role"],
              "api_request_attempted": True, "model_response_received": True, "action_executed": False,
              "requested_model": payload["model"], "response_model": response.get("model"),
              "provider": response.get("provider"), "response_id": response.get("id"),
              "finish_reason": response["choices"][0].get("finish_reason"),
              "elapsed_seconds": transport["elapsed_seconds"], "usage": response.get("usage")}
    _save(output / "result.json", result)
    return result
