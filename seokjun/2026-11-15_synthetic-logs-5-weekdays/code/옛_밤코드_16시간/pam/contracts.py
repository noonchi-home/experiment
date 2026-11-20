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


MOMENT_KINDS = ("start", "end", "moment")


def validate_moments(value: Any, within: tuple[str, str] | None = None) -> list[dict]:
    """A moment list {"moments": [{"time": "HH:MM:SS", "kind": ..., "text": ...}, ...]} in time order.

    kind is "start" or "end" for the first and last line of an ongoing activity (same
    text for both) and "moment" for a short action. `within` is (first, last) line time
    of the one part of the record the list was made from; every time must be in it.
    """
    moments = _array(_object(value, {"moments"}, "response")["moments"], "moments")
    if not moments:
        raise ContractError("moments: at least one moment is required")
    first, last = (_clock(within[0], "within"), _clock(within[1], "within")) if within else (0, 24 * 3600)
    previous = -1
    for index, moment in enumerate(moments):
        path = f"moments[{index}]"
        _object(moment, {"time", "kind", "text"}, path)
        current = _clock(moment["time"], f"{path}.time")
        if moment["kind"] not in MOMENT_KINDS:
            raise ContractError(f"{path}.kind: expected one of {', '.join(MOMENT_KINDS)}")
        _text(moment["text"], f"{path}.text")
        if current < previous:
            raise ContractError(f"{path}.time: moments must be in time order")
        if not first <= current <= last:
            raise ContractError(f"{path}.time: {moment['time']} is outside this part of the record")
        previous = current
    return moments


def validate_marks(value: Any, candidates: list[tuple[str, str]], actions: list[str]) -> dict:
    """Times of every asked (state, candidate) and action exactly once, plus unseen intervals."""
    marks = _object(value, {"candidates", "actions", "unseen"}, "marks")
    answered = []
    for index, item in enumerate(_array(marks["candidates"], "marks.candidates")):
        path = f"marks.candidates[{index}]"
        _object(item, {"state", "candidate", "times"}, path)
        answered.append((_text(item["state"], f"{path}.state"), _text(item["candidate"], f"{path}.candidate")))
        for time_index, moment in enumerate(_array(item["times"], f"{path}.times")):
            _clock(moment, f"{path}.times[{time_index}]")
    if sorted(answered) != sorted(tuple(pair) for pair in candidates):
        raise ContractError("marks.candidates: answer every asked candidate exactly once")
    found = []
    for index, item in enumerate(_array(marks["actions"], "marks.actions")):
        path = f"marks.actions[{index}]"
        _object(item, {"action", "times"}, path)
        found.append(_text(item["action"], f"{path}.action"))
        for time_index, moment in enumerate(_array(item["times"], f"{path}.times")):
            _clock(moment, f"{path}.times[{time_index}]")
    if sorted(found) != sorted(actions):
        raise ContractError("marks.actions: answer every asked action exactly once")
    for index, interval in enumerate(_array(marks["unseen"], "marks.unseen")):
        path = f"marks.unseen[{index}]"
        _object(interval, {"start", "end"}, path)
        if _clock(interval["end"], f"{path}.end") < _clock(interval["start"], f"{path}.start"):
            raise ContractError(f"{path}: end must not come before start")
    return marks


def validate_matches(value: Any, count: int, events: list[str]) -> dict:
    """One answer for every candidate number 1..count: an event id from the list, or null."""
    matches = _object(value, {"matches"}, "matches")
    numbers = []
    for index, item in enumerate(_array(matches["matches"], "matches.matches")):
        path = f"matches.matches[{index}]"
        _object(item, {"index", "event"}, path)
        if type(item["index"]) is not int:
            raise ContractError(f"{path}.index: expected a candidate number")
        if item["event"] is not None and item["event"] not in events:
            raise ContractError(f"{path}.event: expected an event id from the list or null")
        numbers.append(item["index"])
    if sorted(numbers) != list(range(1, count + 1)):
        raise ContractError("matches.matches: answer every candidate number exactly once")
    return matches
