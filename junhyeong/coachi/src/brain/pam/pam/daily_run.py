"""Run the text version of the nightly steps one night at a time (하루씩 돌리는 실행기).

Night N: the reflector reads day N's record itself (build on night 1, update
afterwards) -> marking reads each day's record (times of every candidate and action,
asked only for what is not known yet, on every day so far) -> the 75%·p-value check
over days 1..N -> the predictor FSM (passing candidates only). A day is short enough
to be read whole (one hour of 2-second lines, or a few minutes of 1-second lines). The
check window is 5 minutes unless --window-seconds says otherwise; it is written in each
done.json, and a run never mixes windows. Marked times must be times of
lines of that day's record. Everything is
saved under run_dir/night-N/ and never overwritten. A finished night has done.json and
is loaded instead of run again; an unfinished night reuses the step outputs it already
saved. The two AI
steps are passed in as `Steps`, so the same runner works with the model
(`model_steps`) or with an answer key.

Usage (calls the model and costs money; run one night, look, then the next):
    python -m pam.daily_run --records <folder with day1.txt ...> --run-dir <folder> --night 1
        [--tasks <tasks.json>] [--window-seconds 60]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Callable

from .contracts import ContractError, validate_candidate_memory, validate_marks
from .inference import infer_text_bundle
from .messages import PROJECT_ROOT, read_json
from .text_messages import build_marking_bundle, build_reflector_text_bundle, record_bounds
from .trigger_check import FOLLOW_SECONDS, check_candidate, predictor_fsm

_LINE = re.compile(r"^(\d\d):(\d\d):(\d\d) \| .+")


@dataclass
class Steps:
    """The two AI steps, both given a day's record lines; each also gets a fresh folder."""
    reflect: Callable[[int, list[str], dict | None, list[dict] | None, Path], dict]
    mark: Callable[[int, list[str], list[dict], list[str], dict[str, str], Path], dict]


def _seconds(text: str) -> int:
    match = _LINE.match(f"{text} | x")
    if match is None:
        raise ContractError(f"Expected a time as HH:MM:SS, got {text!r}")
    return int(match[1]) * 3600 + int(match[2]) * 60 + int(match[3])


def read_record(path: Path) -> list[str]:
    lines = [line for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines or any(_LINE.match(line) is None for line in (lines[0], lines[-1])):
        raise ContractError(f"{path}: expected record lines `HH:MM:SS | sentence`")
    return lines


def _span(lines: list[str]) -> tuple[int, int, int]:
    """Start, end (exclusive) and line step of a day's record (lines or a chunk list)."""
    first, last, step, _ = record_bounds(lines)
    return _seconds(first), _seconds(last) + step, step


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _write_new(path: Path, value) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump(value), encoding="utf-8")


def _write_or_same(path: Path, value) -> None:
    """For results computed by code: an earlier copy is fine only if it is identical."""
    if path.exists():
        if _read(path) != json.loads(_dump(value)):
            raise FileExistsError(f"{path} already exists with different content")
        return
    _write_new(path, value)


def _fresh(folder: Path) -> Path:
    attempt = 1
    while (folder / f"attempt-{attempt}").exists():
        attempt += 1
    return folder / f"attempt-{attempt}"


def _known_marks(run_dir: Path, night: int) -> dict[int, dict]:
    known: dict[int, dict] = {}
    for done in range(1, night + 1):
        for path in sorted((run_dir / f"night-{done}" / "marks").glob("day*.json")):
            saved = _read(path)
            day = known.setdefault(saved["day"], {"candidates": {}, "actions": {}, "unseen": None})
            for item in saved["candidates"]:
                day["candidates"].setdefault((item["state"], item["candidate"]), item["times"])
            for item in saved["actions"]:
                day["actions"].setdefault(item["action"], item["times"])
            if day["unseen"] is None:
                day["unseen"] = saved["unseen"]
    return known


def _run_one(night: int, records: dict[int, Path], run_dir: Path, steps: Steps, window: int) -> dict:
    folder = run_dir / f"night-{night}"
    work = folder / "work"

    lines = read_record(records[night])
    memory_path = folder / "reflector_fsm.json"
    if memory_path.exists():
        memory = _read(memory_path)
    else:
        previous = run_dir / f"night-{night - 1}"
        prior = None if night == 1 else _read(previous / "reflector_fsm.json")
        results = None if night == 1 else _read(previous / "check_results.json")
        memory = steps.reflect(night, lines, prior, results, _fresh(work / "reflect"))
        validate_candidate_memory(memory)
        _write_new(memory_path, memory)

    states = {state["id"]: state["description"] for state in memory["states"]}
    wanted = []
    for state in memory["states"]:
        for rule in state["rules"]:
            for candidate in rule["triggers"]:
                if {"state": state["id"], "candidate": candidate} not in wanted:
                    wanted.append({"state": state["id"], "candidate": candidate})
    actions = sorted({rule["action"] for state in memory["states"] for rule in state["rules"]})
    known = _known_marks(run_dir, night)
    for day in range(1, night + 1):
        have = known.setdefault(day, {"candidates": {}, "actions": {}, "unseen": None})
        ask = [item for item in wanted if (item["state"], item["candidate"]) not in have["candidates"]]
        ask_actions = [action for action in actions if action not in have["actions"]]
        if not ask and not ask_actions:
            continue
        day_lines = lines if day == night else read_record(records[day])
        marks = steps.mark(day, day_lines, ask, ask_actions, states, _fresh(work / f"mark-day{day}"))
        validate_marks(marks, [(item["state"], item["candidate"]) for item in ask], ask_actions,
                       within=record_bounds(day_lines)[:3])
        _write_new(folder / "marks" / f"day{day}.json", {"day": day, **marks})
        for item in marks["candidates"]:
            have["candidates"][(item["state"], item["candidate"])] = item["times"]
        for item in marks["actions"]:
            have["actions"][item["action"]] = item["times"]
        if have["unseen"] is None:
            have["unseen"] = marks["unseen"]

    spans = {day: _span(read_record(records[day])) for day in range(1, night + 1)}
    results = []
    for state in memory["states"]:
        for rule in state["rules"]:
            for candidate in rule["triggers"]:
                days = []
                for day in range(1, night + 1):
                    start, end, step = spans[day]
                    have = known[day]
                    days.append({
                        "start": start, "end": end,
                        "candidate": [_seconds(t) for t in have["candidates"][(state["id"], candidate)]],
                        "action": [_seconds(t) for t in have["actions"][rule["action"]]],
                        "unseen": [(_seconds(u["start"]), _seconds(u["end"]) + step) for u in have["unseen"] or []],
                    })
                results.append({"state": state["id"], "action": rule["action"], "candidate": candidate,
                                **check_candidate(days, window)})
    _write_or_same(folder / "check_results.json", results)

    passed = {(r["state"], r["action"], r["candidate"]) for r in results if r["passed"]}
    _write_or_same(folder / "predictor_fsm.json", predictor_fsm(memory, passed))
    summary = {"night": night, "window_seconds": window, "states": len(memory["states"]), "candidates": len(results),
               "passed": [{"state": s, "action": a, "candidate": c} for s, a, c in sorted(passed)]}
    _write_new(folder / "done.json", summary)
    return summary


def run_night(night: int, records: dict[int, Path], run_dir: Path, steps: Steps,
              window: int = FOLLOW_SECONDS) -> dict:
    """Make sure nights 1..night are done, running the missing ones in order; return night's summary."""
    if type(night) is not int or night < 1 or any(day not in records for day in range(1, night + 1)):
        raise ContractError("Give a night from 1 and a record for every day up to it.")
    summary = {}
    for current in range(1, night + 1):
        done = Path(run_dir) / f"night-{current}" / "done.json"
        if done.exists():
            summary = _read(done)
            if summary.get("window_seconds", FOLLOW_SECONDS) != window:
                raise ContractError(f"{done} was checked with a {summary.get('window_seconds', FOLLOW_SECONDS)}-second "
                                    f"window, not {window}; use a new run folder.")
        else:
            summary = _run_one(current, records, Path(run_dir), steps, window)
    return summary


def model_steps(tasks: list[str], config_path: Path, *, project_dir: Path = PROJECT_ROOT,
                window: int = FOLLOW_SECONDS) -> Steps:
    """The two steps done by the model; each sends a whole day's record."""
    def call(bundle: dict, work: Path) -> dict:
        work.mkdir(parents=True, exist_ok=False)
        bundle_path = work / "bundle.json"
        bundle_path.write_text(_dump(bundle), encoding="utf-8")
        result = infer_text_bundle(bundle_path, config_path, work)
        if result.get("status") != "valid":
            raise RuntimeError(f"The {bundle['role']} step did not return a valid answer; see {work}")
        return result["output"]

    def reflect(night: int, lines: list[str], memory: dict | None, results: list[dict] | None,
                work: Path) -> dict:
        bundle = build_reflector_text_bundle(lines, tasks, operation="build" if memory is None else "update",
                                             memory=memory, results=results, window_seconds=window,
                                             project_dir=project_dir)
        return call(bundle, work)

    def mark(day: int, lines: list[str], candidates: list[dict], actions: list[str],
             states: dict[str, str], work: Path) -> dict:
        bundle = build_marking_bundle(lines, candidates=candidates, actions=actions, states=states,
                                      project_dir=project_dir)
        return call(bundle, work)

    return Steps(reflect, mark)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="글 버전 밤 단계를 하루씩 돌린다. 모델을 부르므로 돈이 든다.")
    parser.add_argument("--records", type=Path, required=True, help="day1.txt, day2.txt ... 가 있는 폴더")
    parser.add_argument("--run-dir", type=Path, required=True, help="밤마다 결과를 저장할 폴더")
    parser.add_argument("--night", type=int, required=True, help="이 밤까지 돌린다 (끝난 밤은 다시 돌리지 않는다)")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "openrouter_text.json")
    parser.add_argument("--tasks", type=Path, default=PROJECT_ROOT / "scenarios" / "routine" / "tasks.json")
    parser.add_argument("--window-seconds", type=int, default=FOLLOW_SECONDS,
                        help="검사 기준 시간(초). 신호 뒤 이 시간 안에 행동이 오면 따라온 것으로 센다")
    args = parser.parse_args(argv)
    if not 1 <= args.window_seconds <= 3600:
        parser.error("--window-seconds must be between 1 and 3600")
    records = {day: args.records / f"day{day}.txt" for day in range(1, args.night + 1)}
    steps = model_steps(read_json(args.tasks), args.config, window=args.window_seconds)
    print(json.dumps(run_night(args.night, records, args.run_dir, steps, args.window_seconds),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
