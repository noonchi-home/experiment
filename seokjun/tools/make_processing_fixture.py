"""Make small colored-image fixtures, NOT household scenes or evaluation data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image


def create_fixture(output: Path, count: int = 201) -> dict:
    if type(count) is not int or count < 1:
        raise ValueError("count must be a positive integer")
    output.mkdir(parents=True, exist_ok=False)
    images = output / "camera_files"
    images.mkdir()
    start = datetime.fromisoformat("2026-10-24T07:00:00+09:00")
    observations = []
    for index in range(count):
        left, right = f"camera_files/left_{index:04d}.png", f"camera_files/right_{index:04d}.png"
        Image.new("RGB", (32, 24), (200, index % 256, 0)).save(output / left)
        Image.new("RGB", (40, 24), (0, index % 256, 200)).save(output / right)
        observations.append({"timestamp": (start + timedelta(seconds=index)).isoformat(),
                             "left_image": left, "right_image": right})
    # This is an empty memory shape fixture, not a learned habit or paper result.
    fsm = {"initial_state": "fixture", "states": [
        {"id": "fixture", "description": "Processing fixture only.", "rules": [], "next": []}]}
    files = {
        "observations.json": {"observations": observations},
        "fsm_memory.json": fsm, "list_memory.json": {"rules": []},
        "fixture_provenance.json": {
            "purpose": "Image processing and message assembly verification only",
            "evaluation_data": False, "real_household_scene": False,
            "generated_model_response": False, "timestamp_source": "artificial 1 Hz schedule",
            "memory_source": "Manually constructed empty schema fixture, not learned memory",
        },
    }
    for name, value in files.items():
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "summary.txt").write_text(
        "Processing fixture only; no person acted and no robot action was executed.\n", encoding="utf-8")
    return {"output": str(output.resolve()), "observations": count, "evaluation_data": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=201)
    args = parser.parse_args()
    print(json.dumps(create_fixture(args.output, args.count)))
