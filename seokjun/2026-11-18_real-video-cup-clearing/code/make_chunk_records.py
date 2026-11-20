"""Write each day's chunk list as the record the night steps read (덩어리 기록 만들기).

data/chunks/dayN.json (the chunking step's answer) -> data/chunked/dayN.txt, one line per
chunk: `HH:MM:SS | (until HH:MM:SS) sentence`. Sounds are a separate record (a microphone,
not the camera), so they do not go through chunking: every "The sound of ..." sentence of
the second-by-second record becomes a line of its own at its time, and the chunk it falls
in is split around it. No model is called.

Usage: python make_chunk_records.py --days 1 2 3 4
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
SOUND = "The sound of "


def sec(text: str) -> int:
    return int(text[:2]) * 3600 + int(text[3:5]) * 60 + int(text[6:8])


def hms(seconds: int) -> str:
    return (datetime(2000, 1, 1) + timedelta(seconds=seconds)).strftime("%H:%M:%S")


def chunk_record(day: int) -> list[str]:
    chunks = json.loads((EXP / "data" / "chunks" / f"day{day}.json").read_text(encoding="utf-8"))["chunks"]
    rows = [(sec(c["start"]), sec(c["end"]), c["text"]) for c in chunks]
    lines = [l for l in (EXP / "data" / f"day{day}.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    for line in lines:
        if SOUND not in line:
            continue
        moment, sound = sec(line[:8]), line[line.index(SOUND):]
        index = next(i for i, (start, end, _) in enumerate(rows) if start <= moment <= end)
        start, end, text = rows[index]
        pieces = ([(start, moment - 1, text)] if moment > start else []) + [(moment, moment, sound)] \
            + ([(moment + 1, end, text)] if moment < end else [])
        rows[index:index + 1] = pieces
    first, last = sec(lines[0][:8]), sec(lines[-1][:8])
    covered = [s for start, end, _ in rows for s in range(start, end + 1)]
    if covered != list(range(first, last + 1)):
        raise SystemExit(f"day{day}: the chunks do not cover the record exactly once")
    return [f"{hms(start)} | (until {hms(end)}) {text}" for start, end, text in rows]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, nargs="+", required=True)
    out = EXP / "data" / "chunked"
    out.mkdir(parents=True, exist_ok=True)
    for day in parser.parse_args(argv).days:
        path = out / f"day{day}.txt"
        if path.exists():
            raise SystemExit(f"이미 있음: {path}")
        record = chunk_record(day)
        path.write_text("\n".join(record) + "\n", encoding="utf-8")
        print(f"day{day}: {len(record)} lines")


if __name__ == "__main__":
    main()
