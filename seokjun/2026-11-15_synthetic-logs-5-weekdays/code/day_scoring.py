"""Day scoring for experiment ② (낮 채점): does night N's FSM make the robot help rightly on day N+1?

1. The right answer at each moment (2026-11-15 사용자 결정: 이분법):
   - must help (label = the task): from the signal of a real habit until the person starts
     moving to do the task themselves, on days the person did it within five minutes. When
     the person leaves the camera view right after the signal (the room light case), the
     signal itself is a moment to help.
   - must not help (label -1): every other moment. Coincidences, things done once and habits
     the person did not keep that day are here too.
   Real habits are the rules of cases the answer key marks as true ("예"), with only their
   candidates expected to pass on some night. The moments asked are the answer key's moment
   list (the start, and the last line of an event longer than 4 seconds), without the time
   the person is out of view.
2. Asking (묻기): at each moment the predictor gets the latest five record lines, night N's
   predictor FSM and the task list (never the answer). One JSON line per answer goes to
   run_dir/scoring/day-D-answers.jsonl; answers already there are not asked again, so a
   stopped run continues where it stopped.
3. Scoring (채점): the paper scores of pam.routine_scoring, counted per ask instead of per
   second, and per task: times it had to help, helped, missed, and wrong helps. Saved to
   run_dir/scoring/day-D.json (an earlier copy must be identical).

Usage (from this folder; --predictor model calls the AI and costs money):
    python day_scoring.py --data ../data --run-dir ../runs/free --day 5
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # ai/, for the pam package

from pam.inference import infer_text_bundle  # noqa: E402
from pam.routine_scoring import score_round  # noqa: E402
from pam.text_messages import PREDICTOR_LINES, build_predictor_text_bundle  # noqa: E402

FOLLOW = 300       # the person must do it within five minutes of the signal
SHORT = 4          # an event of one or two lines is one moment
NO_ACT = -1
TEXT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "openrouter_text.json"


def _sec(text: str) -> int:
    hours, minutes, seconds = map(int, text.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _hms(value: int) -> str:
    return f"{value // 3600:02d}:{value // 60 % 60:02d}:{value % 60:02d}"


def _segments(key: dict, day: int) -> list[dict]:
    entry = next(entry for entry in key["days"] if entry["day"] == day)
    return [{**s, "start": _sec(s["start"]), "end": _sec(s["end"])} for s in entry["segments"]]


# 1. The right answer -----------------------------------------------------------------------
def real_habit_signals(key: dict) -> dict[str, set[str]]:
    """Rule id -> the candidate events of a real habit (those expected to pass on some night)."""
    real = {case["rule"] for case in key["cases"] if case["rule"] and case["true_habit"].startswith("예")}
    return {rule["id"]: {c["event"] for c in rule["candidates"] if c["expected_nights"]}
            for rule in key["rules"] if rule["id"] in real}


def help_windows(key: dict, segments: list[dict]) -> list[tuple[int, int, int]]:
    """(start, end, task) stretches where the robot must help; segment times are in seconds."""
    signals = real_habit_signals(key)
    task_of = {name: event["task"] for name, event in key["events"].items()}
    windows = []
    for rule in key["rules"]:
        for index, signal in enumerate(segments):
            if signal["event"] not in signals.get(rule["id"], ()) or signal["state"] != rule["state"]:
                continue
            after = segments[index + 1:]
            if after and after[0]["event"] == "unseen":
                windows.append((signal["start"], after[0]["start"], rule["task"]))
                continue
            for position, later in enumerate(after):
                if later["start"] - signal["start"] > FOLLOW:
                    break
                if task_of.get(later["event"]) == rule["task"]:
                    first = position
                    while first > 0 and after[first - 1]["role"] == "approach":
                        first -= 1
                    windows.append((signal["start"], after[first]["start"], rule["task"]))
                    break
    return windows


def day_labels(key: dict, day: int) -> list[dict]:
    """Every moment asked on this day with the labels that count as right."""
    segments = _segments(key, day)
    windows = help_windows(key, segments)
    rows = []
    for segment in segments:
        if segment["event"] == "unseen":
            continue
        moments = [segment["start"]]
        if segment["end"] - segment["start"] > SHORT:
            moments.append(segment["end"] - key["line_seconds"])
        for moment in moments:
            tasks = sorted({task for start, end, task in windows if start <= moment < end})
            rows.append({"time": _hms(moment), "labels": tasks or [NO_ACT]})
    return rows


# 2. Asking ---------------------------------------------------------------------------------
def ask_day(key: dict, day: int, lines: list[str], memory: dict, ask: Callable[[dict], dict],
            path: Path) -> list[dict]:
    """Ask at every moment of the day and add one JSON line per answer to `path`.

    `lines` is the day's record (`HH:MM:SS | sentence`). Answers already in the file are not
    asked again. Returns every saved answer.
    """
    path = Path(path)
    done = set()
    if path.exists():
        done = {json.loads(line)["time"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    position = {line[:8]: index for index, line in enumerate(lines)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        for row in day_labels(key, day):
            if row["time"] in done:
                continue
            end = position[row["time"]] + 1
            bundle = build_predictor_text_bundle(lines[max(0, end - PREDICTOR_LINES):end], memory, key["tasks"])
            out.write(json.dumps({"time": row["time"], **ask(bundle)}, ensure_ascii=False) + "\n")
            out.flush()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def answer_key_predictor(key: dict, day: int) -> Callable[[dict], dict]:
    """Check of the scoring code: answers what the answer key says is right at that moment."""
    right = {row["time"]: row["labels"][0] for row in day_labels(key, day)}

    def ask(bundle: dict) -> dict:
        return {"status": "valid", "errors": [],
                "output": {"observation": "(answer key)", "reasoning": "(answer key)",
                           "task_index": right[bundle["time"]]}}
    return ask


def model_predictor(config_path: Path) -> Callable[[dict], dict]:
    """Ask the AI (role "predictor_text"). A broken answer is saved and scored as wrong; a
    failed call stops the run so that it can continue later."""
    def ask(bundle: dict) -> dict:
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            bundle_path = work / "bundle.json"
            bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = infer_text_bundle(bundle_path, Path(config_path), work)
        if result["status"] == "api_error":
            raise RuntimeError(f"The predictor call at {bundle['time']} failed: {result['error']} "
                               f"(HTTP {result['http_status']})")
        return result
    return ask


# 3. Scoring --------------------------------------------------------------------------------
def _occurrences(windows: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """One stretch per time a habit happened: the windows of two signals of one time overlap."""
    merged: list[tuple[int, int, int]] = []
    for start, end, task in sorted(windows, key=lambda window: (window[2], window[0])):
        if merged and merged[-1][2] == task and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]), task)
        else:
            merged.append((start, end, task))
    return merged


def score_day(key: dict, day: int, answers: list[dict]) -> dict:
    rows = day_labels(key, day)
    by_time = {answer["time"]: answer for answer in answers}
    if len(by_time) != len(answers) or set(by_time) != {row["time"] for row in rows}:
        raise ValueError(f"Day {day}: the answers must cover every moment exactly once.")
    predicted = [by_time[row["time"]]["output"]["task_index"] if by_time[row["time"]]["status"] == "valid"
                 else None for row in rows]
    paper = score_round({"per_second": [row["labels"] for row in rows], "segments": []}, predicted,
                        len(key["tasks"]))
    habits: dict[int, dict] = {}

    def habit(task: int) -> dict:
        return habits.setdefault(task, {"task": task, "action": key["tasks"][task], "should_help": 0,
                                        "helped": 0, "missed": 0, "wrong_help": 0, "missed_at": [],
                                        "wrong_at": []})

    times = [_sec(row["time"]) for row in rows]
    for start, end, task in _occurrences(help_windows(key, _segments(key, day))):
        item = habit(task)
        item["should_help"] += 1
        if any(start <= moment < end and choice == task for moment, choice in zip(times, predicted)):
            item["helped"] += 1
        else:
            item["missed"] += 1
            item["missed_at"].append(_hms(start))
    for row, choice in zip(rows, predicted):
        if choice is not None and choice != NO_ACT and choice not in row["labels"]:
            item = habit(choice)
            item["wrong_help"] += 1
            item["wrong_at"].append(row["time"])
    return {"day": day, "asks": len(rows), "broken_answers": predicted.count(None), "paper": paper,
            "habits": [habits[task] for task in sorted(habits)]}


def run_day(day: int, data_dir: Path, run_dir: Path, key: dict, ask: Callable[[dict], dict]) -> dict:
    """Day D with night D-1's predictor FSM: ask, then score."""
    lines = (Path(data_dir) / f"day{day}.txt").read_text(encoding="utf-8").splitlines()
    memory = json.loads((Path(run_dir) / f"night-{day - 1}" / "predictor_fsm.json").read_text(encoding="utf-8"))
    folder = Path(run_dir) / "scoring"
    answers = ask_day(key, day, lines, memory, ask, folder / f"day-{day}-answers.jsonl")
    report = {"night_fsm": day - 1, **score_day(key, day, answers)}
    path = folder / f"day-{day}.json"
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise FileExistsError(f"{path} already exists with different content")
    path.write_text(text, encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="낮 채점: 밤 FSM으로 다음 날 기록을 따라가며 낮 AI에게 묻고 채점한다. "
                                                 "--predictor model만 AI를 부른다(돈이 든다).")
    parser.add_argument("--data", type=Path, required=True, help="dayN.txt 와 answer_key.json 이 있는 폴더")
    parser.add_argument("--run-dir", type=Path, required=True, help="밤 결과 폴더 (night-1, night-2 ...)")
    parser.add_argument("--day", type=int, required=True, help="2일째부터 이 날까지 채점한다 (N일째는 N-1일째 밤 FSM으로)")
    parser.add_argument("--predictor", choices=("answer-key", "model"), default="answer-key",
                        help="answer-key: 정답을 그대로 답하는 가짜(채점 코드 확인용), model: 실제 AI(실험 ②)")
    parser.add_argument("--config", type=Path, default=TEXT_CONFIG)
    args = parser.parse_args(argv)
    key = json.loads((args.data / "answer_key.json").read_text(encoding="utf-8"))
    for day in range(2, args.day + 1):
        ask = answer_key_predictor(key, day) if args.predictor == "answer-key" else model_predictor(args.config)
        report = run_day(day, args.data, args.run_dir, key, ask)
        paper = report["paper"]
        print(f"{day}일째 ({day - 1}일째 밤 FSM): 물어본 횟수 {report['asks']}, 답이 깨진 횟수 {report['broken_answers']}, "
              f"맞힌 비율 {paper['accuracy']:.3f}, 할 일 평균 F1 {paper['task_macro']['f1']:.3f}, "
              f"안 도움 F1 {paper['no_act']['f1']:.3f}")
        for item in report["habits"]:
            print(f"  {item['action']}: 도와야 함 {item['should_help']}, 맞게 도움 {item['helped']}, "
                  f"놓침 {item['missed']} {item['missed_at']}, 괜히 도움 {item['wrong_help']} {item['wrong_at']}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
