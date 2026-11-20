"""Single-attempt OpenRouter transport for the paper's exact Qwen model.

No API key is read while building a request. No request or response is logged
here. The caller stores responses and checks finish_reason and task semantics.
"""

from __future__ import annotations

import base64
from copy import deepcopy
from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .contracts import ContractError
from .messages import predictor_image_count, read_json


MODEL = "qwen/qwen3.5-27b"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_NO_COMPRESSION = [{"id": "context-compression", "enabled": False}]
_ERROR_BODY_LIMIT = 64 * 1024
_DIAGNOSTIC_TEXT_LIMIT = 2048


class OpenRouterError(ValueError):
    """Static exception text, plus a bounded and redacted diagnostic allowlist."""

    def __init__(self, message: str, *, http_status: int | None = None,
                 elapsed_seconds: float | None = None, error_code: int | None = None,
                 diagnostic: dict | None = None):
        super().__init__(message)
        self.http_status = http_status
        self.elapsed_seconds = elapsed_seconds
        self.error_code = error_code
        self.diagnostic = diagnostic if diagnostic is not None else {}


def _redacted_text(value: object, key: str, *, nested_json: bool = False) -> str:
    """Redact before truncating so a cut string cannot expose a key prefix."""
    if nested_json and isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, RecursionError):
            pass
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError, RecursionError):
            return "[UNREADABLE_DIAGNOSTIC_VALUE]"
    value = re.sub(r"data:image/[^\s,;]+(?:;[^\s,;]+)*;base64,(?:[A-Za-z0-9+/=_\r\n-]|\\[nr/])*",
                   "[REDACTED_IMAGE_DATA]", value, flags=re.IGNORECASE)
    value = re.sub(r"\bBearer[ \t]+[^\s\"'<>;,{}\[\]]+", "Bearer [REDACTED_SECRET]", value, flags=re.IGNORECASE)
    if key:
        value = value.replace(key, "[REDACTED_SECRET]")
    value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED_KEY_LIKE_VALUE]", value, flags=re.IGNORECASE)
    return value if len(value) <= _DIAGNOSTIC_TEXT_LIMIT else value[:_DIAGNOSTIC_TEXT_LIMIT - 1] + "…"


def _error_diagnostic(body: bytes, key: str) -> dict:
    """Retain only error code/message and selected metadata, or a safe text preview."""
    body = body[:_ERROR_BODY_LIMIT]
    diagnostic = {"body_bytes_read": len(body), "body_read_limit": _ERROR_BODY_LIMIT,
                  "body_limit_reached": len(body) == _ERROR_BODY_LIMIT}
    text = body.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except (ValueError, RecursionError):
        diagnostic.update({"format": "non_json", "body_preview": _redacted_text(text, key)})
        return diagnostic
    diagnostic["format"] = "json"
    error = parsed.get("error") if isinstance(parsed, dict) else None
    if not isinstance(error, dict):
        return diagnostic
    selected = {}
    if type(error.get("code")) is int:
        selected["code"] = error["code"]
    elif isinstance(error.get("code"), str):
        selected["code"] = _redacted_text(error["code"], key)
    if isinstance(error.get("message"), str):
        selected["message"] = _redacted_text(error["message"], key)
    metadata = error.get("metadata")
    if isinstance(metadata, dict):
        fields = {}
        for name in ("raw", "provider_name", "request_id"):
            if name in metadata:
                fields[name] = _redacted_text(metadata[name], key, nested_json=name == "raw")
        if fields:
            selected["metadata"] = fields
    diagnostic["error"] = selected
    return diagnostic


def _validate_config(config: dict) -> dict:
    required = {"endpoint", "model", "api_key_env", "provider", "timeout_seconds", "max_tokens"}
    if (not isinstance(config, dict) or not required <= set(config)
            or set(config) - required - {"provenance", "image_detail", "reflector_frame_count"}):
        raise OpenRouterError("Invalid OpenRouter configuration fields.")
    _validate_connection(config)
    limits = config["max_tokens"]
    if not isinstance(limits, dict) or set(limits) != {"predictor", "reflector"}:
        raise OpenRouterError("Provide separate predictor and reflector output-token limits.")
    if any(type(limit) is not int or not 1 <= limit <= 65536 for limit in limits.values()):
        raise OpenRouterError("Output-token limits must be integers from 1 to 65536.")
    reflector_count = config.get("reflector_frame_count", 200)
    if type(reflector_count) is not int or reflector_count not in (50, 100, 150, 200):
        raise OpenRouterError("reflector_frame_count must be 50, 100, 150, or the paper default 200.")
    if "image_detail" in config:
        details = config["image_detail"]
        if (not isinstance(details, dict) or set(details) - {"predictor", "reflector"}
                or any(not isinstance(value, str) or value not in {"auto", "high", "low"}
                       for value in details.values())):
            raise OpenRouterError("image_detail accepts only predictor/reflector roles and auto/high/low values.")
    return config


def _validate_connection(config: dict) -> None:
    """Fixed endpoint, model and key variable, one pinned provider, a bounded timeout."""
    if config["endpoint"] != ENDPOINT or config["model"] != MODEL:
        raise OpenRouterError("The transport requires the fixed OpenRouter endpoint and qwen/qwen3.5-27b model.")
    if config["api_key_env"] != "OPENROUTER_API_KEY":
        raise OpenRouterError("Authentication must use OPENROUTER_API_KEY.")
    provider = config["provider"]
    if (not isinstance(provider, dict)
            or set(provider) != {"order", "allow_fallbacks", "require_parameters"}
            or not isinstance(provider["order"], list) or len(provider["order"]) != 1
            or not isinstance(provider["order"][0], str) or not provider["order"][0].strip()
            or provider["allow_fallbacks"] is not False or provider["require_parameters"] is not True):
        raise OpenRouterError("Pin exactly one provider, disable fallbacks, and require parameter support.")
    timeout = config["timeout_seconds"]
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 600:
        raise OpenRouterError("timeout_seconds must be a finite positive number at most 600.")


def load_openrouter_config(path: Path) -> dict:
    """Read public connection settings; never read or accept a stored secret."""
    try:
        config = read_json(Path(path))
    except (ContractError, OSError, ValueError, TypeError):
        raise OpenRouterError("Cannot read valid OpenRouter configuration JSON.") from None
    return _validate_config(config)


def build_request(bundle: dict, config: dict) -> dict:
    """Encode every PNG; reduced-frame reflection requires an explicit user override."""
    _validate_config(config)
    if not isinstance(bundle, dict) or bundle.get("model") != "Qwen3.5-27B":
        raise OpenRouterError("Input bundle must use the paper's Qwen3.5-27B model.")
    role = bundle.get("role")
    if role not in {"predictor", "reflector"}:
        raise OpenRouterError("Input bundle role must be predictor or reflector.")
    if role == "predictor":
        try:
            expected_count = predictor_image_count(bundle)
        except ContractError as exc:
            raise OpenRouterError(str(exc)) from None
    if role == "reflector":
        expected_count = config.get("reflector_frame_count", 200)
        declared_count = bundle.get("frame_count", 200)
        if type(declared_count) is not int or declared_count != expected_count:
            raise OpenRouterError("Reflector bundle frame count differs from the provider configuration.")
        if declared_count != 200 and bundle.get("frame_count_source") != "explicit_user_override":
            raise OpenRouterError("Reduced-frame reflection requires an explicit user override declaration.")
    generation = bundle.get("generation")
    thinking = role == "reflector"
    if (not isinstance(generation, dict) or set(generation) != {"temperature", "enable_thinking"}
            or type(generation["temperature"]) is not float or generation["temperature"] != 0.3
            or generation["enable_thinking"] is not thinking):
        raise OpenRouterError("Paper temperature or role-specific thinking setting has changed.")
    messages = bundle.get("messages")
    if (not isinstance(messages, list) or len(messages) != 2
            or any(not isinstance(message, dict) or set(message) != {"role", "content"} for message in messages)
            or [message["role"] for message in messages] != ["system", "user"]
            or not isinstance(messages[0]["content"], str) or not messages[0]["content"].strip()
            or not isinstance(messages[1]["content"], list)):
        raise OpenRouterError("Expected the prepared system prompt and user multimodal message.")

    content = []
    image_count = 0
    for part in messages[1]["content"]:
        if not isinstance(part, dict):
            raise OpenRouterError("Invalid multimodal content part.")
        if part.get("type") == "text":
            if set(part) != {"type", "text"} or not isinstance(part["text"], str):
                raise OpenRouterError("Invalid text content part.")
            content.append(dict(part))
        elif part.get("type") == "image_file":
            if (set(part) != {"type", "path", "mime_type"} or part["mime_type"] != "image/png"
                    or not isinstance(part["path"], str)):
                raise OpenRouterError("Expected a composed PNG image file.")
            try:
                data = Path(part["path"]).read_bytes()
            except (OSError, ValueError):
                raise OpenRouterError("Cannot read a composed image file.") from None
            if not data.startswith(_PNG_SIGNATURE):
                raise OpenRouterError("A composed image file is not PNG data.")
            image_url = {"url": "data:image/png;base64," + base64.b64encode(data).decode("ascii")}
            if role in config.get("image_detail", {}):
                image_url["detail"] = config["image_detail"][role]
            content.append({"type": "image_url", "image_url": image_url})
            image_count += 1
        else:
            raise OpenRouterError("Unsupported content part; input is not silently dropped.")
    if image_count != expected_count:
        raise OpenRouterError(f"The {role} request requires exactly {expected_count} composed images.")
    return {
        "model": MODEL,
        "messages": [dict(messages[0]), {"role": "user", "content": content}],
        "temperature": generation["temperature"],
        "reasoning": {"enabled": thinking},
        "max_tokens": config["max_tokens"][role],
        "provider": deepcopy(config["provider"]),
        "stream": False,
        "plugins": deepcopy(_NO_COMPRESSION),
    }


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirect must never forward the authorization header to another URL.
        return None


def _validate_payload(payload: dict, config: dict, predictor_images: int = 5) -> None:
    fields = {"model", "messages", "temperature", "reasoning", "max_tokens", "provider", "stream", "plugins"}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise OpenRouterError("Send only the payload produced by build_request.")
    if (payload["model"] != MODEL or payload["provider"] != config["provider"]
            or type(payload["temperature"]) is not float or payload["temperature"] != 0.3
            or payload["stream"] is not False or payload["plugins"] != _NO_COMPRESSION):
        raise OpenRouterError("The fixed model, provider, or paper transport settings were changed.")
    reasoning = payload["reasoning"]
    if (not isinstance(reasoning, dict) or set(reasoning) != {"enabled"}
            or type(reasoning["enabled"]) is not bool):
        raise OpenRouterError("Use reasoning.enabled; hiding reasoning does not disable it.")
    role = "reflector" if reasoning["enabled"] else "predictor"
    details = config.get("image_detail", {})
    image_fields = {"url", "detail"} if role in details else {"url"}
    if type(payload["max_tokens"]) is not int or payload["max_tokens"] != config["max_tokens"][role]:
        raise OpenRouterError("The request output cap does not match the configured role limit.")
    messages = payload["messages"]
    if (not isinstance(messages, list) or len(messages) != 2
            or any(not isinstance(message, dict) or set(message) != {"role", "content"} for message in messages)
            or [message["role"] for message in messages] != ["system", "user"]
            or not isinstance(messages[0]["content"], str)
            or not isinstance(messages[1]["content"], list)):
        raise OpenRouterError("Invalid request message structure.")
    count = 0
    for part in messages[1]["content"]:
        if not isinstance(part, dict):
            raise OpenRouterError("Invalid request content.")
        if part.get("type") == "text" and set(part) == {"type", "text"} and isinstance(part["text"], str):
            continue
        if (part.get("type") != "image_url" or set(part) != {"type", "image_url"}
                or not isinstance(part["image_url"], dict) or set(part["image_url"]) != image_fields
                or not isinstance(part["image_url"]["url"], str)
                or not part["image_url"]["url"].startswith("data:image/png;base64,")):
            raise OpenRouterError("The request must contain embedded composed PNG images.")
        if role in details and part["image_url"]["detail"] != details[role]:
            raise OpenRouterError("Image detail no longer matches the configured role setting.")
        count += 1
    if count != (config.get("reflector_frame_count", 200) if role == "reflector" else predictor_images):
        raise OpenRouterError("Request image count no longer matches its paper role.")


def send_request(payload: dict, config: dict, *, api_key: str | None = None,
                 predictor_images: int = 5) -> dict:
    """Make one POST; return full JSON/raw text even when output is truncated.

    The optional key is an in-memory injection seam for tests/callers. Production
    callers omit it and use the environment. Exception messages stay static;
    diagnostics contain only bounded, redacted fields from provider errors.
    ``predictor_images`` is the bundle's declared predictor count (paper: 5).
    """
    _validate_config(config)
    _validate_payload(payload, config, predictor_images)
    return _post(payload, config, api_key)


def _post(payload: dict, config: dict, api_key: str | None) -> dict:
    """One POST of an already validated payload; no retry. Shared by both request kinds."""
    key = os.environ.get(config["api_key_env"]) if api_key is None else api_key
    if not isinstance(key, str) or not key or any(not 33 <= ord(char) <= 126 for char in key):
        raise OpenRouterError("OPENROUTER_API_KEY is missing or is not a valid header value.")
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    request = Request(ENDPOINT, data=body, method="POST", headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    started = time.perf_counter()
    try:
        with build_opener(_RejectRedirects()).open(request, timeout=config["timeout_seconds"]) as response:
            status = response.status
            raw_bytes = response.read()
    except HTTPError as error:
        status = error.code
        try:
            diagnostic = _error_diagnostic(error.read(_ERROR_BODY_LIMIT), key)
        except (OSError, HTTPException, ValueError, TypeError):
            diagnostic = {"format": "unreadable", "body_read_limit": _ERROR_BODY_LIMIT,
                          "body_read_failed": True}
        finally:
            error.close()
        code = diagnostic.get("error", {}).get("code")
        raise OpenRouterError("OpenRouter rejected the request; no retry was attempted.",
                              http_status=status, elapsed_seconds=time.perf_counter() - started,
                              error_code=code if type(code) is int else None, diagnostic=diagnostic) from None
    except (TimeoutError, socket.timeout, URLError, OSError):
        raise OpenRouterError("OpenRouter connection failed or timed out; completion and billing are unknown.",
                              elapsed_seconds=time.perf_counter() - started) from None
    elapsed = time.perf_counter() - started
    if not 200 <= status < 300:
        raise OpenRouterError("OpenRouter returned a non-success HTTP status.", http_status=status,
                              elapsed_seconds=elapsed, diagnostic=_error_diagnostic(raw_bytes, key))
    try:
        raw = raw_bytes.decode("utf-8")
        parsed = json.loads(raw)
    except (UnicodeError, ValueError):
        raise OpenRouterError("OpenRouter returned an unreadable JSON response.",
                              http_status=status, elapsed_seconds=elapsed) from None
    if not isinstance(parsed, dict):
        raise OpenRouterError("OpenRouter returned a non-object JSON response.", http_status=status, elapsed_seconds=elapsed)
    if "error" in parsed:
        error = parsed["error"]
        code = error.get("code") if isinstance(error, dict) else None
        raise OpenRouterError("OpenRouter returned an API error in the response body.", http_status=status,
                              elapsed_seconds=elapsed, error_code=code if type(code) is int else None,
                              diagnostic=_error_diagnostic(raw_bytes, key))
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices or any(not isinstance(choice, dict) for choice in choices):
        raise OpenRouterError("OpenRouter returned no completion choices.", http_status=status, elapsed_seconds=elapsed)
    if any("error" in choice or choice.get("finish_reason") == "error" for choice in choices):
        raise OpenRouterError("OpenRouter returned an incomplete provider error.", http_status=status, elapsed_seconds=elapsed)
    # Do not parse task JSON here. In particular, finish_reason='length' remains
    # available for the caller to classify and preserve as a truncated result.
    return {"response": parsed, "raw_response": raw, "elapsed_seconds": elapsed, "http_status": status}


# Text version of the nightly steps: same model, endpoint and pinned provider, no images.
# Thinking stays on only for the reflector, as in the paper.
TEXT_THINKING = {"moments": False, "reflector_text": True, "marking": False, "matching": False,
                 "predictor_text": False}


def _validate_text_config(config: dict) -> dict:
    required = {"endpoint", "model", "api_key_env", "provider", "timeout_seconds", "max_tokens"}
    if not isinstance(config, dict) or not required <= set(config) or set(config) - required - {"provenance"}:
        raise OpenRouterError("Invalid text OpenRouter configuration fields.")
    _validate_connection(config)
    limits = config["max_tokens"]
    if not isinstance(limits, dict) or set(limits) != set(TEXT_THINKING):
        raise OpenRouterError("Provide output-token limits for moments, reflector_text, marking, matching "
                             "and predictor_text.")
    if any(type(limit) is not int or not 1 <= limit <= 65536 for limit in limits.values()):
        raise OpenRouterError("Output-token limits must be integers from 1 to 65536.")
    return config


def load_text_config(path: Path) -> dict:
    """Read the text-step connection settings; never read or accept a stored secret."""
    try:
        config = read_json(Path(path))
    except (ContractError, OSError, ValueError, TypeError):
        raise OpenRouterError("Cannot read valid text OpenRouter configuration JSON.") from None
    return _validate_text_config(config)


def _text_messages(messages: object) -> list[dict]:
    if (not isinstance(messages, list) or len(messages) != 2
            or any(not isinstance(message, dict) or set(message) != {"role", "content"} for message in messages)
            or [message["role"] for message in messages] != ["system", "user"]
            or not isinstance(messages[0]["content"], str) or not messages[0]["content"].strip()
            or not isinstance(messages[1]["content"], list) or not messages[1]["content"]):
        raise OpenRouterError("Expected a system prompt and a text user message.")
    for part in messages[1]["content"]:
        if (not isinstance(part, dict) or part.get("type") != "text" or set(part) != {"type", "text"}
                or not isinstance(part["text"], str)):
            raise OpenRouterError("A text request carries text parts only; images are not sent.")
    return messages


def build_text_request(bundle: dict, config: dict) -> dict:
    _validate_text_config(config)
    role = bundle.get("role") if isinstance(bundle, dict) else None
    if role not in TEXT_THINKING:
        raise OpenRouterError("Text bundle role must be moments, reflector_text, marking, matching or "
                             "predictor_text.")
    if bundle.get("model") != "Qwen3.5-27B":
        raise OpenRouterError("Input bundle must use the paper's Qwen3.5-27B model.")
    generation = bundle.get("generation")
    if (not isinstance(generation, dict) or set(generation) != {"temperature", "enable_thinking"}
            or type(generation["temperature"]) is not float or not 0.0 <= generation["temperature"] <= 1.0
            or generation["enable_thinking"] is not TEXT_THINKING[role]):
        raise OpenRouterError("Text role temperature or thinking setting is invalid.")
    messages = _text_messages(bundle.get("messages"))
    return {
        "model": MODEL,
        "messages": [dict(messages[0]), {"role": "user", "content": [dict(p) for p in messages[1]["content"]]}],
        "temperature": generation["temperature"],
        "reasoning": {"enabled": TEXT_THINKING[role]},
        "max_tokens": config["max_tokens"][role],
        "provider": deepcopy(config["provider"]),
        "stream": False,
        "plugins": deepcopy(_NO_COMPRESSION),
    }


def send_text_request(payload: dict, config: dict, *, role: str, api_key: str | None = None) -> dict:
    """One POST of a text payload built for `role`; no retry and no images."""
    _validate_text_config(config)
    fields = {"model", "messages", "temperature", "reasoning", "max_tokens", "provider", "stream", "plugins"}
    if role not in TEXT_THINKING or not isinstance(payload, dict) or set(payload) != fields:
        raise OpenRouterError("Send only the payload produced by build_text_request.")
    if (payload["model"] != MODEL or payload["provider"] != config["provider"]
            or type(payload["temperature"]) is not float or not 0.0 <= payload["temperature"] <= 1.0
            or payload["reasoning"] != {"enabled": TEXT_THINKING[role]}
            or payload["max_tokens"] != config["max_tokens"][role]
            or payload["stream"] is not False or payload["plugins"] != _NO_COMPRESSION):
        raise OpenRouterError("The text payload does not match its role settings.")
    _text_messages(payload["messages"])
    return _post(payload, config, api_key)
