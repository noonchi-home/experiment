"""Turn one recorded video into record lines (`HH:MM:SS | sentence`, one every 2 seconds).

Each line is the `observation` sentence of the paper's no-memory predictor prompt
(prompts/paper/predictor_no_memory.txt) given the paper window: the latest 5 frames,
2 seconds apart. Lines start once 5 frames exist (8 s into the video). The only prompt
change: one camera instead of two concatenated cameras. The task list is the 11-04 routine
list for now (the user will choose the robot's tasks later); the chosen task is not used.

Usage: python run_video_text.py <video> <output folder (new)>
Calls OpenRouter (qwen/qwen3.5-27b, Alibaba) once per line; costs money.
"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
AI = Path(__file__).resolve().parents[3]  # the ai repository
sys.path.insert(0, str(AI))
from pam.inference import infer_bundle  # noqa: E402
from pam.messages import build_predictor_messages, read_json  # noqa: E402
from pam.routine_experiment import _bundle, _frame_records  # noqa: E402
from pam.scenarios import load_scenario  # noqa: E402
from pam.video_frames import extract_frames  # noqa: E402

HERE = Path(__file__).resolve().parent
CONFIG = AI / "config/openrouter.json"
START = datetime.fromisoformat("2026-11-18T20:00:00+09:00")
WINDOW, STRIDE = 5, 2
PAUSE, WAIT, TRIES = 2, 60, 5
RATE = "Request rate increased too quickly"

video, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=False)

# Scenario: the routine scenario's camera sentence, replaced by "one camera".
routine = read_json(AI / "scenarios/routine/scenario.json")
camera = next(c for c in routine["prompt_replacements"] if "two back-facing cameras (\nleft_back" in c["old"])
tasks = read_json(AI / "scenarios/routine/tasks.json")
(out / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(out / "scenario.json").write_text(json.dumps({
    "id": "desk_video_2026-11-18",
    "description": "휴대폰 한 대로 책상을 고정해서 찍은 영상 4개(물 마시며 일하다 빈 컵을 치움). 영상을 글로 바꾸기만 한다.",
    "tasks_file": "tasks.json", "memory_files": {},
    "prompt_replacements": [{"old": camera["old"], "new": " frame. Each frame is a single camera view.",
                             "reason": "휴대폰 한 대로 책상을 고정해서 찍었다."}],
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
scenario = load_scenario(out / "scenario.json")

# Paper cadence (config/paper.json): one call every second, each with the latest 5 frames
# 2 seconds apart. Frames are taken once per second, so frame k is at k seconds.
frames = _frame_records(extract_frames(video, out / "frames_1s", fps=1, width=360, height=640), START)
inputs = {"video": {"path": str(video)}, "scenario": {"path": scenario["_config_path"],
                                                     "sha256": scenario["_config_sha256"]}}
lines, cost = [], 0.0
for k in range((WINDOW - 1) * STRIDE, len(frames)):
    window = frames[k - (WINDOW - 1) * STRIDE:k + 1:STRIDE]
    request = build_predictor_messages(window, tasks, memory_kind="none", scenario=scenario)
    for attempt in range(1, TRIES + 1):
        time.sleep(PAUSE)
        work = out / "calls" / f"f{k:03d}-{attempt}"
        work.mkdir(parents=True)
        bundle_path = work / "input_bundle.json"
        bundle_path.write_text(json.dumps(_bundle(request, window, inputs), ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        result = infer_bundle(bundle_path, CONFIG, work)
        if result.get("status") != "api_error":
            break
        message = json.dumps(result.get("diagnostic") or result.get("error"), ensure_ascii=False)
        if RATE not in message:
            print("stopped:", work, message[:300], flush=True)
            sys.exit(1)
        print(f"{k}: rate error, waiting {WAIT}s", flush=True)
        time.sleep(WAIT)
    else:
        print("gave up at frame", k, flush=True)
        sys.exit(1)
    cost += (result.get("usage") or {}).get("cost") or 0
    stamp = (START + timedelta(seconds=frames[k]["seconds"])).strftime("%H:%M:%S")
    if result.get("status") == "valid":
        p = result["prediction"]
        line = f"{stamp} | {p['observation']}"
        extra = {"task_index": p["task_index"], "reasoning": p["reasoning"]}
    else:
        line = f"{stamp} | (no valid sentence)"
        extra = {"errors": result.get("errors")}
    lines.append(line)
    with (out / "details.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time": stamp, "video_seconds": frames[k]["seconds"],
                                 "status": result.get("status"), **extra}, ensure_ascii=False) + "\n")
    print(line, flush=True)
(out / "record.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"done: {len(lines)} lines, cost ${cost:.4f}", flush=True)
