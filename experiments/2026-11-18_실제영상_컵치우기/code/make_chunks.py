"""Turn each day's record into chunks of what the person does (하루 기록을 덩어리로 바꾸기).

Calls the model once per day (role "chunking", prompts/text/chunking.txt; costs money).
Every call is saved under runs/chunks/dayN/attempt-K/. A finished day is written to
data/chunks/dayN.json and data/chunks/dayN.txt (`start ~ end | text`) and is not asked
again. Waits PAUSE seconds before each call; on Alibaba's "Request rate increased too
quickly" it waits WAIT seconds and asks again. Any other error stops.

Usage: python make_chunks.py --days 1 2 3 4
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
AI = EXP.parent.parent
sys.path.insert(0, str(AI))
from pam.daily_run import read_record  # noqa: E402
from pam.inference import infer_text_bundle  # noqa: E402
from pam.text_messages import build_chunking_bundle  # noqa: E402

CONFIG = AI / "config" / "openrouter_text.json"
RATE = "Request rate increased too quickly"
PAUSE, WAIT, TRIES = 30, 120, 6


def chunk_day(day: int) -> dict:
    out_json = EXP / "data" / "chunks" / f"day{day}.json"
    if out_json.exists():
        print(f"day{day}: already done", flush=True)
        return json.loads(out_json.read_text(encoding="utf-8"))
    lines = read_record(EXP / "data" / f"day{day}.txt")
    bundle = build_chunking_bundle(lines, project_dir=AI)
    for attempt in range(1, TRIES + 1):
        work = EXP / "runs" / "chunks" / f"day{day}" / f"attempt-{attempt}"
        if work.exists():
            continue
        time.sleep(PAUSE)
        work.mkdir(parents=True)
        bundle_path = work / "bundle.json"
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(datetime.now().strftime("%H:%M:%S"), f"day{day}: asking ({work.name})", flush=True)
        result = infer_text_bundle(bundle_path, CONFIG, work)
        if result.get("status") == "valid":
            break
        message = json.dumps(result.get("diagnostic") or result.get("errors") or result.get("error"), ensure_ascii=False)
        if result.get("status") == "api_error" and RATE in message:
            print(f"day{day}: rate error, waiting {WAIT}s", flush=True)
            time.sleep(WAIT)
            continue
        raise SystemExit(f"day{day}: stopped ({result.get('status')}): {message[:300]} — see {work}")
    else:
        raise SystemExit(f"day{day}: gave up after {TRIES} tries")
    chunks = result["output"]
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_json.with_suffix(".txt")).write_text(
        "".join(f"{c['start']} ~ {c['end']} | {c['text']}\n" for c in chunks["chunks"]), encoding="utf-8")
    cost = (result.get("usage") or {}).get("cost")
    print(f"day{day}: {len(chunks['chunks'])} chunks from {len(lines)} lines, ${cost}", flush=True)
    return chunks


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, nargs="+", required=True)
    for day in parser.parse_args(argv).days:
        chunk_day(day)


if __name__ == "__main__":
    main()
