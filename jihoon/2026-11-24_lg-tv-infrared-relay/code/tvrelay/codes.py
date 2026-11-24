"""녹음한 리모컨 신호 저장소: tvrelay/local/codes.json (gitignore).

  { "<이름>": {"kind": "raw", "khz": 38, "ticks": [...], "decoded": {"protocol", "address", "command"} | null, "at": ISO},
    "<이름>": {"kind": "nec", "address": 4, "command": 8} }
원본(raw)은 켜짐·꺼짐 길이(50us 단위) 목록이라 방식을 몰라도 그대로 다시 쏠 수 있다(구형 에어컨·셋톱).
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from .ir import Bridge

DEFAULT = Path(__file__).parent / "local" / "codes.json"
NAME_RE = re.compile(r"^[\w-]{1,40}$")


def load(path: Path = DEFAULT) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def get(name: str, path: Path = DEFAULT) -> dict:
    codes = load(path)
    if name not in codes:
        raise KeyError(f"'{name}' 신호가 없어요. 있는 것: {', '.join(codes) or '없음'} (python -m tvrelay record {name})")
    return codes[name]


def save(name: str, code: dict, path: Path = DEFAULT) -> None:
    if not NAME_RE.match(name):
        raise ValueError("이름은 영문·숫자·_·- 40자 이내로 지어 주세요 (예: aircon_on)")
    codes = load(path)
    codes[name] = code
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(codes, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def record(bridge: Bridge, timeout: float = 30.0, settle: float = 0.8) -> dict | None:
    """리모컨 버튼 한 번을 원본으로 녹음한다. 해석까지 되면(예: NEC) decoded에 같이 적는다. 시간 안에 없으면 None."""
    bridge.raw_report(True)
    try:
        start_raw, start_rx, start_ovf = len(bridge.raws), len(bridge.rx), bridge.overflows
        end = time.time() + timeout
        while time.time() < end and len(bridge.raws) == start_raw:
            if bridge.overflows > start_ovf:
                raise ValueError("신호가 너무 길어 아두이노 버퍼(750칸)를 넘었어요. 버튼을 짧게 눌러 다시 해 보세요")
            time.sleep(0.05)
        if len(bridge.raws) == start_raw:
            return None
        time.sleep(settle)                         # 같은 누름의 해석 줄(RX)이 뒤따라 온다
        raw = bridge.raws[start_raw]
        rx = [r for r in bridge.rx[start_rx:] if abs(r["t"] - raw["t"]) < 1.0]
        decoded = {k: rx[0][k] for k in ("protocol", "address", "command")} if rx else None
        return {"kind": "raw", "khz": 38, "ticks": raw["ticks"], "decoded": decoded,
                "at": datetime.now().isoformat(timespec="seconds")}
    finally:
        bridge.raw_report(False)
