"""한 사람의 생활을 먼저 구성하고 가전 신호가 덮는 시각에서만 카메라 기록을 꺼낸다."""
from bisect import bisect_right
from datetime import date, timedelta
from math import cos, pi, sin
from pathlib import Path
import json
import random

import morning
import daytime
import evening


ROOT = Path(__file__).resolve().parent.parent
START = date(2026, 10, 12)
RAIN = {2, 5, 7, 10, 12, 13, 17, 20, 23, 25, 27}
SEED = 20261110


def clock(t):
    return f"{t // 3600:02}:{t // 60 % 60:02}:{t % 60:02}"


def dump_lines(path, records):
    with path.open("w", encoding="utf-8", newline="\n") as out:
        for record in records:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")


def check_time(t):
    if not isinstance(t, int) or t % 4 or not 0 <= t < 86400:
        raise ValueError(f"4초 시계 밖 시각 {t}")


class Day:
    def __init__(self, n):
        self.n = n
        self.date = START + timedelta(days=n - 1)
        self.work = "휴일" if self.date.weekday() >= 5 else "출근"
        if n in (3, 10, 17, 24):
            self.work = "재택"
        if n in (12, 23):
            self.work = "휴가"
        self.guest = n == 20
        self.meal_out = n in (4, 14, 25)
        self.clean_dishes = False
        self.rain = n in RAIN
        self.rng = random.Random(SEED + n)
        self.views = {0: ("거실", "충전대 앞 거실 바닥과 닫힌 방문이 보인다.")}
        self.signals = []
        self.notes = []

    def see(self, t, location, sentence):
        check_time(t)
        if t in self.views and self.views[t] != (location, sentence):
            raise ValueError(f"{self.date} {clock(t)} 중복 장면 {self.views[t]} / {sentence}")
        if not location or not sentence or "\n" in sentence or " / " in sentence:
            raise ValueError(f"관찰 형식 오류 {sentence}")
        self.views[t] = (location, sentence)

    def signal(self, t, actor, device, event, value):
        check_time(t)
        if actor not in ("사람", "기계") or not all((device, event, value)):
            raise ValueError(f"신호 형식 오류 {t} {actor} {device} {event} {value}")
        self.signals.append((t, actor, device, event, value))

    def note(self, t, text):
        check_time(t)
        self.notes.append((t, text))


def write_environment(day, folder):
    # 해당 시각의 합성 날씨 보고값. 미래 예보는 재생기에 전달하지 않는다.
    hourly = []
    rng = random.Random(SEED * 10 + day.n)
    daily_bias = 2.1 * sin(day.n * 0.57) + rng.uniform(-0.45, 0.45)
    rain_start, rain_stop = rng.randint(6, 10), rng.randint(21, 23)
    for hour in range(24):
        raining = day.rain and rain_start <= hour < rain_stop
        sky = "비" if raining else ("흐림" if day.rain else ("구름조금" if (hour // 5 + day.n) % 4 == 0 else "맑음"))
        degrees = 15.1 - (day.n - 1) * 0.16 + daily_bias + 4.2 * cos((hour - 15) * pi / 12)
        hourly.append({"시각": clock(hour * 3600), "날씨": sky, "외기온_C": round(degrees - (1.3 if raining else 0), 1)})
    (folder / "weather.json").write_text(json.dumps(hourly, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temperatures = []
    for half in range(48):
        hour = half / 2
        degrees = 21.8 + 0.32 * daily_bias + 1.2 * cos((hour - 16) * pi / 12) + rng.uniform(-0.09, 0.09)
        temperatures.append({"시각": clock(half * 1800), "기기": "에어컨", "항목": "현재온도", "값_C": round(degrees, 1)})
    dump_lines(folder / "실내온도.jsonl", temperatures)


def export_day(day, review):
    date_string = day.date.isoformat()
    folder = ROOT / "일별입력" / date_string
    folder.mkdir(parents=True, exist_ok=True)
    write_environment(day, folder)
    rows, windows, covered = [], [], set()
    if len(day.signals) != len(set(day.signals)):
        raise ValueError(f"{day.date} 동일 신호 중복")
    for index, (t, actor, device, event, value) in enumerate(sorted(day.signals, key=lambda s: s[0]), 1):
        identifier = f"{date_string}-{index:03}"
        start = t - 600 if actor == "사람" else t
        end = t + 600
        if start < 0 or end >= 86400:
            raise ValueError("생활일 경계를 넘는 수집 구간")
        covered.update(range(start, end + 1, 4))
        rows.append({"신호ID": identifier, "시각": clock(t), "주체": actor, "기기": device, "항목": event, "값": value})
        windows.append({"날짜": date_string, "신호ID": identifier, "시작": clock(start), "끝": clock(end), "관찰수": (end - start) // 4 + 1})
    dump_lines(folder / "가전신호.jsonl", rows)
    ticks = sorted(day.views)
    with (folder / "관찰.txt").open("w", encoding="utf-8", newline="\n") as out:
        for t in sorted(covered):
            location, sentence = day.views[ticks[bisect_right(ticks, t) - 1]]
            out.write(f"{clock(t)} / {location} / {sentence}\n")
    notes = [{"시각": clock(t), "내용": s} for t, s in sorted(day.notes)]
    review.append({"날짜": date_string, "요일": "월화수목금토일"[day.date.weekday()], "생활설정": day.work,
                   "낮비": day.rain, "저녁손님": day.guest, "외식설정": day.meal_out,
                   "가전신호수": len(rows), "관찰줄수": len(covered), "작성자메모": notes})
    return windows


def main():
    review, all_windows = [], []
    output = ROOT / "검토용"
    output.mkdir(parents=True, exist_ok=True)
    clean_dishes = False
    for n in range(1, 29):
        day = Day(n)
        day.clean_dishes = clean_dishes
        for part, module in enumerate((morning, daytime, evening)):
            day.rng = random.Random((SEED + n) * 10 + part)
            module.build(day)
        if not day.meal_out:
            clean_dishes = any(device == "식기세척기" and event == "운전" and value == "완료"
                               for _, _, device, event, value in day.signals)
        all_windows.extend(export_day(day, review))
    dump_lines(output / "수집구간.jsonl", all_windows)
    dump_lines(output / "날짜별설정.jsonl", review)
    signals = sum(d["가전신호수"] for d in review)
    frames = sum(d["관찰줄수"] for d in review)
    print(f"생성한 날짜 {len(review)}일, 가전 신호 {signals}건, 관찰 {frames}줄")


if __name__ == "__main__":
    main()
