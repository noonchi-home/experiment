"""Answer-key steps for experiment ① (AI 없이 정답표 값으로 돌리기).

The two AI steps (the reflector and marking) are replaced by the true answers in
answer_key.json, so only the code is tested: counting, the 80%·p-value check and the
predictor FSM. If a night's pass/fail differs from the expected nights, the code is wrong,
not an AI. A candidate's or an action's time is the first line of the event; an unseen
interval runs from its first to its last line. Candidates and rules use the event names of
the answer key.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # ai/, for the pam package

from pam.daily_run import Steps  # noqa: E402


def _sec(text: str) -> int:
    hours, minutes, seconds = map(int, text.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _hms(value: int) -> str:
    return f"{value // 3600:02d}:{value // 60 % 60:02d}:{value % 60:02d}"


def true_memory(key: dict) -> dict:
    """The planted rules as a candidate FSM: every state, with the rules of the answer key."""
    rules: dict[str, list[dict]] = {}
    for rule in key["rules"]:
        rules.setdefault(rule["state"], []).append(
            {"triggers": [candidate["event"] for candidate in rule["candidates"]],
             "action": key["tasks"][rule["task"]]})
    states = list(key["states"])
    return {"initial_state": states[0], "states": [
        {"id": state, "description": key["states"][state], "rules": rules.get(state, []), "next": []}
        for state in states]}


def true_marks(segments: list[dict], candidates: list[dict], actions: list[str], key: dict, step: int) -> dict:
    found = []
    for asked in candidates:
        times = [segment["start"] for segment in segments
                 if segment["event"] == asked["candidate"] and segment["state"] == asked["state"]]
        found.append({"state": asked["state"], "candidate": asked["candidate"], "times": times})
    done = []
    for action in actions:
        task = key["tasks"].index(action)
        events = {name for name, event in key["events"].items() if event["task"] == task}
        done.append({"action": action, "times": [s["start"] for s in segments if s["event"] in events]})
    unseen = [{"start": s["start"], "end": _hms(_sec(s["end"]) - step)} for s in segments if s["event"] == "unseen"]
    return {"candidates": found, "actions": done, "unseen": unseen}


def answer_key_steps(key: dict) -> Steps:
    days = {entry["day"]: entry["segments"] for entry in key["days"]}
    step = key["line_seconds"]
    return Steps(
        reflect=lambda night, lines, memory, results, work: true_memory(key),
        mark=lambda day, lines, candidates, actions, states, work: true_marks(days[day], candidates, actions,
                                                                             key, step))


def score_night(results: list[dict], key: dict, night: int) -> list[dict]:
    """Each checked candidate next to what the plan expects on this night."""
    expected = {(rule["state"], key["tasks"][rule["task"]], candidate["event"]): night in candidate["expected_nights"]
                for rule in key["rules"] for candidate in rule["candidates"]}
    rows = []
    for result in results:
        want = expected.get((result["state"], result["action"], result["candidate"]))
        rows.append({"state": result["state"], "action": result["action"], "candidate": result["candidate"],
                     "n": result["n"], "k": result["k"], "unknown": result["unknown"], "p0": result["p0"],
                     "p_value": result["p_value"], "passed": result["passed"], "expected": want,
                     "match": want == result["passed"]})
    return rows
