"""Prepare two seated cases; --execute explicitly makes at most two API calls."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pam.__main__ import main as prepare
from pam.experiment_paths import breakfast_dataset
from pam.inference import infer_bundle


def run(dataset: Path, output: Path, execute: bool) -> dict:
    dataset, output = breakfast_dataset(dataset), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    scenario = ROOT / "scenarios/breakfast/scenario.json"
    seed = scenario.parent / "initial_fsm.json"
    report = {"status": "running", "created_at": datetime.now(timezone.utc).isoformat(),
              "scenario": "scenarios/breakfast/scenario.json", "seed_origin": "manual_seed",
              "seed_sha256": hashlib.sha256(seed.read_bytes()).hexdigest(),
              "api_execution_requested": execute, "maximum_calls": 2,
              "action_executed": False, "reflection_run": False,
              "evaluation_labels_sent_to_model": False, "cases": []}
    def save():
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save()
    try:
        for case, expected in (("seated_without_milk", 0), ("seated_with_milk", -1)):
            manifest = dataset / f"{case}_observations.json"
            records = json.loads(manifest.read_text(encoding="utf-8"))["observations"]
            prepared = output / case / "prepared"
            code = prepare(["prepare-predictor", "--observations", str(manifest),
                            "--scenario", str(scenario), "--memory-kind", "fsm",
                            "--at", records[-1]["timestamp"], "--output", str(prepared)])
            if code != 0:
                raise RuntimeError(f"Preparation failed for {case}.")
            item = {"case": case, "expected_task_index": expected, "status": "prepared",
                    "prepared_bundle": f"{case}/prepared/input_bundle.json"}
            report["cases"].append(item)
            save()
            if execute:
                target = output / case / "inference"
                target.mkdir()
                result = infer_bundle(prepared / "input_bundle.json", ROOT / "config/openrouter.json", target)
                item.update(status=result["status"], result=f"{case}/inference/result.json")
                if result["status"] != "valid":
                    raise RuntimeError(f"Model response failed validation for {case}; no retry.")
                task = result["prediction"]["task_index"]
                item.update(actual_task_index=task, passed=task == expected,
                            response_id=result["response_id"], cost=(result.get("usage") or {}).get("cost"))
                save()
        report["status"] = "completed" if execute else "prepared_only"
        if execute:
            report["passed"] = sum(c["passed"] for c in report["cases"])
            report["total"] = len(report["cases"])
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error))
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/morning_3d_v1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Make up to two paid OpenRouter calls; otherwise prepare only.")
    args = parser.parse_args()
    result = run(args.dataset, args.output, args.execute)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(2 if result["status"] == "failed" else 0)
