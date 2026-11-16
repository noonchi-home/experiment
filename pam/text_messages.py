"""Prepare text-only bundles for the text version of the nightly steps (글 버전 밤 단계 입력 만들기).

Roles: "reflector_text" reads a day's record (`HH:MM:SS | sentence` lines) and makes
the candidate FSM (paper reflector, text input), and "marking" reads a day's record and
finds when the asked candidates and actions happened. Prompts are read from
prompts/text/<id>.txt and each bundle records the prompt's sha256. The paper
prompts and image bundles in messages.py are not used or changed here. No model
is called.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .contracts import ContractError, validate_candidate_memory, validate_tasks
from .messages import PROJECT_ROOT
from .trigger_check import FOLLOW_SECONDS

MODEL_NAME = "Qwen3.5-27B"
GENERATION = {
    # The reflector keeps the paper settings; marking should be as steady as possible.
    "reflector_text": {"temperature": 0.3, "enable_thinking": True},
    "marking": {"temperature": 0.0, "enable_thinking": False},
}
PROMPT_IDS = frozenset({"reflector_text_build", "reflector_text_update", "marking"})
RECORD_LINE = re.compile(r"\d\d:\d\d:\d\d \| \S")


def load_text_prompt(prompt_id: str, project_dir: Path = PROJECT_ROOT) -> tuple[str, dict]:
    if prompt_id not in PROMPT_IDS:
        raise ContractError(f"Unknown text prompt: {prompt_id}")
    relative = f"prompts/text/{prompt_id}.txt"
    try:
        raw = (Path(project_dir) / relative).read_bytes()
    except OSError as exc:
        raise ContractError(f"Cannot read text prompt {relative}") from exc
    text = raw.decode("utf-8")
    if not text.strip():
        raise ContractError(f"Text prompt {relative} is empty")
    return text, {"id": prompt_id, "file": relative, "sha256": hashlib.sha256(raw).hexdigest()}


def _bundle(role: str, prompt_id: str, user_text: str, project_dir: Path, **extra) -> dict:
    template, source = load_text_prompt(prompt_id, project_dir)
    return {"role": role, "model": MODEL_NAME, "prompt_source": source,
            "generation": dict(GENERATION[role]),
            "messages": [{"role": "system", "content": template},
                         {"role": "user", "content": [{"type": "text", "text": user_text}]}],
            "status": "prepared", "execution_mode": "offline_preparation", **extra}


def _record_block(lines: list[str]) -> str:
    """The record lines as they are; each must be `HH:MM:SS | sentence` on one line."""
    if not lines or any(not isinstance(line, str) or "\n" in line or not RECORD_LINE.match(line) for line in lines):
        raise ContractError("Expected record lines (HH:MM:SS | sentence).")
    return "\n".join(lines)


def _line_seconds(lines: list[str]) -> int:
    clock = lambda line: int(line[:2]) * 3600 + int(line[3:5]) * 60 + int(line[6:8])   # noqa: E731
    return clock(lines[1]) - clock(lines[0]) if len(lines) > 1 else 2


def build_reflector_text_bundle(lines: list[str], tasks: list[str], *, operation: str,
                                memory: dict | None = None, results: list[dict] | None = None,
                                feedback: str | None = None, project_dir: Path = PROJECT_ROOT) -> dict:
    """The paper reflector with text input: it reads the day's record itself. Build on the
    first night, update afterwards."""
    # The window comes from the check itself, so the prompt never disagrees with the count.
    window = (f"{FOLLOW_SECONDS // 60} minutes" if FOLLOW_SECONDS % 60 == 0 else f"{FOLLOW_SECONDS} seconds")
    sections = ["Available robot tasks:\n" + "\n".join(f"{index}: {task}"
                                                       for index, task in enumerate(validate_tasks(tasks))),
                f"Check window: an action counts as following a candidate when it comes within {window} "
                "after the candidate.",
                "Today's record (HH:MM:SS | sentence):\n" + _record_block(lines)]
    if operation == "build":
        if any(value is not None for value in (memory, results, feedback)):
            raise ContractError("The first night receives no prior memory, check results, or feedback.")
    elif operation == "update":
        if memory is None or results is None:
            raise ContractError("A later night needs the current memory and yesterday's check results.")
        validate_candidate_memory(memory)
        sections += ["Current memory:\n" + json.dumps(memory, ensure_ascii=False, indent=2),
                     "Yesterday's check results:\n" + json.dumps(results, ensure_ascii=False, indent=2)]
        if feedback is not None:
            if not isinstance(feedback, str) or not feedback.strip():
                raise ContractError("Feedback must be nonempty text when supplied.")
            sections.append("Human feedback:\n" + feedback)
    else:
        raise ContractError("operation must be build or update")
    return _bundle("reflector_text", f"reflector_text_{operation}", "\n\n".join(sections), project_dir,
                   operation=operation)


def build_marking_bundle(lines: list[str], *, candidates: list[dict], actions: list[str],
                         states: dict[str, str], project_dir: Path = PROJECT_ROOT) -> dict:
    """Ask for the times of each (state, candidate), each action, and unseen intervals in
    one day's record. The answer's times are checked against the record's lines.

    Either list may be empty (a past day may only need a new candidate), but not both.
    """
    record = _record_block(lines)
    asked = []
    for candidate in candidates:
        if candidate.get("state") not in states:
            raise ContractError(f"Candidate state {candidate.get('state')!r} is not a known state.")
        if not isinstance(candidate.get("candidate"), str) or not candidate["candidate"].strip():
            raise ContractError("Each candidate needs nonempty text.")
        asked.append([candidate["state"], candidate["candidate"]])
    if actions:
        validate_tasks(actions)
    if not asked and not actions:
        raise ContractError("A marking request needs at least one candidate or action.")
    sections = ["States (id: description):\n" + "\n".join(f"{state}: {text}" for state, text in states.items()),
                "Candidates to find (state | candidate):\n" + ("\n".join(f"{s} | {c}" for s, c in asked) or "(none)"),
                "Actions to find:\n" + ("\n".join(actions) or "(none)"),
                "Record (HH:MM:SS | sentence):\n" + record]
    return _bundle("marking", "marking", "\n\n".join(sections), project_dir,
                   asked_candidates=asked, asked_actions=list(actions),
                   first_time=lines[0][:8], last_time=lines[-1][:8], line_seconds=_line_seconds(lines))
