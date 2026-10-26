"""Paper observation selection and two-camera image composition.

This module prepares inputs only; it never predicts an action. The predictor
uses five paired observations at t-8, t-6, t-4, t-2, t. A reflector sees 200
uniformly selected paired observations from the day's chronological record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

from PIL import Image, UnidentifiedImageError

from .contracts import ContractError, validate_observation_records


class ObservationNotReady(ValueError):
    """The predictor has not yet accumulated a complete eight-second window."""


class InsufficientObservations(ValueError):
    """The day record cannot supply the required number of distinct frames."""


@dataclass(frozen=True)
class Observation:
    timestamp: datetime
    left_image: Path
    right_image: Path


def _aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ContractError(f"{label} must include a date, time, and timezone.")


def _validate_sequence(observations: Sequence[Observation]) -> None:
    previous = None
    for index, observation in enumerate(observations):
        if not isinstance(observation, Observation):
            raise ContractError(f"Observation {index} must be an Observation.")
        _aware_datetime(observation.timestamp, f"Observation {index} timestamp")
        if previous is not None and observation.timestamp <= previous:
            raise ContractError("Observation timestamps must be unique and chronological.")
        if not isinstance(observation.left_image, Path) or not isinstance(
            observation.right_image, Path
        ):
            raise ContractError(f"Observation {index} needs left and right image Paths.")
        previous = observation.timestamp


def _distinct_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _camera_paths(observation: Observation) -> tuple[Path, Path]:
    left, right = observation.left_image.resolve(), observation.right_image.resolve()
    for label, path in (("left", left), ("right", right)):
        if not path.is_file():
            raise ContractError(f"Missing {label} camera image: {path}")
    if left == right or left.samefile(right):
        raise ContractError("Left and right cameras must reference distinct image files.")
    return left, right


def load_observations(manifest_path: Path) -> list[Observation]:
    """Read validated paired observations; resolve image paths at the manifest.

    A manifest has only an ``observations`` list. Each entry has ``timestamp``,
    ``left_image``, and ``right_image``. Evaluation labels are not model input.
    Image contents are decoded when selected observations are composed.
    """
    manifest_path = Path(manifest_path).resolve()
    try:
        value = json.loads(
            manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_distinct_pairs
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot read observation manifest {manifest_path}: {exc}") from exc
    records = validate_observation_records(value)
    result = []
    for record in records:
        # Python 3.11 accepts both ISO 8601 UTC 'Z' and explicit UTC offsets.
        observation = Observation(
            timestamp=datetime.fromisoformat(record["timestamp"]),
            left_image=(manifest_path.parent / record["left_image"]).resolve(),
            right_image=(manifest_path.parent / record["right_image"]).resolve(),
        )
        _camera_paths(observation)
        result.append(observation)
    _validate_sequence(result)
    return result


def select_predictor_window(
    observations: Sequence[Observation], at: datetime
) -> list[Observation]:
    """Select the paper's five timestamps without nearest-frame substitution.

    Before eight seconds have elapsed from the first observation this raises
    ObservationNotReady, which is input readiness, not the model's NO_ACT.
    Later gaps are malformed input and raise ContractError.
    """
    _aware_datetime(at, "Prediction time")
    _validate_sequence(observations)
    if not observations or at - observations[0].timestamp < timedelta(seconds=8):
        raise ObservationNotReady("A complete eight-second observation window is not ready.")
    wanted = [at - timedelta(seconds=offset) for offset in (8, 6, 4, 2, 0)]
    by_time = {observation.timestamp: observation for observation in observations}
    missing = [timestamp.isoformat() for timestamp in wanted if timestamp not in by_time]
    if missing:
        raise ContractError("Missing required observation timestamps: " + ", ".join(missing))
    return [by_time[timestamp] for timestamp in wanted]


def select_reflector_frames(
    observations: Sequence[Observation], count: int = 200
) -> list[Observation]:
    """Uniform selection including both endpoints, without duplicate padding.

    Paper: uniformly downsample to 200 temporal frames. Undisclosed detail:
    choose index round_half_up(i * (N-1) / (count-1)), using integer arithmetic
    so platform-dependent floating-point rounding cannot change the input.
    ``count`` permits smaller processing tests; the paper configuration is 200.
    """
    _validate_sequence(observations)
    if type(count) is not int or count < 2:
        raise ContractError("Reflector frame count must be an integer of at least two.")
    total = len(observations)
    if total < count:
        raise InsufficientObservations(
            f"Reflector requires {count} distinct observations; only {total} are available."
        )
    denominator = count - 1
    indices = [
        (2 * index * (total - 1) + denominator) // (2 * denominator)
        for index in range(count)
    ]
    return [observations[index] for index in indices]


def compose_observations(
    observations: Sequence[Observation], output_dir: Path, *, vertical_padding_px: int = 0
) -> list[dict]:
    """Write lossless RGB PNGs: left camera then right, with no resizing.

    Images must have equal heights. Their original pixel dimensions and left /
    right ordering are preserved. Returned paths are absolute for inspection.
    Optional equal black margins above and below the combined image preserve
    every source RGB pixel. This letterboxing is an experimental API-input
    adaptation, not a paper parameter. The default adds no padding.
    These files contain no action labels or model output.
    """
    if type(vertical_padding_px) is not int or vertical_padding_px < 0:
        raise ContractError("Vertical padding must be a nonnegative integer pixel count.")
    _validate_sequence(observations)
    output_dir = Path(output_dir).resolve()
    pairs = [_camera_paths(observation) for observation in observations]
    output_paths = [output_dir / f"frame_{index:03d}.png" for index in range(len(pairs))]
    source_paths = {path for pair in pairs for path in pair}
    if any(path in source_paths for path in output_paths):
        raise ContractError("Output image paths must not overwrite source camera images.")
    if any(path.exists() for path in output_paths):
        raise ContractError("Composed frame paths already exist; choose a fresh output directory.")
    output_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for observation, (left_path, right_path), output_path in zip(
        observations, pairs, output_paths
    ):
        try:
            with Image.open(left_path) as left_source, Image.open(right_path) as right_source:
                if left_source.height != right_source.height:
                    raise ContractError(
                        f"Camera image heights differ at {observation.timestamp.isoformat()}: "
                        f"left={left_source.height}, right={right_source.height}."
                    )
                left = left_source.convert("RGB")
                right = right_source.convert("RGB")
                combined = Image.new(
                    "RGB", (left.width + right.width, left.height + 2 * vertical_padding_px),
                    color=(0, 0, 0),
                )
                combined.paste(left, (0, vertical_padding_px))
                combined.paste(right, (left.width, vertical_padding_px))
                combined.save(output_path, format="PNG")
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise ContractError(
                f"Cannot decode or compose camera images at {observation.timestamp.isoformat()}: {exc}"
            ) from exc
        result.append(
            {
                "timestamp": observation.timestamp.isoformat(),
                "left_image": str(left_path),
                "right_image": str(right_path),
                "image_path": str(output_path),
                "width": combined.width,
                "height": combined.height,
                "vertical_padding_px": vertical_padding_px,
                "content_box": [0, vertical_padding_px, combined.width,
                                vertical_padding_px + left.height],
            }
        )
    return result
