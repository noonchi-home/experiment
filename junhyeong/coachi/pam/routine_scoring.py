"""Score a routine run against evaluator-only per-second labels, after all model calls.

Paper metrics (Section 4.1): per-class precision / recall / F1 over the tasks and
NO_ACT (-1), their macro averages, and first-fire delay: seconds from the start of
a segment until the first matching prediction, or the whole segment if none.
Our additions (decided with the user):
- A frame whose label lists two actions counts as correct if either is predicted.
- Delivery segments: first matching prediction before the person stands up to fetch
  the item = "on_time", afterwards = "late", none = "missed". The can segment cannot
  be on time, so it is only "given" or "missed".
Invalid model outputs are never counted as NO_ACT; they are wrong for every class.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .experiment_paths import routine_labels
from .messages import read_json


class ScoringError(ValueError):
    """Predictions and labels cannot be compared as declared."""


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def load_predictions(path: Path) -> list[int | None]:
    """task_index per second; None for an invalid output."""
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if [row["t"] for row in rows] != list(range(len(rows))):
        raise ScoringError(f"Predictions must cover every second from 0 in order: {path}")
    return [row["task_index"] if row["status"] == "valid" else None for row in rows]


def score_round(labels: dict, predictions: list[int | None], task_count: int) -> dict:
    per_second = labels["per_second"]
    if len(per_second) != len(predictions):
        raise ScoringError(f"Label frames ({len(per_second)}) and predictions ({len(predictions)}) differ.")
    gold = [p if p in allowed else allowed[0] for allowed, p in zip(per_second, predictions)]
    classes = [-1, *range(task_count)]
    per_class = {}
    for c in classes:
        tp = sum(p == c and g == c for p, g in zip(predictions, gold))
        fp = sum(p == c and g != c for p, g in zip(predictions, gold))
        fn = sum(g == c and p != c for p, g in zip(predictions, gold))
        precision, recall = _rate(tp, tp + fp), _rate(tp, tp + fn)
        per_class[str(c)] = {"support": tp + fn, "predicted": tp + fp, "tp": tp, "fp": fp, "fn": fn,
                             "precision": precision, "recall": recall, "f1": _f1(precision, recall)}
    tasks = [per_class[str(c)] for c in range(task_count) if per_class[str(c)]["support"]]
    macro = {key: sum(item[key] for item in tasks) / len(tasks) if tasks else 0.0
             for key in ("precision", "recall", "f1")}

    segments = []
    for segment in labels["segments"]:
        if segment["kind"] == "none":
            continue
        frames = range(segment["frame_start"], segment["frame_end"] + 1)
        first = next((t for t in frames if predictions[t] in segment["labels"]), None)
        length = len(frames)
        item = {"frame_start": segment["frame_start"], "frame_end": segment["frame_end"],
                "labels": segment["labels"], "kind": segment["kind"], "first_fire_frame": first,
                "first_fire_delay_seconds": (first - segment["frame_start"]) if first is not None else length,
                "fired": first is not None}
        if segment["scoring"] == "on_time_late_missed":
            item["outcome"] = ("missed" if first is None else
                               "on_time" if first < segment["late_from_frame"] else "late")
        elif segment["scoring"] == "given_or_missed":
            item["outcome"] = "given" if first is not None else "missed"
        segments.append(item)
    outcomes = {}
    for item in segments:
        if "outcome" in item:
            outcomes[item["outcome"]] = outcomes.get(item["outcome"], 0) + 1
    return {"frames": len(predictions), "invalid_outputs": sum(p is None for p in predictions),
            "accuracy": _rate(sum(p == g for p, g in zip(predictions, gold)), len(predictions)),
            "per_class": per_class, "task_macro": macro, "no_act": per_class["-1"],
            "distractor_predictions": {str(c): per_class[str(c)]["predicted"] for c in range(task_count)
                                       if not per_class[str(c)]["support"] and per_class[str(c)]["predicted"]},
            "mean_first_fire_delay_seconds": (sum(item["first_fire_delay_seconds"] for item in segments)
                                              / len(segments)) if segments else None,
            "delivery_outcomes": outcomes, "segments": segments}


def score_run(run_dir: Path, labels_path: Path) -> dict:
    run_dir = Path(run_dir).resolve()
    labels_path = routine_labels(Path(labels_path))
    report, labels = read_json(run_dir / "report.json"), read_json(labels_path)
    task_count = len(read_json(Path(report["settings"]["tasks_file"])))
    result = {"run": str(run_dir), "mode": report["mode"], "labels": str(Path(labels_path).resolve()),
              "rounds": {}}
    for record in report["rounds"]:
        name = record["round"]
        if name not in labels["rounds"]:
            raise ScoringError(f"No labels for round {name}.")
        predictions = load_predictions(run_dir / name / "predictions.jsonl")
        result["rounds"][name] = score_round(labels["rounds"][name], predictions, task_count)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="4일 실험 채점 (모델 호출이 끝난 뒤, 평가자 정답 사용)")
    parser.add_argument("--run", type=Path, required=True, help="routine_experiment 결과 폴더")
    parser.add_argument("--labels", type=Path, required=True, help="정답 JSON (평가자 전용)")
    parser.add_argument("--output", type=Path, help="점수 JSON을 저장할 파일 (기본: 결과 폴더/scores.json)")
    args = parser.parse_args(argv)
    scores = score_run(args.run, args.labels)
    output = args.output or Path(args.run) / "scores.json"
    output.write_text(json.dumps(scores, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, item in scores["rounds"].items():
        print(json.dumps({"round": name, "task_macro_f1": round(item["task_macro"]["f1"], 3),
                          "no_act_f1": round(item["no_act"]["f1"], 3),
                          "mean_first_fire_delay_seconds": item["mean_first_fire_delay_seconds"],
                          "delivery_outcomes": item["delivery_outcomes"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
