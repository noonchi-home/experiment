"""영상(mp4)을 초당 12프레임 PNG로 뽑아 2초 창마다 VLM에 보내고, 창마다 관찰 기록 .json을 저장한다(VLM 호출).

PNG는 임시 폴더에만 만들고 끝나면 지운다(저장하지 않음). 끝에 남은 2초 미만의 프레임은 쓰지 않는다.
창의 시각 = 영상 시작 시각(scenarios/<시나리오>/scenario.json start, 2026-11-03 07:00:00) + 창 시작 위치.(test에만 적용되고, 추후 실제 시간으로 동기화)
결과: data/Coffee_man/live_<vlm>_rep<n>/frames/070000.json, 070002.json, ... 와 scenario.json. 판단은 run_coffee.py가 한다.

VLM은 Qwen3.5-27B(OpenRouter)이고, OPENROUTER_API_KEY가 필요하다(.env 또는 환경 변수).
ffmpeg가 필요하다: 환경 변수 FFMPEG, PATH의 ffmpeg, 또는 ~/.local/share/imageio-ffmpeg/ffmpeg 순서로 찾는다.
실행: python record_video_vlm.py [--scenario scenarios/Coffee_man] [--rep 1]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from noonchi import VisionClient, VisionError  # noqa: E402
from noonchi.config import MODEL, load_env, read_json  # noqa: E402
from noonchi.vision import DEFAULT_PROVIDER, PROVIDERS  # noqa: E402

FFMPEG_FALLBACK = Path.home() / ".local" / "share" / "imageio-ffmpeg" / "ffmpeg"


def find_ffmpeg() -> str:
    for c in (os.environ.get("FFMPEG"), shutil.which("ffmpeg"), str(FFMPEG_FALLBACK)):
        if c and Path(c).is_file():
            return c
    raise FileNotFoundError("ffmpeg not found (set FFMPEG, add it to PATH, or install imageio-ffmpeg)")


def extract_frames(video: Path, out_dir: Path, fps: int, width: int | None) -> list[Path]:
    vf = f"fps={fps}" + (f",scale={width}:-2" if width else "")
    subprocess.run([find_ffmpeg(), "-loglevel", "error", "-i", str(video), "-vf", vf, str(out_dir / "f_%05d.png")],
                   check=True)
    return sorted(out_dir.glob("f_*.png"))


def windows(frames: list[Path], size: int) -> list[list[Path]]:
    """프레임 k(0부터)는 영상의 k/fps초. size개씩 끊고, 끝에 남은 size 미만은 버린다."""
    return [frames[i:i + size] for i in range(0, len(frames) - size + 1, size)]


def main() -> int:
    load_env(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=str(ROOT / "scenarios" / "Coffee_man"))
    ap.add_argument("--vlm", choices=sorted(PROVIDERS), default=os.environ.get("VLM_PROVIDER", DEFAULT_PROVIDER))
    ap.add_argument("--model", help="override the provider's model name")
    ap.add_argument("--rep", type=int, default=1)
    args = ap.parse_args()
    sc = read_json(Path(args.scenario) / "scenario.json")
    v = MODEL["video"]
    fps, win = v["fps"], v["window_seconds"]
    video, start = ROOT / sc["video"], datetime.fromisoformat(sc["start"])
    out = ROOT / sc["cases"] / f"live_{args.vlm}_rep{args.rep}"
    if out.exists():
        print(f"error: {out.name} already exists; move it away first (results are never overwritten)", file=sys.stderr)
        return 1
    try:
        vision = VisionClient(os.environ.get(VisionClient.key_env(args.vlm), ""), provider=args.vlm, model=args.model)
    except VisionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    who, stamp = f"{vision.provider}:{vision.model}", datetime.now().strftime("%Y-%m-%d %H:%M")

    with tempfile.TemporaryDirectory(prefix="noonchi_frames_") as tmp:  # PNG는 여기서만 쓰고 지운다
        groups = windows(extract_frames(video, Path(tmp), fps, v["frame_width"]), fps * win)
        print(f"{video.name}: {len(groups)} windows x {fps * win} frames ({fps} fps)", flush=True)
        (out / "frames").mkdir(parents=True)
        for w, paths in enumerate(groups):
            t0, t1 = start + timedelta(seconds=w * win), start + timedelta(seconds=(w + 1) * win)
            try:
                f = vision.describe(paths, t0.isoformat(), clip={"fps": fps, "end": t1.isoformat()})
            except VisionError as e:
                print(f"error at window {w} ({t0:%H:%M:%S}): {e}; {w} windows saved in {out}", file=sys.stderr)
                return 1
            f["frame"] = f"{t0:%H%M%S}"
            (out / "frames" / f"{f['frame']}.json").write_text(json.dumps(f, ensure_ascii=False, indent=1) + "\n",
                                                               encoding="utf-8")
            act = "; ".join(f"{p['location']}: {p['activity']}" for p in f["people"]) or "no one"
            print(f"{t0:%H:%M:%S}  {act}", flush=True)
    meta = {"name": f"Live VLM observations: {out.name}",
            "description": f"{who} observations of {video.name}, recorded {stamp}.",
            "video": sc["video"], "start": sc["start"], "fps": fps, "window_seconds": win, "frame_width": v["frame_width"],
            "_note": "Real VLM output from record_video_vlm.py (not hand-written). One observation per 2-second window; "
                     "time = video start + window start. PNG frames were not saved."}
    (out / "scenario.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"VLM calls {vision.usage['calls']}, tokens {vision.usage['total_tokens']}\nsaved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
