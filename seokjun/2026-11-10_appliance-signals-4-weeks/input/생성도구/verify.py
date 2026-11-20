"""생성 코드를 불러오지 않고 디스크에 저장된 28일을 독립 검사한다."""
from collections import Counter
from datetime import date, timedelta
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from 하루읽기 import read_day


def json_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def seconds(value):
    h, m, s = map(int, value.split(":"))
    assert 0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60, value
    return h * 3600 + m * 60 + s


def check_states(rows, label):
    doors, motors, power = set(), set(), set()
    for sig in rows:
        device, event, value = (sig[key] for key in ("기기", "항목", "값"))
        if device == "TV" and event == "채널":
            assert device in power, (label, sig)
        for group, field, start, stop in ((doors, "문", "열림", "닫힘"), (motors, "운전", "시작", "완료"),
                                          (power, "전원", "켜짐", "꺼짐")):
            if event != field or value not in (start, stop):
                continue
            assert (device in group) == (value == stop), (label, sig, group)
            if value == start:
                group.add(device)
            else:
                group.remove(device)
    assert not doors and not motors and not power, (label, doors, motors, power)


def check_scenes(folder, rows, times, sentences, counts):
    sport = [r for r in rows if r["기기"] == "TV" and r["값"] == "채널 37"]
    expected = date.fromisoformat(folder.name).weekday() in (0, 4)
    assert len(sport) == int(expected), folder.name
    if sport:
        switch = seconds(sport[0]["시각"])
        assert abs(switch - 22 * 3600) <= 90
        assert "점수판" in sentences[times.index(switch)]
        first_beer = next(t for t, s in zip(times, sentences) if "냉장고" in s and "맥주" in s)
        counts["경기전_맥주" if first_beer < switch else "경기후_맥주"] += 1
    by_time = dict(zip(times, sentences))
    for r in rows:
        if r["항목"] == "문열림경고" and r["기기"] == "냉장고":
            t = seconds(r["시각"])
            assert t in by_time
            scene = by_time[t]
            if "앞에는 사람이 없다" in scene:
                counts["경고_앞이빔"] += 1
            elif "열린 냉장고 앞에 서서" in scene:
                counts["경고_사용중"] += 1
            else:
                assert "보이지 않는다" in scene, (folder.name, scene)
                counts["경고_시야가림"] += 1


def main():
    start = date(2026, 10, 12)
    folders = sorted((ROOT / "일별입력").iterdir())
    assert [f.name for f in folders] == [(start + timedelta(days=n)).isoformat() for n in range(28)]
    windows = json_lines(ROOT / "검토용" / "수집구간.jsonl")
    spans = {w["신호ID"]: w for w in windows}
    assert len(spans) == len(windows)
    calendars = json_lines(ROOT / "검토용" / "날짜별설정.jsonl")
    assert [r["날짜"] for r in calendars] == [f.name for f in folders]
    totals, on_days, all_signals = Counter(), Counter(), set()
    for folder, calendar in zip(folders, calendars):
        rows = json_lines(folder / "가전신호.jsonl")
        assert rows and [r["시각"] for r in rows] == sorted(r["시각"] for r in rows)
        check_states(rows, folder.name)
        expected = set()
        for row in rows:
            key = row["신호ID"]
            assert key not in all_signals and key.startswith(folder.name + "-"), key
            all_signals.add(key)
            actor, t = row["주체"], seconds(row["시각"])
            assert actor in ("기계", "사람")
            lo, hi = (t if actor == "기계" else t - 600), t + 600
            subset = range(lo, hi + 1, 4)
            assert len(subset) == (151 if actor == "기계" else 301)
            window = spans[key]
            assert (window["날짜"], seconds(window["시작"]), seconds(window["끝"]), window["관찰수"]) == (folder.name, lo, hi, len(subset))
            expected.update(subset)
            totals[actor] += 1
            totals["구간별_줄수_합"] += len(subset)
        times, sentences = [], []
        for line in (folder / "관찰.txt").read_text(encoding="utf-8").splitlines():
            t, loc, sentence = line.split(" / ")
            assert loc and sentence and loc != "욕실" and "\ufffd" not in line, (folder.name, line)
            times.append(seconds(t))
            sentences.append(sentence)
        assert times == sorted(expected), (folder.name, len(times), len(expected))
        assert len(times) == calendar["관찰줄수"] and len(rows) == calendar["가전신호수"]
        totals["관찰"] += len(times)
        if any(a == b and s2 - s1 == 4 for s1, s2, a, b in zip(times, times[1:], sentences, sentences[1:])):
            on_days["동일문장_연속"] += 1
        check_scenes(folder, rows, times, sentences, on_days)
        sky = json.loads((folder / "weather.json").read_text(encoding="utf-8"))
        assert [seconds(r["시각"]) for r in sky] == list(range(0, 86400, 3600))
        temp = json_lines(folder / "실내온도.jsonl")
        assert [seconds(r["시각"]) for r in temp] == list(range(0, 86400, 1800))
        # 사용자에게 주는 실제 일별 읽기 경로를 전부 실행해 시각·건수를 대조한다.
        counts, previous = Counter(), -1
        for row in read_day(folder):
            t = seconds(row["시각"])
            assert row["날짜"] == folder.name and t >= previous
            assert not any(key in row for key in ("작성자메모", "저녁손님", "수집끝", "생활설정"))
            previous = t
            counts[row["종류"]] += 1
        assert counts == {"날씨": 24, "실내온도": 48, "가전신호": len(rows), "관찰": len(times)}
        scene_text = "\n".join(set(sentences))
        for word in ("이불", "충전기", "노트북", "약통", "접이식", "드라마", "식기세척기", "맥주", "건조대", "방문객", "우산", "드라이어", "물받이", "커피"):
            if word in scene_text:
                on_days[word] += 1
        if any(r["기기"] == "건조기" and r["값"] == "시작" for r in rows):
            assert calendar["낮비"], folder.name
            on_days["비오는날_건조기_시작"] += 1
        for r in rows:
            if r["기기"] == "건조기" and r["값"] == "시작":
                assert sky[seconds(r["시각"]) // 3600]["날씨"] == "비", (folder.name, r)
    assert set(spans) == all_signals
    assert on_days["동일문장_연속"] == 28
    assert on_days["경기전_맥주"] == 2 and on_days["경기후_맥주"] == 6 and on_days["방문객"] == 1, on_days
    assert (on_days["경고_사용중"], on_days["경고_앞이빔"], on_days["경고_시야가림"]) == (3, 2, 1)
    assert on_days["비오는날_건조기_시작"] == on_days["건조대"] == 4
    for term in ("이불", "충전기", "노트북", "약통", "접이식", "드라마", "식기세척기", "맥주", "건조대", "비오는날_건조기_시작"):
        assert on_days[term] >= 2, (term, on_days[term])
    print(f"통과 | 연속 날짜 {len(folders)}일 | 사람 조작 {totals['사람']}건 × 301시점 | 기계 신호 {totals['기계']}건 × 151시점")
    print(f"통과 | 관찰 {totals['관찰']:,}줄 | 구간 합계 {totals['구간별_줄수_합']:,}시점 | 겹쳐 한 번만 쓴 시점 수(중복 출현분) {totals['구간별_줄수_합'] - totals['관찰']:,}")
    print("통과 | 날짜 경계·전체 구간 양 끝·4초 누락·구간 밖 행·중복·문과 운전 상태 쌍·30분 온도·시간별 날씨·날짜별 순차 입력")
    print("관찰에서 확인된 날짜 수 | " + ", ".join(f"{k} {v}일" for k,v in on_days.items()))


if __name__ == "__main__":
    main()
