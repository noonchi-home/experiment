"""Experiment ①: run the nights with the answer key instead of the AI (돈이 들지 않는다).

Needs the generated records and answer key (python make_records.py --out ../data).
Prints, for the given night, every checked candidate next to the expected result.

Usage:
    python free_run.py --data ../data --run-dir ../runs/free --night 7
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import free_steps as fs
from pam.daily_run import run_night


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="정답표 값으로 밤 단계를 돌리고, 그 밤의 결과를 예상과 나란히 보여 준다.")
    parser.add_argument("--data", type=Path, required=True, help="day1.txt ... 와 answer_key.json 이 있는 폴더")
    parser.add_argument("--run-dir", type=Path, required=True, help="밤마다 결과를 저장할 폴더")
    parser.add_argument("--night", type=int, required=True)
    args = parser.parse_args(argv)
    key = json.loads((args.data / "answer_key.json").read_text(encoding="utf-8"))
    records = {day: args.data / f"day{day}.txt" for day in range(1, args.night + 1)}
    run_night(args.night, records, args.run_dir, fs.answer_key_steps(key))
    results = json.loads((args.run_dir / f"night-{args.night}" / "check_results.json").read_text(encoding="utf-8"))
    rows = fs.score_night(results, key, args.night)
    for row in rows:
        mark = "같음" if row["match"] else "다름"
        print(f"[{mark}] {row['state']:13} {row['candidate']:22} n={row['n']:2} k={row['k']:2} "
              f"p={row['p_value']:.2e} 통과={row['passed']} 예상={row['expected']}")
    print(f"{args.night}일째 밤: {sum(row['match'] for row in rows)}/{len(rows)} 예상과 같음")


if __name__ == "__main__":
    main()
