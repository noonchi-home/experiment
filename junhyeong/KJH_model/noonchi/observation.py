"""관찰 프레임: 영상의 한 창(2초)에서 카메라가 본 것을 정해진 단어로 적은 기록.

VLM 출력이든 사람이 쓴 파일이든 모든 프레임은 다음 형식으로 맞춘다:
  {time, frame, summary, people:[{location, activity}], objects:[{label, name, on, attributes, confidence}]}
가전 상태는 관찰에 넣지 않는다(스마트홈 허브가 알려 준다). 예전 기록에 electronics가 있어도 읽지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path

LABELS = ["cup", "plate", "bowl", "pan", "pot", "kettle", "food", "bottle", "phone", "box", "other"]
SURFACES = ["counter", "kitchen island", "stove", "sink", "table", "shelf", "floor", "other"]
PLACES = ["kitchen", "dining area", "living room", "entrance", "other"]
CONFIDENCE = ["high", "medium", "low"]
UNKNOWN = "unknown"
UNKNOWN_VALUES = {UNKNOWN, "n/a", "not visible", ""}


class ObservationError(ValueError):
    pass


def is_unknown(value) -> bool:
    return value is None or str(value).strip().lower() in UNKNOWN_VALUES


def _pick(value, allowed: list[str], default: str) -> str:
    return value if value in allowed else default


def normalize(raw: dict, time: str | None = None) -> dict:
    """time을 주면 그 값을 쓴다(영상 시작 시각 + 창 위치로 코드가 정한 시각). VLM이 적은 time은 쓰지 않는다."""
    t = time or raw.get("time")
    if not t:
        raise ObservationError("observation has no time")
    objects = []
    for o in raw.get("objects", []):
        label = o.get("label")
        if label not in LABELS:
            raise ObservationError(f"unknown object label: {label} (allowed: {', '.join(LABELS)})")
        attrs = o.get("attributes", {})
        if isinstance(attrs, list):  # VLM 응답 형식 [{name, value}]
            attrs = {a["name"]: a["value"] for a in attrs}
        objects.append({
            "label": label,
            "name": o.get("name") or label,
            "on": _pick(o.get("on"), SURFACES, "other"),
            "attributes": dict(attrs),
            "confidence": _pick(o.get("confidence"), CONFIDENCE, "high"),
        })
    return {
        "time": t,
        "frame": raw.get("frame") or t,
        "summary": raw.get("summary", ""),
        "people": [{"location": _pick(p.get("location"), PLACES, "other"), "activity": p.get("activity", "")}
                   for p in raw.get("people", [])],
        "objects": objects,
    }


def load_frame(path: str | Path, time: str | None = None) -> dict:
    return normalize(json.loads(Path(path).read_text(encoding="utf-8")), time)
