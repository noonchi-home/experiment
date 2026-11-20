"""지정한 날짜의 입력만 시각순 JSON 줄로 내보낸다. 검토용 파일은 열지 않는다."""
import argparse
from datetime import date
from heapq import merge
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent / "일별입력"


def json_rows(path, kind):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield {"종류": kind, **json.loads(line)}


def observations(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            t, location, text = line.rstrip("\n").split(" / ", 2)
            yield {"종류": "관찰", "시각": t, "위치": location, "문장": text}


def read_day(folder):
    weather = json.loads((folder / "weather.json").read_text(encoding="utf-8"))
    streams = (
        ({"종류": "날씨", **row} for row in weather),
        json_rows(folder / "실내온도.jsonl", "실내온도"),
        json_rows(folder / "가전신호.jsonl", "가전신호"),
        observations(folder / "관찰.txt"),
    )
    for row in merge(*streams, key=lambda r: r["시각"]):
        yield {"날짜": folder.name, **row}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("날짜", type=date.fromisoformat)
    args = parser.parse_args()
    folder = ROOT / args.날짜.isoformat()
    if not folder.is_dir():
        parser.error("일별입력에 이 날짜가 없습니다.")
    sys.stdout.reconfigure(encoding="utf-8")
    for item in read_day(folder):
        print(json.dumps(item, ensure_ascii=False))
