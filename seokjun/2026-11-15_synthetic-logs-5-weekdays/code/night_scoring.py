"""Night scoring for experiment ② (밤 채점): compare the nightly results with the answer key.

1. Matching (짝 맞추기): the reflector writes trigger candidates in its own words, so an
   LLM tells which answer-key event each candidate is (or none). Candidates never change
   their wording, so each candidate is matched once, on the night it first appears. Each
   night's new matches are saved to run_dir/scoring/matches-night-N.json and never
   overwritten; a saved night is read back instead of asked again.
2. Comparison (예상과 같음/다름): the state of a candidate is not taken from the name the
   AI gave it but from the answer key at the times the marking step found it. Each
   checked candidate is then compared with the night the plan expects it to pass, and the
   found times are checked against the answer key.
3. Changes (자기반성이 바꾼 것): what the reflector changed from the night before.

The match table and the report are evaluator-side data and are never given to the
nightly steps.

Usage (from this folder; --matcher model calls the AI and costs money):
    python night_scoring.py --data ../data --run-dir ../runs/free --night 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # ai/, for the pam package

from pam.contracts import validate_matches  # noqa: E402
from pam.inference import infer_text_bundle  # noqa: E402
from pam.text_messages import build_matching_bundle  # noqa: E402

TOLERANCE = 10   # seconds of slack around an answer-key event when checking a found time
TEXT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "openrouter_text.json"


def _read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sec(text: str) -> int:
    hours, minutes, seconds = map(int, text.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _fresh(folder: Path) -> Path:
    attempt = 1
    while (folder / f"attempt-{attempt}").exists():
        attempt += 1
    return folder / f"attempt-{attempt}"


# 1. Matching -----------------------------------------------------------------------------
def event_sentences(key: dict) -> dict[str, list[str]]:
    """Every answer-key event with the sentences used for it in the record."""
    return {name: list(event["phrases"]) for name, event in key["events"].items()}


def night_candidates(memory: dict) -> list[str]:
    """Each candidate text of a reflector FSM once, in the order it first appears."""
    found = []
    for state in memory["states"]:
        for rule in state["rules"]:
            for candidate in rule["triggers"]:
                if candidate not in found:
                    found.append(candidate)
    return found


def match_table(night: int, run_dir: Path, key: dict,
                call: Callable[[dict, Path], dict]) -> dict[str, str | None]:
    """Candidate text -> answer-key event (None if no event is the same moment), nights 1..night.

    `call(bundle, work)` asks the LLM and returns its answer; only candidates not matched
    on an earlier night are asked.
    """
    run_dir = Path(run_dir)
    events = event_sentences(key)
    table: dict[str, str | None] = {}
    for current in range(1, night + 1):
        path = run_dir / "scoring" / f"matches-night-{current}.json"
        if not path.exists():
            memory = _read(run_dir / f"night-{current}" / "reflector_fsm.json")
            new = [text for text in night_candidates(memory) if text not in table]
            matches = []
            if new:
                answer = call(build_matching_bundle(new, events),
                              _fresh(run_dir / "scoring" / "work" / f"night-{current}"))
                validate_matches(answer, len(new), list(events))
                matches = [{"candidate": new[item["index"] - 1], "event": item["event"]}
                           for item in sorted(answer["matches"], key=lambda item: item["index"])]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"night": current, "matches": matches}, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        for item in _read(path)["matches"]:
            table[item["candidate"]] = item["event"]
    return table


def answer_key_matcher(key: dict) -> Callable[[dict, Path], dict]:
    """For runs whose candidates are answer-key event names (experiment ①): each name is its own match."""
    def call(bundle: dict, work: Path) -> dict:
        return {"matches": [{"index": number, "event": text if text in key["events"] else None}
                            for number, text in enumerate(bundle["asked_candidates"], start=1)]}
    return call


def model_matcher(config_path: Path) -> Callable[[dict, Path], dict]:
    """Ask the LLM (role "matching"); the bundle, the request and the answer are kept in `work`."""
    def call(bundle: dict, work: Path) -> dict:
        work.mkdir(parents=True, exist_ok=False)
        bundle_path = work / "bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = infer_text_bundle(bundle_path, Path(config_path), work)
        if result.get("status") != "valid":
            raise RuntimeError(f"The matching step did not return a valid answer; see {work}")
        return result["output"]
    return call


# 2. Comparison ---------------------------------------------------------------------------
def _days(key: dict) -> dict[int, list[dict]]:
    return {entry["day"]: [{**s, "start": _sec(s["start"]), "end": _sec(s["end"])} for s in entry["segments"]]
            for entry in key["days"]}


def _state_at(segments: list[dict], moment: int) -> str | None:
    return next((s["state"] for s in segments if s["start"] <= moment < s["end"]), None)


def _found_marks(run_dir: Path, night: int) -> dict[int, dict[tuple[str, str], list[int]]]:
    """Candidate times the marking step found, by day, as saved in night-1 .. night-N (first answer kept)."""
    found: dict[int, dict[tuple[str, str], list[int]]] = {}
    for done in range(1, night + 1):
        for path in sorted((run_dir / f"night-{done}" / "marks").glob("day*.json")):
            saved = _read(path)
            day = found.setdefault(saved["day"], {})
            for item in saved["candidates"]:
                day.setdefault((item["state"], item["candidate"]), [_sec(t) for t in item["times"]])
    return found


def _time_check(found: list[int], true: list[dict]) -> dict[str, int]:
    """A found time is right when it lies on, or within TOLERANCE seconds of, a true event not yet claimed."""
    left, right = list(true), 0
    for moment in sorted(found):
        hit = next((s for s in left if s["start"] - TOLERANCE <= moment <= s["end"] + TOLERANCE), None)
        if hit is not None:
            left.remove(hit)
            right += 1
    return {"right": right, "missed": len(true) - right, "wrong": len(found) - right}


def _expectation(key: dict, state: str, task: int | None, event: str, night: int) -> tuple[str, bool | None]:
    for rule in key["rules"]:
        if rule["state"] == state and rule["task"] == task:
            for candidate in rule["candidates"]:
                if candidate["event"] == event:
                    return "심어 둔 후보", night in candidate["expected_nights"]
    if any(rule["task"] == task and event in rule["forbidden"] for rule in key["rules"]):
        return "행동의 일부", False
    if any(rule["task"] == task and any(c["event"] == event for c in rule["candidates"]) for rule in key["rules"]):
        return "다른 상태", False
    return "심지 않음", None


def compare_night(night: int, run_dir: Path, key: dict, matches: dict[str, str | None]) -> list[dict]:
    """Each checked candidate next to what the answer key expects on this night, plus planted
    candidates the reflector never proposed. Without any found time, a planted candidate takes
    the state it was planted in, and is marked as not happened yet or as missed by the marking step."""
    run_dir = Path(run_dir)
    found = _found_marks(run_dir, night)
    days = _days(key)
    planted = {(rule["state"], rule["task"], c["event"]) for rule in key["rules"] for c in rule["candidates"]}
    rows, proposed = [], set()
    for result in _read(run_dir / f"night-{night}" / "check_results.json"):
        event = matches.get(result["candidate"])
        task = key["tasks"].index(result["action"]) if result["action"] in key["tasks"] else None
        times = {day: found.get(day, {}).get((result["state"], result["candidate"]), []) for day in range(1, night + 1)}
        states = sorted({_state_at(days[day], moment) for day, moments in times.items() for moment in moments} - {None})
        if not states:
            states = sorted({s for s, t, e in planted if t == task and e == event})[:2]
            states = states if len(states) == 1 else []
            unfound = True
        else:
            unfound = False
        row = {"state": result["state"], "candidate": result["candidate"], "action": result["action"],
               "event": event, "answer_state": states[0] if len(states) == 1 else (states or None),
               "n": result["n"], "k": result["k"], "passed": result["passed"], "expected": None, "times": None}
        if event is None:
            row["kind"] = "짝 없음"
        elif not states:
            row["kind"] = "시각 못 찾음"
        elif len(states) > 1:
            row["kind"] = "상태 섞임"
        else:
            row["kind"], row["expected"] = _expectation(key, states[0], task, event, night)
            true = {day: [s for s in days[day] if s["event"] == event and s["state"] == states[0]] for day in times}
            checks = [_time_check(times[day], true[day]) for day in times]
            row["times"] = {name: sum(check[name] for check in checks) for name in ("right", "missed", "wrong")}
            if unfound:
                row["kind"] = "아직 안 일어남" if not any(true.values()) else "시각 못 찾음"
            if (states[0], task, event) in planted:
                proposed.add((states[0], task, event))
        row["verdict"] = None if row["expected"] is None else ("같음" if row["expected"] == result["passed"] else "다름")
        rows.append(row)
    for rule in key["rules"]:
        for candidate in rule["candidates"]:
            if (rule["state"], rule["task"], candidate["event"]) not in proposed:
                expected = night in candidate["expected_nights"]
                rows.append({"state": None, "candidate": None, "action": key["tasks"][rule["task"]],
                             "event": candidate["event"], "answer_state": rule["state"], "n": None, "k": None,
                             "passed": False, "expected": expected, "times": None, "kind": "후보로 안 나옴",
                             "verdict": "다름" if expected else "같음"})
    return rows


# 3. Changes ------------------------------------------------------------------------------
def _rules(memory: dict) -> dict[tuple[str, str], set[str]]:
    rules: dict[tuple[str, str], set[str]] = {}
    for state in memory["states"]:
        for rule in state["rules"]:
            rules.setdefault((state["id"], rule["action"]), set()).update(rule["triggers"])
    return rules


def changes(night: int, run_dir: Path) -> list[dict]:
    """What the reflector changed from the night before. A candidate may be replaced only after
    three or more checks with a rate under 80% (prompts/text/reflector_text_update.txt)."""
    if night == 1:
        return []
    run_dir = Path(run_dir)
    before = _read(run_dir / f"night-{night - 1}" / "reflector_fsm.json")
    after = _read(run_dir / f"night-{night}" / "reflector_fsm.json")
    checked = {(r["state"], r["action"], r["candidate"]): r
               for r in _read(run_dir / f"night-{night - 1}" / "check_results.json")}
    old_states = {s["id"]: s["description"] for s in before["states"]}
    new_states = {s["id"]: s["description"] for s in after["states"]}
    rows = [{"kind": "사라진 상태", "state": s} for s in old_states if s not in new_states]
    rows += [{"kind": "새 상태", "state": s} for s in new_states if s not in old_states]
    rows += [{"kind": "설명 바뀜", "state": s, "before": old_states[s], "after": new_states[s]}
             for s in old_states if s in new_states and old_states[s] != new_states[s]]
    old_rules, new_rules = _rules(before), _rules(after)
    rows += [{"kind": "사라진 규칙", "state": s, "action": a}
             for s, a in old_rules if (s, a) not in new_rules and s in new_states]
    for (state, action), candidates in old_rules.items():
        for candidate in sorted(candidates - new_rules.get((state, action), set())):
            result = checked.get((state, action, candidate))
            if result and result["passed"]:
                flag = "통과 중이던 후보가 사라짐"
            elif result and result["n"] >= 3 and result["rate"] < 0.8:
                flag = "규칙대로 바꿈"
            else:
                flag = "규칙 어김"
            rows.append({"kind": "사라진 후보", "state": state, "action": action, "candidate": candidate,
                         "flag": flag, "n": result["n"] if result else None, "k": result["k"] if result else None})
    for (state, action), candidates in new_rules.items():
        for candidate in sorted(candidates - old_rules.get((state, action), set())):
            rows.append({"kind": "새 후보", "state": state, "action": action, "candidate": candidate})
    return rows


# Night report ------------------------------------------------------------------------------
def score_night(night: int, run_dir: Path, key: dict, call: Callable[[dict, Path], dict]) -> dict:
    """Match new candidates, compare with the answer key and list the changes; saved to
    run_dir/scoring/night-N.json (an earlier copy must be identical)."""
    matches = match_table(night, run_dir, key, call)
    report = {"night": night, "rows": compare_night(night, run_dir, key, matches),
              "changes": changes(night, run_dir)}
    path = Path(run_dir) / "scoring" / f"night-{night}.json"
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise FileExistsError(f"{path} already exists with different content")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="밤 채점: 밤 결과를 정답표와 비교한다. --matcher model만 AI를 부른다(돈이 든다).")
    parser.add_argument("--data", type=Path, required=True, help="answer_key.json 이 있는 폴더")
    parser.add_argument("--run-dir", type=Path, required=True, help="밤 결과 폴더 (night-1, night-2 ...)")
    parser.add_argument("--night", type=int, required=True, help="1일째 밤부터 이 밤까지 채점한다")
    parser.add_argument("--matcher", choices=("answer-key", "model"), default="answer-key",
                        help="answer-key: 후보가 정답표 사건 이름일 때(실험 ①), model: AI가 짝을 맞춘다(실험 ②)")
    parser.add_argument("--config", type=Path, default=TEXT_CONFIG)
    args = parser.parse_args(argv)
    key = _read(args.data / "answer_key.json")
    call = answer_key_matcher(key) if args.matcher == "answer-key" else model_matcher(args.config)
    for night in range(1, args.night + 1):
        report = score_night(night, args.run_dir, key, call)
        verdicts = [row["verdict"] for row in report["rows"]]
        print(f"{night}일째 밤: 같음 {verdicts.count('같음')}, 다름 {verdicts.count('다름')}, "
              f"판단 없음 {verdicts.count(None)}, 바뀐 것 {len(report['changes'])}")
    for row in report["rows"]:
        if row["verdict"] != "같음":
            print(f"  [{row['kind']}] {row['state']} | {row['candidate']} → {row['event']} "
                  f"(정답표 상태 {row['answer_state']}, 통과 {row['passed']}, 예상 {row['expected']}, 시각 {row['times']})")
    for change in report["changes"]:
        print(f"  [{change['kind']}] {change.get('state')} | {change.get('candidate', '')} {change.get('flag', '')}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
