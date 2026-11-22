"""Extract PNG frames from one recorded video with ffmpeg.

This module prepares images only: no model call, no action, no evaluation label.
Frame k of an extraction at rate R shows the source frame nearest to k / R
seconds (ffmpeg ``fps`` filter, default nearest rounding). One camera only.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .contracts import ContractError


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ContractError(f"{name} is required to read recorded videos but was not found on PATH.")
    return path


def probe_duration(video: Path) -> float:
    """Container duration in seconds, as reported by ffprobe."""
    video = Path(video).resolve()
    if not video.is_file():
        raise ContractError(f"Video does not exist: {video}")
    completed = subprocess.run(
        [_tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, encoding="utf-8", check=False)
    try:
        duration = float(json.loads(completed.stdout)["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        raise ContractError(f"Cannot read the duration of {video}.") from None
    if completed.returncode != 0 or not duration > 0:
        raise ContractError(f"Cannot read the duration of {video}.")
    return duration


def extract_frames(video: Path, output_dir: Path, *, fps: float, width: int, height: int) -> list[dict]:
    """Write frame_00000.png, frame_00001.png, ... into a new directory.

    Returns one record per frame: index, seconds (index / fps), and image_path.
    """
    video, output_dir = Path(video).resolve(), Path(output_dir).resolve()
    if not video.is_file():
        raise ContractError(f"Video does not exist: {video}")
    if not (isinstance(fps, (int, float)) and fps > 0):
        raise ContractError("Frame rate must be positive.")
    if type(width) is not int or type(height) is not int or width < 16 or height < 16:
        raise ContractError("Frame width and height must be integers of at least 16 pixels.")
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except OSError:
        raise ContractError(f"Choose a new frame directory: {output_dir}") from None
    completed = subprocess.run(
        [_tool("ffmpeg"), "-v", "error", "-nostdin", "-i", str(video),
         "-vf", f"fps={fps!r},scale={width}:{height}", "-start_number", "0",
         str(output_dir / "frame_%05d.png")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if completed.returncode != 0:
        raise ContractError(f"ffmpeg could not extract frames from {video}: {completed.stderr.strip()[:500]}")
    paths = sorted(output_dir.glob("frame_*.png"))
    if not paths:
        raise ContractError(f"No frames were extracted from {video}.")
    return [{"index": index, "seconds": index / fps, "image_path": str(path)}
            for index, path in enumerate(paths)]


def uniform_indices(total: int, count: int) -> list[int]:
    """The same uniform rule as observations.select_reflector_frames (both endpoints, integer rounding)."""
    if type(count) is not int or count < 2 or total < count:
        raise ContractError(f"Cannot select {count} distinct frames from {total}.")
    denominator = count - 1
    return [(2 * index * (total - 1) + denominator) // (2 * denominator) for index in range(count)]


def extract_reflector_frames(video: Path, output_dir: Path, *, count: int = 200,
                             width: int, height: int) -> list[dict]:
    """Extract slightly more than ``count`` evenly spaced frames, then keep exactly ``count``."""
    duration = probe_duration(video)
    frames = extract_frames(video, output_dir, fps=count * 1.02 / duration, width=width, height=height)
    return [frames[index] for index in uniform_indices(len(frames), count)]
