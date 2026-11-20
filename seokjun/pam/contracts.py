"""Validate the paper's data contracts without making assistance decisions.

The list and FSM memory schemas follow Appendix F. Prediction responses follow
Appendix E. Observation records are the local input manifest, not a paper output.
"""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any


class ContractError(ValueError):
    """An input or model response does not satisfy the declared contract."""


def _object(value: Any, fields: set[str], path: str) -> dict:
    if not isinstance(value, dict):
        raise ContractError(f"{path}: expected an object")
    actual = set(value)
    if actual != fields:
        missing = sorted(fields - actual)
        extra = sorted(repr(key) for key in actual - fields)
        raise ContractError(f"{path}: incorrect fields (missing={missing}, extra={extra})")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path}: expected a nonempty string")
    return value


def _array(value: Any, path: str) -> list:
    if not isinstance(value, list):
        raise ContractError(f"{path}: expected an array")
    return value


def validate_tasks(value: Any) -> list[str]:
    """Validate a nonempty, ordered list of available actions."""
    tasks = _array(value, "tasks")
    if not tasks:
        raise ContractError("tasks: at least one available action is required")
    for index, task in enumerate(tasks):
        _text(task, f"tasks[{index}]")
    return tasks


def _rules(value: Any, path: str) -> None:
    for index, rule in enumerate(_array(value, path)):
        rule_path = f"{path}[{index}]"
        _object(rule, {"trigger", "action"}, rule_path)
        _text(rule["trigger"], f"{rule_path}.trigger")
        _text(rule["action"], f"{rule_path}.action")


def validate_memory(value: Any, kind: str) -> dict:
    """Validate list or FSM memory; never execute rules or advance a state."""
    if kind == "list":
        memory = _object(value, {"rules"}, "memory")
        _rules(memory["rules"], "memory.rules")
        return memory
    if kind != "fsm":
        raise ContractError("memory kind: expected 'list' or 'fsm'")

    memory = _object(value, {"initial_state", "states"}, "memory")
    initial_state = _text(memory["initial_state"], "memory.initial_state")
    states = _array(memory["states"], "memory.states")
    if not states:
        raise ContractError("memory.states: at least one state is required")

    identifiers: set[str] = set()
    destinations: list[tuple[str, str]] = []
    for index, state in enumerate(states):
        path = f"memory.states[{index}]"
        _object(state, {"id", "description", "rules", "next"}, path)
        identifier = _text(state["id"], f"{path}.id")
        if identifier in identifiers:
            raise ContractError(f"{path}.id: duplicate state identifier {identifier!r}")
        identifiers.add(identifier)
        _text(state["description"], f"{path}.description")
        _rules(state["rules"], f"{path}.rules")
        for next_index, transition in enumerate(_array(state["next"], f"{path}.next")):
            next_path = f"{path}.next[{next_index}]"
            _object(transition, {"to", "on"}, next_path)
            destination = _text(transition["to"], f"{next_path}.to")
            _text(transition["on"], f"{next_path}.on")
            destinations.append((f"{next_path}.to", destination))

    if initial_state not in identifiers:
        raise ContractError("memory.initial_state: must name an existing state")
    for path, destination in destinations:
        if destination not in identifiers:
            raise ContractError(f"{path}: unknown state identifier {destination!r}")
    return memory


def validate_prediction(value: Any, tasks: list[str]) -> dict:
    """Validate structure and action bounds, not semantic correctness."""
    validate_tasks(tasks)
    prediction = _object(value, {"observation", "reasoning", "task_index"}, "prediction")
    _text(prediction["observation"], "prediction.observation")
    _text(prediction["reasoning"], "prediction.reasoning")
    index = prediction["task_index"]
    # bool is a subclass of int in Python, but is not a paper action index.
    if type(index) is not int or not -1 <= index < len(tasks):
        raise ContractError(f"prediction.task_index: expected an integer from -1 to {len(tasks) - 1}")
    return prediction


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"response JSON: duplicate key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractError(f"response JSON: nonstandard numeric constant {value!r}")


def parse_prediction(raw: str, tasks: list[str]) -> dict:
    """Preserve the original response and keep invalid output distinct from wait.

    Only a complete JSON object is accepted. Markdown fences, surrounding prose,
    duplicate keys, and nonstandard numeric constants are not silently repaired.
    """
    result = {
        "status": "invalid",
        "raw_response": raw,
        "prediction": None,
        "selected_action": None,
        "errors": [],
    }
    try:
        if not isinstance(raw, str):
            raise ContractError("response: expected a JSON string")
        value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        prediction = validate_prediction(value, tasks)
    except (ContractError, json.JSONDecodeError) as error:
        result["errors"].append(str(error))
        return result

    result["status"] = "valid"
    result["prediction"] = prediction
    index = prediction["task_index"]
    result["selected_action"] = None if index == -1 else tasks[index]
    return result


def validate_observation_records(value: Any) -> list[dict]:
    """Validate ordered paired-camera records, without reading image files.

    Accept either an array or the manifest object {"observations": [...]}. Extra
    fields are rejected so evaluation labels cannot enter the model input here.
    Timestamps must be timezone-aware ISO strings and strictly increasing in
    absolute time. The supplied ordering and strings are preserved.
    """
    if isinstance(value, dict):
        value = _object(value, {"observations"}, "manifest")["observations"]
    records = _array(value, "observations")
    if not records:
        raise ContractError("observations: at least one paired-camera record is required")
    previous: datetime | None = None
    for index, record in enumerate(records):
        path = f"observations[{index}]"
        _object(record, {"timestamp", "left_image", "right_image"}, path)
        timestamp = _text(record["timestamp"], f"{path}.timestamp")
        _text(record["left_image"], f"{path}.left_image")
        _text(record["right_image"], f"{path}.right_image")
        try:
            current = datetime.fromisoformat(timestamp)
        except ValueError as error:
            raise ContractError(f"{path}.timestamp: expected an ISO datetime") from error
        if current.tzinfo is None or current.utcoffset() is None:
            raise ContractError(f"{path}.timestamp: timezone information is required")
        if previous is not None and current <= previous:
            raise ContractError(f"{path}.timestamp: timestamps must be unique and increasing")
        previous = current
    return records


# Text version of the nightly steps (설계문서/2026-11-14_PAM_80퍼센트_p-value_구현계획서.md).

_CLOCK = re.compile(r"^([01]\d|2[0-3]):([0-5]\d):([0-5]\d)$")


def _clock(value: Any, path: str) -> int:
    """Seconds since midnight for an "HH:MM:SS" string."""
    match = _CLOCK.match(value) if isinstance(value, str) else None
    if match is None:
        raise ContractError(f"{path}: expected a time as HH:MM:SS")
    return int(match[1]) * 3600 + int(match[2]) * 60 + int(match[3])


def validate_candidate_memory(value: Any) -> dict:
    """Reflector-side FSM: the paper FSM, except each rule lists 1-3 trigger candidates."""
    memory = _object(value, {"initial_state", "states"}, "memory")
    initial_state = _text(memory["initial_state"], "memory.initial_state")
    states = _array(memory["states"], "memory.states")
    if not states:
        raise ContractError("memory.states: at least one state is required")
    identifiers: set[str] = set()
    destinations: list[tuple[str, str]] = []
    for index, state in enumerate(states):
        path = f"memory.states[{index}]"
        _object(state, {"id", "description", "rules", "next"}, path)
        identifier = _text(state["id"], f"{path}.id")
        if identifier in identifiers:
            raise ContractError(f"{path}.id: duplicate state identifier {identifier!r}")
        identifiers.add(identifier)
        _text(state["description"], f"{path}.description")
        for rule_index, rule in enumerate(_array(state["rules"], f"{path}.rules")):
            rule_path = f"{path}.rules[{rule_index}]"
            _object(rule, {"triggers", "action"}, rule_path)
            triggers = _array(rule["triggers"], f"{rule_path}.triggers")
            if not 1 <= len(triggers) <= 3:
                raise ContractError(f"{rule_path}.triggers: expected 1 to 3 candidates")
            for trigger_index, trigger in enumerate(triggers):
                _text(trigger, f"{rule_path}.triggers[{trigger_index}]")
            if len(set(triggers)) != len(triggers):
                raise ContractError(f"{rule_path}.triggers: candidates must differ")
            _text(rule["action"], f"{rule_path}.action")
        for next_index, transition in enumerate(_array(state["next"], f"{path}.next")):
            next_path = f"{path}.next[{next_index}]"
            _object(transition, {"to", "on"}, next_path)
            destinations.append((f"{next_path}.to", _text(transition["to"], f"{next_path}.to")))
            _text(transition["on"], f"{next_path}.on")
    if initial_state not in identifiers:
        raise ContractError("memory.initial_state: must name an existing state")
    for path, destination in destinations:
        if destination not in identifiers:
            raise ContractError(f"{path}: unknown state identifier {destination!r}")
    return memory


def validate_chunks(value: Any, within: tuple[str, str, int] | None = None) -> dict:
    """Chunks of what the person does, in time order and not overlapping.

    With `within` (first line, last line, seconds between lines) every start and end must be
    the time of a line of the record that was read.
    """
    chunks = _object(value, {"chunks"}, "chunks")
    items = _array(chunks["chunks"], "chunks.chunks")
    if not items:
        raise ContractError("chunks.chunks: at least one chunk is required")
    previous_end = None
    for index, item in enumerate(items):
        path = f"chunks.chunks[{index}]"
        _object(item, {"start", "end", "text"}, path)
        times = []
        for name in ("start", "end"):
            moment = _clock(item[name], f"{path}.{name}")
            if within is not None:
                first, last, step = _clock(within[0], "within"), _clock(within[1], "within"), within[2]
                if not first <= moment <= last or (moment - first) % step:
                    raise ContractError(f"{path}.{name}: {item[name]} is not the time of a line of the record")
            times.append(moment)
        if times[1] < times[0]:
            raise ContractError(f"{path}: end must not come before start")
        if previous_end is not None and times[0] <= previous_end:
            raise ContractError(f"{path}: chunks must follow in time order without overlapping")
        _text(item["text"], f"{path}.text")
        previous_end = times[1]
    return chunks


def validate_marks(value: Any, candidates: list[tuple[str, str]], actions: list[str],
                   within: tuple[str, str, int] | None = None) -> dict:
    """Times of every asked (state, candidate) and action exactly once, plus unseen intervals.

    `within` is (first line, last line, seconds between lines) of the record that was read;
    every time must then be the time of one of its lines.
    """
    marks = _object(value, {"candidates", "actions", "unseen"}, "marks")

    def line_time(text: Any, path: str) -> int:
        moment = _clock(text, path)
        if within is not None:
            first, last, step = _clock(within[0], "within"), _clock(within[1], "within"), within[2]
            if not first <= moment <= last or (moment - first) % step:
                raise ContractError(f"{path}: {text} is not the time of a line of the record")
        return moment

    answered = []
    for index, item in enumerate(_array(marks["candidates"], "marks.candidates")):
        path = f"marks.candidates[{index}]"
        _object(item, {"state", "candidate", "times"}, path)
        answered.append((_text(item["state"], f"{path}.state"), _text(item["candidate"], f"{path}.candidate")))
        for time_index, moment in enumerate(_array(item["times"], f"{path}.times")):
            line_time(moment, f"{path}.times[{time_index}]")
    if sorted(answered) != sorted(tuple(pair) for pair in candidates):
        raise ContractError("marks.candidates: answer every asked candidate exactly once")
    found = []
    for index, item in enumerate(_array(marks["actions"], "marks.actions")):
        path = f"marks.actions[{index}]"
        _object(item, {"action", "times"}, path)
        found.append(_text(item["action"], f"{path}.action"))
        for time_index, moment in enumerate(_array(item["times"], f"{path}.times")):
            line_time(moment, f"{path}.times[{time_index}]")
    if sorted(found) != sorted(actions):
        raise ContractError("marks.actions: answer every asked action exactly once")
    for index, interval in enumerate(_array(marks["unseen"], "marks.unseen")):
        path = f"marks.unseen[{index}]"
        _object(interval, {"start", "end"}, path)
        if line_time(interval["end"], f"{path}.end") < line_time(interval["start"], f"{path}.start"):
            raise ContractError(f"{path}: end must not come before start")
    return marks
