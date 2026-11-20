"""Freeze each day's FSM memory and retain evidence for next-day reflection.

This module never calls a model, executes an action, edits a memory rule, or
silently carries the seed into an unassigned day. It is a single-writer local
store: immutable version files and an atomically replaced assignment manifest.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

from .contracts import ContractError, validate_memory
from .messages import read_json


class MemoryStoreError(ValueError):
    """The memory history or its supporting artifacts cannot be accepted."""


_MODEL = "qwen/qwen3.5-27b"


def _day(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise MemoryStoreError("Memory days must use YYYY-MM-DD.") from None
    if parsed.isoformat() != value:
        raise MemoryStoreError("Memory days must use YYYY-MM-DD.")
    return parsed


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _thinking_on(value: object) -> bool:
    return isinstance(value, dict) and set(value) == {"enabled"} and value["enabled"] is True


def _read(path: Path) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError:
        raise MemoryStoreError(f"Cannot read required memory artifact: {path}") from None


def _json(path: Path) -> dict:
    try:
        value = read_json(Path(path))
    except (ContractError, OSError, ValueError, TypeError):
        raise MemoryStoreError(f"Invalid JSON memory artifact: {path}") from None
    if not isinstance(value, dict):
        raise MemoryStoreError(f"Memory artifact must be a JSON object: {path}")
    return value


def _fsm(value: object) -> dict:
    try:
        return validate_memory(value, "fsm")
    except ContractError as error:
        raise MemoryStoreError(str(error)) from None


def _write_new(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        raise MemoryStoreError(f"Cannot create immutable memory artifact: {path}") from None


def _write_manifest(path: Path, manifest: dict) -> None:
    temporary = path.with_name(f".manifest-{uuid.uuid4().hex}.tmp")
    data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        _write_new(temporary, data)
        os.replace(temporary, path)
    except OSError:
        raise MemoryStoreError("Cannot atomically publish the memory assignment manifest.") from None
    finally:
        if temporary.exists():
            temporary.unlink()


def _manifest(store_dir: Path) -> dict:
    value = _json(store_dir / "manifest.json")
    if value.get("schema_version") != 1 or value.get("memory_kind") != "fsm":
        raise MemoryStoreError("Unsupported memory store format.")
    assignments, versions = value.get("assignments"), value.get("versions")
    if not isinstance(assignments, dict) or not assignments or not isinstance(versions, dict):
        raise MemoryStoreError("Memory store assignments or versions are missing.")
    for day, identifier in assignments.items():
        _day(day)
        if not isinstance(identifier, str) or identifier not in versions:
            raise MemoryStoreError("A day refers to a missing memory version.")
        record = versions[identifier]
        if (not isinstance(record, dict) or record.get("version_id") != identifier
                or record.get("effective_day") != day or not isinstance(record.get("file"), str)
                or not isinstance(record.get("sha256"), str)):
            raise MemoryStoreError("Memory version metadata does not match its frozen day.")
    return value


def initialize_store(store_dir: Path, seed_path: Path, day: str) -> dict:
    """Assign an exact copy of the provided FSM seed to one explicit first day."""
    _day(day)
    root, seed = Path(store_dir).resolve(), Path(seed_path).resolve()
    _fsm(_json(seed))
    seed_bytes = _read(seed)
    if root.exists():
        raise MemoryStoreError("The memory store already exists; it will not be reset.")
    try:
        (root / "versions").mkdir(parents=True, exist_ok=False)
    except OSError:
        raise MemoryStoreError("Cannot create a new memory store.") from None
    identifier = "000_seed"
    record = {
        "version_id": identifier, "file": "versions/000_seed.json", "sha256": _hash(seed_bytes),
        "effective_day": day, "source_day": None, "origin": "provided_seed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evidence": {"seed": {"path": str(seed), "sha256": _hash(seed_bytes)}},
    }
    manifest = {"schema_version": 1, "memory_kind": "fsm", "assignments": {day: identifier},
                "versions": {identifier: record}}
    _write_new(root / record["file"], seed_bytes)
    _write_manifest(root / "manifest.json", manifest)
    return deepcopy(manifest)


def get_memory_for_day(store_dir: Path, day: str) -> tuple[dict, dict]:
    """Return the frozen FSM and record, including its absolute memory_path.

    Unknown days are errors. No reflection means no implicit new assignment.
    Editing a version file is detected before its memory can be used again.
    """
    _day(day)
    root = Path(store_dir).resolve()
    manifest = _manifest(root)
    identifier = manifest["assignments"].get(day)
    if identifier is None:
        raise MemoryStoreError(f"No memory is assigned to {day}; a prior reflection is required.")
    record = deepcopy(manifest["versions"][identifier])
    path = (root / record["file"]).resolve()
    if not path.is_relative_to(root / "versions"):
        raise MemoryStoreError("A memory version points outside the version directory.")
    if _hash(_read(path)) != record["sha256"]:
        raise MemoryStoreError("A frozen memory version has changed.")
    if record.get("origin") == "actual_api_reflection":
        evidence = record.get("evidence")
        if not isinstance(evidence, dict):
            raise MemoryStoreError("Reflection provenance is missing.")
        for section in ("artifacts", "inputs"):
            if not isinstance(evidence.get(section), dict) or not evidence[section]:
                raise MemoryStoreError("Reflection provenance snapshots are missing.")
            for proof in evidence[section].values():
                if not isinstance(proof, dict) or not isinstance(proof.get("snapshot"), str):
                    raise MemoryStoreError("Reflection provenance snapshot metadata is invalid.")
                snapshot = (root / proof["snapshot"]).resolve()
                if (not snapshot.is_relative_to(root / "evidence" / identifier)
                        or _hash(_read(snapshot)) != proof.get("sha256")):
                    raise MemoryStoreError("A reflection provenance snapshot has changed.")
    memory = _fsm(_json(path))
    record["memory_path"] = str(path)
    return memory, record


def _proof(path: Path) -> tuple[dict, bytes]:
    path = Path(path).resolve()
    data = _read(path)
    return {"path": str(path), "sha256": _hash(data)}, data


def _text_memory(raw: str) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise MemoryStoreError("Reflection memory has duplicate JSON keys.")
            value[key] = item
        return value

    def reject_constant(value):
        raise MemoryStoreError("Reflection memory contains a non-JSON numeric constant.")

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=reject_constant)
    except (TypeError, ValueError):
        raise MemoryStoreError("Reflection content must be complete strict JSON.") from None
    return _fsm(value)


def commit_reflection(store_dir: Path, result_path: Path, bundle_path: Path,
                      source_day: str, effective_day: str) -> dict:
    """Assign a validated real-response artifact to exactly the following day.

    The original model content is copied byte-for-byte as the new memory JSON.
    Small proof artifacts and input manifests/texts are copied into evidence/;
    image files remain referenced by the original bundle's paths and hashes.
    """
    source_date, effective_date = _day(source_day), _day(effective_day)
    if effective_date != source_date + timedelta(days=1):
        raise MemoryStoreError("Reflected memory can apply only to the immediately following calendar day.")
    root, result_path, bundle_path = Path(store_dir).resolve(), Path(result_path).resolve(), Path(bundle_path).resolve()
    manifest = _manifest(root)
    if effective_day in manifest["assignments"]:
        raise MemoryStoreError("The following day's memory is already frozen and cannot be replaced.")
    _, source_record = get_memory_for_day(root, source_day)
    result, bundle = _json(result_path), _json(bundle_path)
    required = {"status": "valid", "role": "reflector", "api_request_attempted": True,
                "model_response_received": True, "action_executed": False, "finish_reason": "stop",
                "requested_model": _MODEL, "response_model": _MODEL, "memory_automatically_applied": False}
    if any(type(result.get(key)) is not type(value) or result.get(key) != value for key, value in required.items()):
        raise MemoryStoreError("Only a successful actual reflector response with no executed action can be committed.")
    if result.get("errors") != [] or not _thinking_on(result.get("reasoning_requested")):
        raise MemoryStoreError("Reflection must have no validation errors and must request thinking.")
    generation = bundle.get("generation")
    if (bundle.get("status") != "prepared" or bundle.get("execution_mode") != "offline_preparation"
            or bundle.get("role") != "reflector" or bundle.get("operation") != "update"
            or bundle.get("memory_kind") != "fsm" or bundle.get("model") != "Qwen3.5-27B"
            or bundle.get("action_executed") is not False
            or not isinstance(generation, dict) or set(generation) != {"temperature", "enable_thinking"}
            or type(generation.get("temperature")) is not float or generation["temperature"] != 0.3
            or generation.get("enable_thinking") is not True):
        raise MemoryStoreError("The source bundle must be the paper's prepared FSM memory update.")
    frame_count = bundle.get("frame_count", 200)
    if (type(frame_count) is not int or frame_count not in (50, 100, 150, 200)
            or frame_count != 200 and bundle.get("frame_count_source") != "explicit_user_override"
            or not isinstance(bundle.get("frames"), list) or len(bundle["frames"]) != frame_count):
        raise MemoryStoreError("Reflection must contain paper 200 frames or the declared user-requested 150/100/50 frames.")
    inputs = bundle.get("inputs")
    if not isinstance(inputs, dict) or not {"memory", "summary", "observations"} <= set(inputs):
        raise MemoryStoreError("Reflection input proof must include memory, summary, and observations.")
    input_data = {}
    for name, proof in inputs.items():
        if not isinstance(name, str) or not isinstance(proof, dict) or not isinstance(proof.get("path"), str):
            raise MemoryStoreError("Invalid reflection input provenance.")
        actual, data = _proof(Path(proof["path"]))
        if proof.get("sha256") != actual["sha256"]:
            raise MemoryStoreError(f"A reflection input changed after preparation: {name}")
        input_data[name] = (actual, data)
    memory_proof = input_data["memory"][0]
    if (memory_proof["path"] != source_record["memory_path"]
            or memory_proof["sha256"] != source_record["sha256"]):
        raise MemoryStoreError("Reflection input memory does not match the source day's frozen version.")

    artifact_paths = {"result": result_path, "input_bundle": bundle_path,
                      "raw_api_response": result_path.parent / "api_response.raw.json",
                      "input_reference": result_path.parent / "input_reference.json",
                      "request_record": result_path.parent / "request_record.json"}
    artifacts = {name: _proof(path) for name, path in artifact_paths.items()}
    reference = _json(artifact_paths["input_reference"])
    if (reference.get("sha256") != artifacts["input_bundle"][0]["sha256"]
            or reference.get("path") != str(bundle_path) or reference.get("action_executed") is not False):
        raise MemoryStoreError("The actual inference input reference does not match the supplied bundle.")
    request = _json(artifact_paths["request_record"])
    if (request.get("model") != _MODEL or type(request.get("temperature")) is not float
            or request["temperature"] != 0.3 or not _thinking_on(request.get("reasoning"))):
        raise MemoryStoreError("Actual request settings do not match paper reflection settings.")
    provider_config = reference.get("provider_config")
    routing = provider_config.get("provider") if isinstance(provider_config, dict) else None
    if not isinstance(provider_config, dict) or provider_config.get("reflector_frame_count", 200) != frame_count:
        raise MemoryStoreError("The actual provider profile does not match the declared reflection frame count.")
    if (not isinstance(routing, dict) or request.get("provider") != routing
            or routing.get("allow_fallbacks") is not False or routing.get("require_parameters") is not True
            or not isinstance(routing.get("order"), list) or len(routing["order"]) != 1):
        raise MemoryStoreError("The actual request must use one fixed parameter-supporting provider.")
    raw_api = _json(artifact_paths["raw_api_response"])
    response_id, provider = result.get("response_id"), result.get("provider")
    if (not isinstance(response_id, str) or not response_id.strip() or not isinstance(provider, str)
            or not provider.strip() or not isinstance(routing["order"][0], str)
            or provider.casefold() != routing["order"][0].casefold()
            or raw_api.get("id") != response_id or raw_api.get("provider") != provider
            or raw_api.get("model") != _MODEL or "error" in raw_api):
        raise MemoryStoreError("Response identity, model, or provider is inconsistent with the actual API evidence.")
    choices = raw_api.get("choices")
    if (not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict)
            or choices[0].get("finish_reason") != "stop" or not isinstance(choices[0].get("message"), dict)):
        raise MemoryStoreError("The raw API response is not one complete reflection.")
    raw_memory = choices[0]["message"].get("content")
    if not isinstance(raw_memory, str) or raw_memory != result.get("raw_response"):
        raise MemoryStoreError("The stored reflection text differs from the original API content.")
    memory = _text_memory(raw_memory)
    if memory != _fsm(result.get("memory")):
        raise MemoryStoreError("The result memory was modified after the model response.")

    identifier = f"{len(manifest['versions']):03d}_{effective_day}"
    relative_dir = Path("evidence") / identifier
    try:
        (root / relative_dir).mkdir(parents=True, exist_ok=False)
    except OSError:
        raise MemoryStoreError("Cannot create new reflection evidence; existing versions will not be replaced.") from None
    evidence = {"response_id": response_id, "provider": provider, "model": _MODEL,
                "reasoning_requested": {"enabled": True}, "source_version_id": source_record["version_id"],
                "reflector_frame_count": frame_count, "paper_reflector_frame_count": 200,
                "frame_count_source": bundle.get("frame_count_source", "paper"),
                "source_memory_sha256": source_record["sha256"], "artifacts": {}, "inputs": {}}
    for name, (proof, data) in artifacts.items():
        snapshot = relative_dir / f"{name}.json"
        _write_new(root / snapshot, data)
        evidence["artifacts"][name] = {**proof, "snapshot": snapshot.as_posix()}
    for index, (name, (proof, data)) in enumerate(input_data.items()):
        snapshot = relative_dir / f"input_{index:03d}.bin"
        _write_new(root / snapshot, data)
        evidence["inputs"][name] = {**proof, "snapshot": snapshot.as_posix()}
    memory_bytes = raw_memory.encode("utf-8")
    record = {"version_id": identifier, "file": f"versions/{identifier}.json", "sha256": _hash(memory_bytes),
              "effective_day": effective_day, "source_day": source_day, "origin": "actual_api_reflection",
              "created_at": datetime.now(timezone.utc).isoformat(), "evidence": evidence}
    _write_new(root / record["file"], memory_bytes)
    manifest["versions"][identifier] = record
    manifest["assignments"][effective_day] = identifier
    _write_manifest(root / "manifest.json", manifest)
    return {**deepcopy(record), "memory_path": str(root / record["file"])}
