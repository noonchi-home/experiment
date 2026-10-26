"""Split generated camera-pair assets; never generate or retouch scene pixels."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(sequence: str, dataset: Path) -> dict:
    hour = {"wakeup": 7, "cleanup": 8}[sequence]
    start = datetime.fromisoformat(f"2026-10-24T{hour:02d}:00:00+09:00")
    observations, records = [], []
    for second in (0, 2, 4, 6, 8):
        pair = dataset / "generatedimages" / f"{sequence}_{second:02d}_pair.png"
        with Image.open(pair) as image:
            image.load()
            if image.width % 2:
                raise ValueError(f"Pair width must divide into two equal panels: {pair}")
            midpoint = image.width // 2
            record = {"second": second, "pair": str(pair.relative_to(dataset)),
                      "pair_sha256": sha256(pair), "pair_size": list(image.size)}
            for side, box in (("left", (0, 0, midpoint, image.height)),
                              ("right", (midpoint, 0, image.width, image.height))):
                destination = pair.with_name(f"{sequence}_{second:02d}_{side}.png")
                panel = image.crop(box)
                if destination.exists():
                    with Image.open(destination) as existing:
                        if existing.size != panel.size or existing.mode != panel.mode or existing.tobytes() != panel.tobytes():
                            raise ValueError(f"Refusing to replace an existing different asset: {destination}")
                else:
                    panel.save(destination, format="PNG")
                record[side] = {"path": str(destination.relative_to(dataset)).replace("\\", "/"),
                                "sha256": sha256(destination), "size": list(panel.size),
                                "crop_box": list(box)}
        observations.append({"timestamp": (start + timedelta(seconds=second)).isoformat(),
                             "left_image": record["left"]["path"],
                             "right_image": record["right"]["path"]})
        records.append(record)
    manifest = dataset / f"{sequence}_observations.json"
    manifest.write_text(json.dumps({"observations": observations}, indent=2) + "\n", encoding="utf-8")
    verification = {"sequence": sequence, "synthetic": True, "real_capture": False,
                    "single_prediction_window": True, "one_hz_continuous_recording": False,
                    "assumed_timestamps": True, "temporal_span_seconds": 8,
                    "sample_interval_seconds": 2, "paired_observation_count": 5,
                    "pixel_operation": "Split exactly at the image midpoint; no resizing, retouching, or scene editing.",
                    "manifest_sha256": sha256(manifest), "assets": records}
    (dataset / f"{sequence}_asset_verification.json").write_text(
        json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    return {"sequence": sequence, "manifest": str(manifest), "pairs": len(observations)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequence", choices=("wakeup", "cleanup", "all"), default="all")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data" / "morning_v1")
    args = parser.parse_args()
    for selected in (("wakeup", "cleanup") if args.sequence == "all" else (args.sequence,)):
        print(json.dumps(prepare(selected, args.dataset.resolve())))
