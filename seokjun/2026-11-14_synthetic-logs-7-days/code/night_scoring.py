"""Night scoring for experiment ② (밤 채점): compare the nightly results with the answer key.

Matching step (짝 맞추기): the reflector writes trigger candidates in its own words, so
an LLM tells which answer-key event each candidate is (or none). Candidates never
change their wording, so each candidate is matched once, on the night it first
appears. Each night's new matches are saved to run_dir/scoring/matches-night-N.json
and never overwritten; a saved night is read back instead of asked again. The match
table is evaluator-side data and is never given to the nightly steps.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # ai/, for the pam package

from pam.contracts import validate_matches  # noqa: E402
from pam.text_messages import build_matching_bundle  # noqa: E402


def _read(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fresh(folder: Path) -> Path:
    attempt = 1
    while (folder / f"attempt-{attempt}").exists():
        attempt += 1
    return folder / f"attempt-{attempt}"


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
