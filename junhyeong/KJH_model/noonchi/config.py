"""config/ 폴더의 설정을 읽는다(ai 폴더 config/와 같은 역할). 코드의 기본값은 모두 여기서 온다."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"


def load(name: str) -> dict:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_env(path: Path) -> None:
    """KEY=VALUE 줄만 읽는다. 이미 있는 환경 변수는 덮어쓰지 않는다."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


MODEL = load("model.json")
