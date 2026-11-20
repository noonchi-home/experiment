"""배포된 정답 파일을 원본과 직접 대조한다. 정답 생성기나 학습 함수를 실행하지 않는다."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
from functools import lru_cache
from math import comb, isclose
from pathlib import Path

from source import DEFAULT_INPUT, ROOT


DATES = [(date(2026, 10, 12) + timedelta(days=n)).isoformat() for n in range(28)]
RESULTS = ("함", "하지 않음", "이미 함", "관찰 불가")


def insist(ok, *context):
    if not ok:
        raise ValueError("검사 실패 " + repr(context))


def lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8-sig").splitlines() if x]


def seconds(stamp):
    h, m, s = map(int, stamp.split(":"))
    return h * 3600 + m * 60 + s


def tomorrow(stamp, delta=1):
    return (date.fromisoformat(stamp) + timedelta(days=delta)).isoformat()


def originals(data, manifests, signal_index):
    files = {row["날짜"]: row for row in manifests}
    insist(len(files) == len(manifests) == 28 and set(files) == set(DATES), "원본 지문 날짜")
    expected_files = {"weather.json", "실내온도.jsonl", "가전신호.jsonl", "관찰.txt"}
    obs, signals, by_time = {}, {}, defaultdict(list)
    for dt in DATES:
        folder = data / dt
        for name in expected_files:
            checksum = hashlib.sha256((folder / name).read_bytes()).hexdigest()
            insist(files[dt]["원본SHA256"].get(name) == checksum, dt, name, "원본 SHA256")
        frames = {}
        for number, row in enumerate((folder / "관찰.txt").read_text(encoding="utf-8").splitlines(), 1):
            stamp, place, caption = row.split(" / ", 2)
            insist(stamp not in frames, dt, stamp, "중복 관찰 시각")
            frames[stamp] = (number, place, caption)
        signal_rows = lines(folder / "가전신호.jsonl")
        for row in signal_rows:
            key = row["신호ID"]
            insist(key not in signals, "중복 신호", key)
            signals[key] = (dt, row)
            by_time[dt, row["시각"]].append(key)
        insist(files[dt]["신호"] == len(signal_rows) and files[dt]["관찰"] == len(frames), dt, "건수")
        obs[dt] = frames
    insist(len(signal_index) == len(signals) == 861 and sum(map(len, obs.values())) == 86995, "원본 규모")
    seen = set()
    for indexed in signal_index:
        key = indexed["신호ID"]
        dt, raw = signals[key]
        insist(key not in seen and indexed["날짜"] == dt and all(indexed.get(k) == v for k, v in raw.items()),
                "원본과 신호 색인", key)
        seen.add(key)
    return obs, by_time


def evidence_at(dt, ev, obs, by_time, allow_clock=False):
    stamp = ev["시각"]
    raw = obs[dt].get(stamp)
    if raw:
        insist((ev.get("관찰줄"), ev.get("위치"), ev.get("관찰")) == raw, "원문·시각·줄", dt, stamp)
    else:
        insist(not {"관찰줄", "위치", "관찰"}.intersection(ev), dt, stamp, "없는 관찰을 인용")
    ids = by_time.get((dt, stamp), [])
    insist(ev.get("신호ID", []) == ids, dt, stamp, "동시각 신호 식별자")
    insist(allow_clock or raw or ids, dt, stamp, "근거 없는 시각")


def guard_reader(data, obs, signal_index):
    skies = {dt: json.loads((data / dt / "weather.json").read_text(encoding="utf-8")) for dt in DATES}
    temps = {dt: lines(data / dt / "실내온도.jsonl") for dt in DATES}
    channels, visibility = [], defaultdict(list)
    for r in signal_index:
        if r["기기"] == "TV":
            channel = r["값"] if r["항목"] == "채널" else "모름"
            channels.append((r["날짜"], r["시각"], channel))
    channels.sort()
    for dt, frames in obs.items():
        for stamp, (_, _, txt) in frames.items():
            if "방문객" in txt:
                visibility[dt].append((seconds(stamp), "방문객 있음"))
            if "현관문이 닫히고 현관 안쪽에는 사용자만" in txt:
                visibility[dt].append((seconds(stamp), "모름"))

    @lru_cache(maxsize=None)
    def read(dt, stamp):
        t = seconds(stamp)
        wi = date.fromisoformat(dt).weekday()
        i = bisect_right(channels, (dt, stamp, chr(0x10ffff))) - 1
        j = bisect_right(visibility[dt], (t, chr(0x10ffff))) - 1
        guest = visibility[dt][j][1] if j >= 0 and t - visibility[dt][j][0] <= 1800 else "모름"
        degrees = int(temps[dt][t // 1800]["값_C"]) // 2 * 2
        return {"요일": "월화수목금토일"[wi], "날짜종류": "주말" if wi >= 5 else "평일",
                "시간대": stamp[:2] + "시대", "날씨": "비" if skies[dt][t//3600]["날씨"] == "비" else "비 없음",
                "관찰위치": obs[dt][stamp][1] if stamp in obs[dt] else "모름",
                "실내온도구간": f"{degrees}도 이상 {degrees+2}도 미만", "채널": channels[i][2] if i >= 0 else "모름",
                "동석자": guest}
    return read


def stats(samples):
    counts = Counter(r["사후결과"] for r in samples)
    dates = sorted(set(r["날짜"] for r in samples if r["사후결과"] == "함"))
    n = counts["함"] + counts["하지 않음"]
    return {"기회": len(samples), **{k: counts[k] for k in RESULTS}, "일치날짜수": len(dates),
            "일치날짜": dates, "분모": n, "비율": counts["함"] / n if n else None}


def check_guards(night, history, route="사건"):
    active = [v["조건"] for v in night["활성"] if v["경로"] == route and v["조건"]]
    tests = night["조건검사"] if route == "사건" else night["시각검사"].get("조건검사", [])
    for audit in tests:
        stage = audit["탐색차수"]
        cond = audit["조건"]
        same = lambda e, g: all(e["조건"].get(key) == val for key, val in g.items())
        available = [e for e in history if not any(same(e, g) for g in active[:stage-1])]
        base = stats(available)
        part = stats([e for e in available if same(e, cond)])
        insist(audit["근거"] == part, night["날짜"], night["규칙ID"], "조건 부분집합", cond)
        p = max(.01, base["비율"])
        n, k = part["분모"], part["함"]
        # 누적이항분포를 아래 꼬리로 뺄 때 생기는 소수 오차를 피하기 위해 정확한 정수 비율에서 직접 합산한다.
        numerator, denominator = (1, 100) if base["비율"] < .01 else (base["함"], base["분모"])
        tail = sum(comb(n, i) * numerator**i * (denominator-numerator)**(n-i)
                   for i in range(k, n+1)) / denominator**n
        gain = part["비율"] - base["비율"]
        passes = part["일치날짜수"] >= 4 and 5*k >= 4*n and gain >= .2-1e-12 and tail < .001
        insist(isclose(tail, audit["단측p"], abs_tol=1e-13) and isclose(gain, audit["상승폭"], abs_tol=1e-13)
                and audit["통과"] == passes and isclose(p, max(.01, audit["잔여기본비율"])),
                night["날짜"], night["규칙ID"], "이항검정·상승폭", cond)


def night_checks(nights, events, read_guards):
    grouped = defaultdict(list)
    for e in events:
        grouped[e["날짜"], e["규칙ID"]].append(e)
    index = {(n["날짜"], n["규칙ID"]): n for n in nights}
    rules = {r["규칙ID"] for r in nights if r["날짜"] == DATES[-1]}
    insist(len(index) == len(nights) == 28 * len(rules) and len(rules) >= 28, "밤별 후보 규모")
    histories = defaultdict(list)
    for dt in DATES:
        for key in rules:
            night = index[dt, key]
            insist(night["다음적용일"] == tomorrow(dt), dt, key, "적용일")
            first = None
            for e in sorted(grouped[dt, key], key=lambda row: row["기회시각"]):
                stamp = e["기회시각"]
                if first is None or seconds(stamp) >= seconds(first) + 3600:
                    first = stamp
                    histories[key].append(e)
                    group = "첫 기회"
                else:
                    group = "60분 안의 반복"
                insist((e["분류"], e["대표시각"]) == (group, first), dt, key, stamp, "60분 묶음")
            actual = stats(histories[key])
            insist(actual == night["누적근거"], dt, key, "그날까지의 누적 기회", actual)
            check_guards(night, histories[key])
            info = night["시각검사"]
            if info:
                results = info["날짜별결과"]
                insist(set(results) == {d for d in DATES if d <= dt}, dt, key, "시각검사일")
                descriptors = [{"날짜": d, "사후결과": r, "조건": read_guards(d, info["시각"])} for d, r in results.items()]
                time_stats = stats(descriptors)
                insist(time_stats == info["근거"], dt, key, "시각 후보 산술")
                check_guards(night, descriptors, "시각")
            previous = index.get((tomorrow(dt, -1), key), {})
            for r in night["활성"]:
                if r in previous.get("활성", []):
                    continue
                if night["종류"] == "고정안전":
                    continue
                if night["종류"] == "기기필수":
                    insist(actual["함"] > 0, dt, key, "관찰 전 기기 관계 채택")
                elif r["조건"]:
                    tests = night["조건검사"] if r["경로"] == "사건" else info["조건검사"]
                    insist(any(c["조건"] == r["조건"] and c["통과"] for c in tests),
                            dt, key, "조건 규칙 채택 근거")
                else:
                    s = info["근거"] if r["경로"] == "시각" else actual
                    insist(s["일치날짜수"] >= 4 and s["함"]*5 >= s["분모"]*4,
                            dt, key, "채택 기준 미달", s)
    for key, guard in (("wet_to_dryer", "비"), ("wet_to_rack", "비 없음")):
        night = index[DATES[-1], key]
        test = next(s for s in night["조건검사"] if s["조건"].get("날씨") == guard)
        s = night["누적근거"]
        insist((s["함"], s["분모"]) == (4, 8) and test["단측p"] == .0625 and not test["통과"],
                key, "날씨에 따른 건조 방법 4/8 → 4/4")
    return index


def decision_checks(decisions, events, nights, obs, by_time, read_guards):
    event_lookup = {(e["날짜"], e["규칙ID"], e["기회시각"]): e for e in events}
    multi = defaultdict(list)
    unique = set()
    decision_at = defaultdict(list)
    labels = {"가능": "실행", "확인필요": "대기", "위험": "대기", "선행": "취소", "불필요": "취소"}
    for r in decisions:
        dt, t, action = r["날짜"], r["시각"], r["행동"]
        insist(dt in DATES and r["전날밤"] == tomorrow(dt, -1) and t == r["근거"]["시각"], dt, t, "판단 경계")
        key = (dt, t, action)
        insist(key not in unique, "한 행동 중복", key)
        unique.add(key)
        evidence_at(dt, r["근거"], obs, by_time, allow_clock=all(v["경로"] == "시각" for v in r["세부"]))
        insist(sorted({p["규칙ID"] for p in r["세부"]}) == r["규칙ID"], dt, t, "결정의 후보")
        statuses = []
        for v in r["세부"]:
            rid, tr, route = v["규칙ID"], v["기회시각"], v["경로"]
            prior = nights.get((r["전날밤"], rid))
            kind = nights[dt, rid]["종류"]
            insist(t >= tr, dt, t, rid, tr, "사건 전 판단")
            if route == "사건":
                ev = event_lookup[dt, rid, tr]
                active = kind == "고정안전" or (prior and any(a["경로"] == route and
                         all(ev["조건"].get(g) == val for g, val in a["조건"].items()) for a in prior["활성"]))
                active = active and ev["분류"] == "첫 기회"
            else:
                candidates = [a for a in (prior or {}).get("활성", []) if a["경로"] == "시각" and a["시각"] == tr]
                insist(candidates, dt, t, rid, "전날 채택된 시각 없음")
                available = read_guards(dt, tr)
                active = any(all(available.get(k) == v for k, v in a["조건"].items()) for a in candidates)
            expected = labels[v["현재확인"]] if active else "미개입"
            insist(v["판정"] == expected, dt, t, rid, "전날 결정으로 재생", expected, v["판정"])
            statuses.append((expected, v["현재확인"]))
            multi[dt, rid, route, tr].append((t, expected))
        best = ("대기" if ("대기", "위험") in statuses else
                next(s for s in ("취소", "실행", "대기", "미개입") if any(s == p for p, _ in statuses)))
        insist(r["예상판정"] == best, dt, t, action, "공동 행동 충돌 해결")
        decision_at[dt, t].append({"행동": action, "판정": best})
    for k, seq in multi.items():
        seq.sort()
        insist(seq[0][0] == k[-1] and all(label == "대기" for _, label in seq[:-1]), k, "집행 종료 뒤 판단", seq)
    for e in events:
        group = (e["날짜"], e["규칙ID"], "사건", e["기회시각"])
        insist(group in multi, "채점에서 사라진 사건", group)
    insist(set(row["예상판정"] for row in decisions) == {"실행", "대기", "취소", "미개입"}, "판정 종류")
    return decision_at


def scene_examples(decisions, signal_index, obs, nights, events):
    typed = defaultdict(set)
    for s in signal_index:
        typed[s["기기"], s["항목"], s["값"]].add((s["날짜"], s["시각"]))
    actual_triggers = defaultdict(set)
    for e in events:
        actual_triggers[e["규칙ID"]].add((e["날짜"], e["기회시각"]))
    for rid, tag in {
        "wash_unload": ("세탁기", "운전", "완료"), "dry_unload": ("건조기", "운전", "완료"),
        "fridge_warning": ("냉장고", "문열림경고", "발생"), "workout_water": ("스마트 스피커", "타이머", "종료"),
        "print_pickup": ("프린터", "복사", "완료"), "pm_clean": ("식기세척기", "운전", "완료"),
        "pm_beer_power": ("TV", "전원", "켜짐"), "am_bedding": ("침실 조명", "전원", "켜짐"),
        "am_alarm": ("스마트 스피커", "생활 알림", "울림"),
    }.items():
        insist(actual_triggers[rid] == typed[tag], rid, "원본 신호에서 직접 찾은 사건 100%")
    all_channels = {(r["날짜"], r["시각"]) for r in signal_index if (r["기기"], r["항목"]) == ("TV", "채널")}
    insist(actual_triggers["pm_beer_channel"] == all_channels, "모든 원본 채널 선택")
    found = {(r["날짜"], r["시각"], k): r["예상판정"] for r in decisions for k in r["규칙ID"]}
    counts = Counter()
    for e in events:
        dt, t, key = e["날짜"], e["기회시각"], e["규칙ID"]
        if key == "fridge_warning":
            raw = obs[dt][t][2]
            expected = "실행" if "그 앞에는 사람이 없다" in raw else "대기"
            insist(found[dt, t, key] == expected, dt, t, key, "냉장고 경고 때 직접 보인 상황")
            counts[expected] += 1
            if expected == "대기":
                closes = [v for v in e["근거"] if v["시각"] > t and "문을 끝까지 밀어 닫는다" in v.get("관찰", "")]
                insist(len(closes) == 1 and found[dt, closes[0]["시각"], key] == "취소", dt, t, "자연 선행 취소")
        if key == "wash_unload":
            # 세탁물이 든 상태에서 처음으로 완료 알림을 관찰한 날은 낮 실행 전이다.
            expected = "미개입" if dt == "2026-10-14" else "실행"
            insist(found[dt, t, key] == expected, dt, t, "세탁 완료 관계의 하루 경계")
        if key == "pm_guest":
            insist(dt == "2026-10-31" and found[dt, t, key] == "미개입", "손님 장면", dt, t)
    insist(counts == {"실행": 2, "대기": 4}, "확인·사용 중·가림", counts)
    sports = nights[DATES[-1], "pm_beer_channel"]
    insist(any(r["조건"] == {"채널": "채널 37"} for r in sports["활성"]), "월·금만으로 맥주 규칙 확정")
    sports_checks = [r for r in decisions if r["날짜"] == "2026-11-06" and "pm_beer_channel" in r["규칙ID"]]
    insist(any(r["예상판정"] == "대기" for r in sports_checks) and any(r["예상판정"] == "취소" for r in sports_checks),
            "11월 6일 스포츠 채널에서 재고 확인과 선행 취소")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--answers", type=Path, default=ROOT / "채점자료")
    args = parser.parse_args()
    read = lambda f: lines(args.answers / f)
    nights, events = read("밤별규칙.jsonl"), read("원본근거와기회.jsonl")
    decisions, signal_index = read("시각별판단.jsonl"), read("전체신호색인.jsonl")
    obs, by_time = originals(args.input, read("원본지문.jsonl"), signal_index)
    read_guards = guard_reader(args.input, obs, signal_index)
    event_refs = defaultdict(set)
    for e in events:
        dt, t = e["날짜"], e["기회시각"]
        insist(dt in DATES and any(p["시각"] == t for p in e["근거"]), dt, t, "기회시각 근거")
        actual = read_guards(dt, t)
        insist(all(e["조건"].get(k) == v for k, v in actual.items()), dt, t, "기회 시점의 원본 사실과 조건", actual, e["조건"])
        for reference in e["근거"]:
            evidence_at(dt, reference, obs, by_time)
            event_refs[dt, reference["시각"]].add(e["규칙ID"])
    indexed = night_checks(nights, events, read_guards)
    judged = decision_checks(decisions, events, indexed, obs, by_time, read_guards)
    for signal in signal_index:
        key = (signal["날짜"], signal["시각"])
        insist(signal["동시각판정"] == judged[key] and signal["근거로참조한규칙"] == sorted(event_refs[key]),
                signal["신호ID"], "모든 가전 신호에서 정답으로의 역참조")
    scene_examples(decisions, signal_index, obs, indexed, events)
    print(f"통과 | 28일·원본 112개 SHA256·가전 신호 {len(signal_index)}건·관찰 86,995줄")
    print(f"통과 | 원본 기회 {len(events)}건 인용 시각·줄·문장, 밤별 누적 규칙 {len(nights)}건과 조건 검정 독립 재계산")
    print(f"통과 | 낮 판단 {len(decisions)}건 전날 버전·같은 시각 중복·실행/대기/취소/미개입, 원본 신호 역참조")
    print("통과 | 날씨 조건 4/4, 기준 4/8, 단측 p=.0625 | 냉장고 경고 6건 | 세탁·스포츠·손님 경계 | 29일째 가상 판단 없음")


if __name__ == "__main__":
    main()
