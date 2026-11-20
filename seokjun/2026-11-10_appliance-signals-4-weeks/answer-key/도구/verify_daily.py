"""빈 폴더에 원본을 하루씩 추가해, 미래 파일이 없는 실행도 같은 정답인지 확인한다."""
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
import json
import subprocess
import sys

from build import build
from source import DEFAULT_INPUT, ROOT, load_jsonl, write_jsonl


def main():
    data = ROOT / "채점자료"
    nights = load_jsonl(data / "밤별규칙.jsonl")
    daylight = load_jsonl(data / "시각별판단.jsonl")
    dates = sorted({r["날짜"] for r in nights})
    with TemporaryDirectory() as name:
        temp = Path(name)
        partial, out = temp / "일별입력", temp / "재생"
        partial.mkdir()
        for day in dates:
            copytree(DEFAULT_INPUT / day, partial / day)
            new_nights, new_decisions, _, _ = build(partial,out)
            assert new_nights == [r for r in nights if r["날짜"] <= day], day
            assert new_decisions == [r for r in daylight if r["날짜"] <= day], day
        print("통과 | 미래 날짜 파일이 없는 28회 독립 재생에서 모든 밤 규칙과 낮 판단이 동일")
        night_actual, day_actual = temp / "밤.jsonl", temp / "낮.jsonl"
        submitted = [{"날짜":d,"규칙들":[{"규칙ID":s["규칙ID"],**a} for s in nights if s["날짜"]==d and
                      s["종류"]!="고정안전" for a in s["활성"]]} for d in dates]
        write_jsonl(night_actual,submitted)
        rows = [{k:r[k] for k in ("날짜","시각","행동")} | {"판정":r["예상판정"]} for r in daylight]
        write_jsonl(day_actual,rows)
        result_file = temp / "대조.json"
        cmd = [sys.executable,"-X","utf8","-B",str(ROOT / "결과대조.py"),"--밤",str(night_actual),
               "--낮",str(day_actual),"--출력",str(result_file)]
        good = subprocess.run(cmd,capture_output=True)
        assert good.returncode == 0, good.stdout+good.stderr
        assert json.loads(result_file.read_text("utf-8"))["차이항목수"] == 0
        sample = next(r for r in rows if r["판정"] == "실행")
        sample["판정"] = "취소"
        write_jsonl(day_actual,rows)
        bad = subprocess.run(cmd,capture_output=True)
        assert bad.returncode == 1, bad.stdout+bad.stderr
        assert json.loads(result_file.read_text("utf-8"))["차이항목수"] == 1
        print("통과 | 28일 비교 형식 왕복, 실행을 취소로 바꾼 1건을 실제 CLI가 검출 (로봇 성능 시험과 별도)")


if __name__ == "__main__":
    main()
