"""사진 -> 관찰 프레임. OpenRouter의 Chat Completions API를 쓴다(표준 라이브러리만).
VLM은 Qwen3.5-27B 하나만 쓴다: OpenRouter, Alibaba 제공자 고정, 다른 제공자로 넘기지 않음,
temperature 0.3, thinking 끔, 문맥 압축 끔.
모델은 observation.py의 정해진 단어로 보이는 것만 말한다(Structured Outputs, strict). 
영상은 2초 창의 연속 프레임을 한 번에 보내고, 창 하나에 관찰 하나를 받는다.
그 뒤(트리거, task, 허브·로봇 요청, FSM 수정)는 모두 결정론적 코드다.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

from .config import MODEL, load
from .observation import CONFIDENCE, LABELS, PLACES, SURFACES, normalize

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}


def _provider(cfg: dict) -> dict:
    """config/<제공자>.json -> 요청에 쓸 값. 값이 null인 항목은 요청에 넣지 않는다."""
    extra = dict(cfg.get("generation") or {})
    if cfg["max_tokens"].get("observer") is not None:
        extra["max_tokens"] = cfg["max_tokens"]["observer"]
    if cfg.get("provider") is not None:
        extra["provider"] = cfg["provider"]
    if cfg.get("plugins") is not None:
        extra["plugins"] = cfg["plugins"]
        extra["stream"] = False  # ai/pam/openrouter.py와 같은 요청 필드
    return {"model": cfg["model"], "base_url": cfg["endpoint"].removesuffix("/chat/completions"),
            "key_env": cfg["api_key_env"], "timeout": cfg["timeout_seconds"], "extra": extra}


PROVIDERS = {name: _provider(load(file)) for name, file in MODEL["observer"]["providers"].items()}
DEFAULT_PROVIDER = MODEL["observer"]["provider_default"]

def _obj(required: list[str], props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": required, "properties": props}


SCHEMA = _obj(["summary", "people", "time", "objects"], {
    "summary": {"type": "string"},
    "people": {"type": "array", "items": _obj(["location", "activity"], {
        "location": {"type": "string", "enum": PLACES}, "activity": {"type": "string"}})},
    "time": {"type": "string"},  # 우선 코드가 사용자 메시지로 알려 준 시각을 그대로 적게 하지만 추후 실제 시각으로 변경
    "objects": {"type": "array", "items": _obj(["label", "name", "on", "attributes", "confidence"], {
        "label": {"type": "string", "enum": LABELS},
        "name": {"type": "string"},
        "on": {"type": "string", "enum": SURFACES},
        "attributes": {"type": "array", "items": _obj(["name", "value"], {
            "name": {"type": "string"}, "value": {"type": "string"}})},
        "confidence": {"type": "string", "enum": CONFIDENCE}})},
})

SYSTEM_PROMPT = f"""You record what a fixed camera inside a home sees. Write only what is visible; do not guess. Write everything in English.

- people: write only location ({", ".join(PLACES)}) and activity (what the person is doing, e.g. "drinking coffee from a mug", "pouring coffee"). Do not write anything that could identify a person, such as face or clothing.
- objects: choose each label only from: {", ".join(LABELS)}. If it is not in the list, use "other" and write its real name in name. on is where the object rests: {", ".join(SURFACES)}. Do not list objects a person is holding; mention them in activity instead.
- In object attributes, write only states used for decisions, such as "contents" (empty / some left / unknown). If a state cannot be confirmed, set value to "unknown".
- time: copy the time given in the request exactly."""


class VisionError(RuntimeError):
    pass


def image_to_data_url(path: str | Path) -> str:
    p = Path(path)
    mime = MIME.get(p.suffix.lower())
    if mime is None:
        raise VisionError(f"unsupported image format: {p.suffix} (png, jpg, webp, gif)")
    if not p.is_file():
        raise VisionError(f"image file not found: {p}")
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
        # Redirect로 Authorization Header가 다른 주소에 넘어가지 않게 한다


class VisionClient:
    def __init__(self, api_key: str, provider: str = DEFAULT_PROVIDER, model: str | None = None,
                 base_url: str | None = None, timeout: float | None = None):
        if provider not in PROVIDERS:
            raise VisionError(f"unknown VLM provider: {provider} (allowed: {', '.join(PROVIDERS)})")
        spec = PROVIDERS[provider]
        if not api_key:
            raise VisionError(f"{spec['key_env']} is not set. Put it in .env (see the README).")
        self.api_key = api_key
        self.provider = provider
        self.model = model or spec["model"]
        self.base_url = (base_url or spec["base_url"]).rstrip("/")
        self.extra = spec["extra"]
        self.timeout = timeout or spec["timeout"]
        self.usage = {"calls": 0, "total_tokens": 0}

    @staticmethod
    def key_env(provider: str = DEFAULT_PROVIDER) -> str:
        return PROVIDERS[provider]["key_env"]

    def build_payload(self, image_path: str | Path | list, time: str, clip: dict | None = None) -> dict:
        """image_path는 리스트일 수 있다. clip({fps, end})을 주면 한 고정 카메라 영상의 연속 프레임으로 보낸다."""
        paths = image_path if isinstance(image_path, (list, tuple)) else [image_path]
        if clip:
            text = (f"The {len(paths)} photos below are consecutive frames ({clip['fps']} per second) from one fixed camera, "
                    f"from {time} to {clip['end']}. Record what happens in this clip as one observation. "
                    "List each object and person only once.")
        elif len(paths) == 1:
            text = "Record the scene in this photo."
        else:
            text = (f"The {len(paths)} photos below show the same moment from different fixed cameras. "
                    "Look at them together and record them as one scene. List each object and person only once.")
        text += f"\ntime: {time}"
        images = [{"type": "image_url", "image_url": {"url": image_to_data_url(p)}} for p in paths]
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [{"type": "text", "text": text}, *images]},
            ],
            "response_format": {"type": "json_schema", "json_schema": {"name": "observation", "strict": True, "schema": SCHEMA}},
            **json.loads(json.dumps(self.extra)),  # 설정을 복사해 요청마다 같은 값을 보낸다
        }

    def describe(self, image_path: str | Path | list, time: str, clip: dict | None = None) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(self.build_payload(image_path, time, clip)).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.build_opener(_NoRedirect()).open(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read())["error"]["message"]
            except Exception:
                msg = e.reason
            raise VisionError(f"API error {e.code}: {msg}") from None
        except urllib.error.URLError as e:
            raise VisionError(f"cannot reach the server: {e.reason}") from None
        except TimeoutError:
            raise VisionError(f"response timed out ({self.timeout:g} s)") from None

        self.usage["calls"] += 1
        self.usage["total_tokens"] += (body.get("usage") or {}).get("total_tokens", 0)
        if "error" in body:  # OpenRouter는 200 응답 안에 제공자 오류를 담기도 한다
            raise VisionError(f"provider error: {body['error'].get('message', body['error'])}")
        choice = body["choices"][0]
        if choice.get("finish_reason") == "length":
            raise VisionError("response was cut off by max_tokens; not used")
        message = choice["message"]
        if message.get("refusal"):
            raise VisionError(f"the model refused: {message['refusal']}")
        try:
            raw = json.loads(message.get("content") or "")
        except json.JSONDecodeError:
            raise VisionError("model response is not JSON") from None
        paths = image_path if isinstance(image_path, (list, tuple)) else [image_path]
        raw["frame"] = f"{Path(paths[0]).name}..{Path(paths[-1]).name}" if clip else "+".join(Path(p).name for p in paths)
        return normalize(raw, time)
