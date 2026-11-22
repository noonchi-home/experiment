"""Single-attempt transport to a self-hosted vLLM server (OpenAI-compatible API).

Same bundle contract as pam.inference.infer_bundle: one call, no retry, no
response repair, nothing executed. Thinking is on only for the reflector, via
``chat_template_kwargs.enable_thinking``. The response is streamed so that an HTTP
proxy idle timeout cannot cut a long reflection. Images are sent as the prepared
PNG bytes. An optional bearer key is read from VLLM_API_KEY and never logged.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .contracts import ContractError, parse_prediction, validate_memory
from .inference import _verify_prepared_images
from .messages import read_json

MODEL = "Qwen/Qwen3.5-27B"
MAX_TOKENS = {"predictor": 2048, "reflector": 16384}


def _save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_payload(bundle: dict, *, model: str = MODEL, max_tokens: dict = MAX_TOKENS) -> dict:
    _verify_prepared_images(bundle)
    generation = bundle["generation"]
    thinking = bundle["role"] == "reflector"
    if generation != {"temperature": 0.3, "enable_thinking": thinking}:
        raise ContractError("Paper temperature or role-specific thinking setting has changed.")
    system, user = bundle["messages"]
    content = []
    for part in user["content"]:
        if part["type"] == "text":
            content.append({"type": "text", "text": part["text"]})
        elif part["type"] == "image_file":
            data = Path(part["path"]).read_bytes()
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(data).decode("ascii")}})
        else:
            raise ContractError("Unsupported content part; input is not silently dropped.")
    return {"model": model, "messages": [{"role": "system", "content": system["content"]},
                                         {"role": "user", "content": content}],
            "temperature": generation["temperature"], "max_tokens": max_tokens[bundle["role"]],
            "stream": True, "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": thinking}}


def _request_record(payload: dict) -> dict:
    recorded = json.loads(json.dumps(payload))
    for part in recorded["messages"][1]["content"]:
        if part["type"] == "image_url":
            raw = base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
            part["image_url"] = {"encoding": "embedded PNG base64", "bytes": len(raw),
                                 "sha256": hashlib.sha256(raw).hexdigest()}
    return recorded


def stream_completion(base_url: str, payload: dict, *, timeout: float) -> dict:
    """POST once and assemble the streamed chunks. Raises URLError/HTTPError/OSError."""
    # A proxy in front of the server (Cloudflare on RunPod) rejects the default Python-urllib agent.
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream",
               "User-Agent": "pam-routine-experiment/1.0"}
    key = os.environ.get("VLLM_API_KEY")
    if key:
        headers["Authorization"] = "Bearer " + key
    request = Request(base_url.rstrip("/") + "/v1/chat/completions",
                      data=json.dumps(payload).encode("utf-8"), method="POST", headers=headers)
    started = time.perf_counter()
    content, reasoning, finish, model, identifier, usage = [], [], None, None, None, None
    with urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            model, identifier = chunk.get("model", model), chunk.get("id", identifier)
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    content.append(delta["content"])
                thought = delta.get("reasoning_content") or delta.get("reasoning")
                if thought:
                    reasoning.append(thought)
                finish = choice.get("finish_reason") or finish
    return {"content": "".join(content), "reasoning": "".join(reasoning), "finish_reason": finish,
            "model": model, "id": identifier, "usage": usage, "elapsed_seconds": time.perf_counter() - started}


def _strict_json(raw: str) -> object:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ContractError("Response has duplicate JSON keys.")
            value[key] = item
        return value

    def reject(value):
        raise ContractError(f"Response has an invalid JSON constant: {value}")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject)


def infer_bundle_vllm(bundle_path: Path, output: Path, *, base_url: str, model: str = MODEL,
                      timeout: float = 1800, max_tokens: dict = MAX_TOKENS) -> dict:
    """Use an already-created empty output directory. One call, no retries."""
    output = Path(output)
    bundle = read_json(bundle_path)
    payload = build_payload(bundle, model=model, max_tokens=max_tokens)
    _save(output / "request_record.json", {"base_url": base_url, **_request_record(payload)})
    base = {"backend": "vllm", "base_url": base_url, "requested_model": model, "role": bundle["role"],
            "action_executed": False, "checked_at": None}
    try:
        response = stream_completion(base_url, payload, timeout=timeout)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        status = getattr(error, "code", None)
        result = {**base, "status": "api_error", "api_request_attempted": True,
                  "model_response_received": False, "http_status": status,
                  "error_type": type(error).__name__, "error": str(error)[:500]}
        _save(output / "api_error.json", result)
        return result
    _save(output / "api_response.raw.json", response)
    raw = response["content"]
    if response["finish_reason"] != "stop":
        checked = {"status": "invalid", "raw_response": raw, "errors": [
            f"Incomplete completion: finish_reason={response['finish_reason']!r}"]}
    elif bundle["role"] == "predictor":
        checked = parse_prediction(raw.strip(), bundle["tasks"])
        if response["reasoning"].strip():
            checked = {"status": "invalid", "raw_response": raw, "prediction": None,
                       "errors": ["Predictor returned thinking although enable_thinking=false."]}
    else:
        try:
            memory = validate_memory(_strict_json(raw.strip()), bundle["memory_kind"])
            checked = {"status": "valid", "raw_response": raw, "memory": memory, "errors": []}
        except (ValueError, TypeError) as error:
            checked = {"status": "invalid", "raw_response": raw, "memory": None, "errors": [str(error)]}
    result = {**base, **checked, "checked_at": datetime.now(timezone.utc).isoformat(),
              "api_request_attempted": True, "model_response_received": True,
              "response_model": response["model"], "response_id": response["id"],
              "finish_reason": response["finish_reason"], "usage": response["usage"],
              "elapsed_seconds": response["elapsed_seconds"],
              "reasoning_characters": len(response["reasoning"])}
    _save(output / "result.json", result)
    if checked["status"] == "valid" and bundle["role"] == "reflector":
        (output / "memory.json").write_text(json.dumps(checked["memory"], ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    return result
