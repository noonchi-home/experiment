"""Prepare text-only bundles for the text version of the nightly steps (글 버전 밤 단계 입력 만들기).

Roles: "moments" turns record lines into a moment list, "reflector_text" turns a
moment list into the candidate FSM (paper reflector, text input), and "marking"
finds when the asked candidates and actions happened. "matching" is for scoring only
(평가자 쪽): it tells which listed event each candidate refers to. "predictor_text" is the
paper predictor (FSM memory) reading the latest record lines instead of camera frames,
used to score a night's FSM on the next day's record. Prompts are read from
prompts/text/<id>.txt and each bundle records the prompt's sha256. The paper
prompts and image bundles in messages.py are not used or changed here. No model
is called.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .contracts import ContractError, validate_candidate_memory, validate_memory, validate_moments, validate_tasks
from .messages import PROJECT_ROOT, _render
from .trigger_check import FOLLOW_SECONDS

MODEL_NAME = "Qwen3.5-27B"
GENERATION = {
    # The reflector and the predictor keep the paper settings; the helper steps should be as steady as possible.
    "moments": {"temperature": 0.0, "enable_thinking": False},
    "reflector_text": {"temperature": 0.3, "enable_thinking": True},
    "marking": {"temperature": 0.0, "enable_thinking": False},
    "matching": {"temperature": 0.0, "enable_thinking": False},
    "predictor_text": {"temperature": 0.3, "enable_thinking": False},
}
PROMPT_IDS = frozenset({"moments", "reflector_text_build", "reflector_text_update", "marking", "matching",
                        "predictor_text"})
PREDICTOR_LINES = 5   # the paper's five frames two seconds apart = five record lines (8 seconds)
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


def _bundle(role: str, prompt_id: str, user_text: str, project_dir: Path, *, values: dict | None = None,
            **extra) -> dict:
    template, source = load_text_prompt(prompt_id, project_dir)
    if values is not None:
        template = _render(template, values)
    return {"role": role, "model": MODEL_NAME, "prompt_source": source,
            "generation": dict(GENERATION[role]),
            "messages": [{"role": "system", "content": template},
                         {"role": "user", "content": [{"type": "text", "text": user_text}]}],
            "status": "prepared", "execution_mode": "offline_preparation", **extra}


def _moment_block(moments: list[dict]) -> str:
    """`HH:MM:SS | text`, with "(start)" or "(end)" for the two ends of an ongoing activity."""
    validate_moments({"moments": moments})
    return "\n".join(f"{moment['time']} | {moment['text']}"
                     + ("" if moment["kind"] == "moment" else f" ({moment['kind']})") for moment in moments)


def build_moments_bundle(lines: list[str], *, previous: list[str] | None = None,
                         project_dir: Path = PROJECT_ROOT) -> dict:
    """One part of a day's record (`HH:MM:SS | sentence` lines) -> a moment list.

    Each part starts and ends its own activities. `previous` is the text of the activities
    the previous part ended at its last line, so that one going on is written with the same
    text and can be joined; their times are not given, so none can be copied.
    """
    if not lines or any(not isinstance(line, str) or "\n" in line or not RECORD_LINE.match(line) for line in lines):
        raise ContractError("A moment-list request needs record lines (HH:MM:SS | sentence).")
    if previous is not None and any(not isinstance(text, str) or not text.strip() or "\n" in text
                                    for text in previous):
        raise ContractError("Activities of the previous part must be one-line texts.")
    sections = []
    if previous:
        sections.append("Activities going on at the last line of the previous part (if one goes on, use exactly "
                        "its text):\n" + "\n".join(previous))
    sections.append("Record lines in time order (HH:MM:SS | sentence):\n" + "\n".join(lines))
    return _bundle("moments", "moments", "\n\n".join(sections), project_dir, line_count=len(lines),
                   first_time=lines[0][:8], last_time=lines[-1][:8])


def build_reflector_text_bundle(moments: list[dict], tasks: list[str], *, operation: str,
                                memory: dict | None = None, results: list[dict] | None = None,
                                feedback: str | None = None, project_dir: Path = PROJECT_ROOT) -> dict:
    """The paper reflector with text input: build on the first night, update afterwards."""
    # The window comes from the check itself, so the prompt never disagrees with the count.
    window = (f"{FOLLOW_SECONDS // 60} minutes" if FOLLOW_SECONDS % 60 == 0 else f"{FOLLOW_SECONDS} seconds")
    sections = ["Available robot tasks:\n" + "\n".join(f"{index}: {task}"
                                                       for index, task in enumerate(validate_tasks(tasks))),
                f"Check window: an action counts as following a candidate when it comes within {window} "
                "after the candidate.",
                "Today's moment list (HH:MM:SS | moment):\n" + _moment_block(moments)]
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


def build_marking_bundle(moments: list[dict], *, candidates: list[dict], actions: list[str],
                         states: dict[str, str], project_dir: Path = PROJECT_ROOT) -> dict:
    """Ask for the times of each (state, candidate), each action, and unseen intervals.

    Either list may be empty (a past day may only need a new candidate), but not both.
    """
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
                "Moment list (HH:MM:SS | moment):\n" + _moment_block(moments)]
    return _bundle("marking", "marking", "\n\n".join(sections), project_dir,
                   asked_candidates=asked, asked_actions=list(actions))


def build_matching_bundle(candidates: list[str], events: dict[str, list[str]], *,
                          project_dir: Path = PROJECT_ROOT) -> dict:
    """Scoring only: which listed event each candidate statement refers to, or none."""
    if (not candidates or any(not isinstance(text, str) or not text.strip() or "\n" in text for text in candidates)
            or len(set(candidates)) != len(candidates)):
        raise ContractError("A matching request needs different one-line candidates.")
    if not events or any(not isinstance(sentences, list) or not sentences
                         or any(not isinstance(text, str) or not text.strip() for text in sentences)
                         for sentences in events.values()):
        raise ContractError("Each event needs the sentences used for it in the record.")
    sections = ["Events (id: sentences used for it in the record):\n"
                + "\n".join(f"{name}: {' | '.join(sentences)}" for name, sentences in events.items()),
                "Candidates (number. statement):\n"
                + "\n".join(f"{number}. {text}" for number, text in enumerate(candidates, start=1))]
    return _bundle("matching", "matching", "\n\n".join(sections), project_dir,
                   asked_candidates=list(candidates), event_ids=list(events))


def build_predictor_text_bundle(lines: list[str], memory: dict, tasks: list[str], *,
                                project_dir: Path = PROJECT_ROOT) -> dict:
    """The paper predictor with the latest record lines (`HH:MM:SS | sentence`) instead of frames.

    The last line is the current moment. Fewer lines are allowed only at the start of a day,
    before the window has filled. `memory` is the predictor FSM (passing candidates only).
    """
    tasks = validate_tasks(tasks)
    validate_memory(memory, "fsm")
    if (not 1 <= len(lines) <= PREDICTOR_LINES
            or any(not isinstance(line, str) or "\n" in line or not RECORD_LINE.match(line) for line in lines)):
        raise ContractError(f"Expected 1 to {PREDICTOR_LINES} record lines (HH:MM:SS | sentence).")
    now = lines[-1][:8]
    values = {"window": str(PREDICTOR_LINES), "n_tasks_minus_one": str(len(tasks) - 1),
              "tasks_block": "\n".join(f"{index}: {task}" for index, task in enumerate(tasks)),
              "fsm_block": json.dumps(memory, ensure_ascii=False, indent=2)}
    text = (f"Wall-clock time of the last line: {now}\n\n"
            "Record lines, oldest first (HH:MM:SS | sentence):\n" + "\n".join(lines))
    return _bundle("predictor_text", "predictor_text", text, project_dir, values=values,
                   tasks=list(tasks), time=now, line_count=len(lines))
