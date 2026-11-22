"""Locate bundled experiment inputs after their move into experiments/."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def breakfast_dataset(path: Path) -> Path:
    path = path.resolve()
    old = ROOT / "examples/breakfast_2026-10-25"
    if path == old and not (path / "seated_without_milk_observations.json").exists():
        return ROOT / "experiments/breakfast_2026-10-25"
    return path


def routine_labels(path: Path) -> Path:
    filename = "정답/4일_정답_초안.json"
    old = ROOT / "docs/research/routine_2026-11-04" / filename
    if path.resolve() == old and not path.exists():
        return ROOT / "2026-11-04_four-day-routine-videos" / filename
    return path
