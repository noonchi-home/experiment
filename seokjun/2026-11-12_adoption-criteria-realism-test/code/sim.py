"""채택 기준 현실성 시험.

설계문서/2026-11-09_가전_관찰에서_도움_규칙_만들기.md 4절의 습관 채택 기준을 코드로 옮기고,
가상의 한 사람이 12주를 사는 동안 밤마다 규칙을 다시 정해 다음 날 그 규칙대로 나서 본다.
모델을 부르지 않는다(비용 0원). 현실 정도(습관을 지키는 비율, 관찰 실수 등)는 모두 이 시험의 가정이다.

사용: python -X utf8 sim.py [사람 수(기본 200)]
      python -X utf8 sim.py 검사   → 설계 문서의 계산 예시와 같은 결과가 나오는지만 확인
"""
import json
import math
import pathlib
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy.stats import binom

DAYS = 84  # 12주, 월요일부터
WD = "월화수목금토일"
EXP = pathlib.Path(__file__).resolve().parents[1]

# 현실 정도. c: 습관인 날 실제로 하는 비율, eps: 습관이 아닌 날에도 하는 비율,
# u: 결과를 못 본 비율(계산에서 제외), m: 했는지를 반대로 잘못 본 비율,
# mt: 트리거 자체를 놓친 비율, trips: 3일짜리 외출 횟수(그동안 집에 아무 일도 없음)
LEVELS = {
    "이상적": dict(c=1.0, eps=0.0, u=0.0, m=0.0, mt=0.0, trips=0),
    "보통": dict(c=0.9, eps=0.05, u=0.1, m=0.05, mt=0.05, trips=2),
    "나쁨": dict(c=0.8, eps=0.1, u=0.2, m=0.1, mt=0.1, trips=2),
}
TRIGGERS = ["TV 켜짐", "기상", "세탁 종료", "귀가", "운동 끝"]


def every(c):
    return True


def friday(c):
    return c["요일"] == "금"


def weekday(c):
    return c["날짜 종류"] == "평일"


def rain(c):
    return c["날씨"] == "비"


def mon_wed_fri(c):
    return c["요일"] in ("월", "수", "금")


def with_guest(c):
    return c["함께 있는 사람"] == "손님"


HABITS = [  # (이름, 트리거, 습관인 날) — 진짜 습관
    ("매일 물", "TV 켜짐", every),
    ("금요일 맥주", "TV 켜짐", friday),
    ("평일 커피", "기상", weekday),
    ("비 오는 날 건조기", "세탁 종료", rain),
    ("월·수·금 간식", "TV 켜짐", mon_wed_fri),
    ("손님 오면 과자", "TV 켜짐", with_guest),
]
NOISE = [  # (이름, 트리거, 하는 비율) — 어떤 조건과도 관계없이 그냥 가끔 하는 행동. 규칙이 생기면 가짜다
    ("무작위 15% ①", "세탁 종료", 0.15), ("무작위 15% ②", "기상", 0.15),
    ("무작위 30% ①", "TV 켜짐", 0.30), ("무작위 30% ②", "운동 끝", 0.30),
    ("무작위 45% ①", "귀가", 0.45), ("무작위 45% ②", "TV 켜짐", 0.45),
    ("무작위 60% ①", "기상", 0.60), ("무작위 60% ②", "운동 끝", 0.60),
]


# ---------------------------------------------------------------- 채택 기준 (설계 문서 4절)

def adopt(G, done, item, th=0.8, ptest=True, minopp=0):
    """G: (조건 값 수, 기회 수) 참거짓, done: 기회마다 했는지, item: 조건 값마다 어느 항목인지.
    돌려주는 것: 채택한 규칙 목록. 규칙 하나 = 조건 값 번호의 묶음(빈 묶음은 조건 없는 규칙)."""
    n = int(done.size)
    if n == 0:
        return []
    k = int(done.sum())
    if k >= 4 and k / n >= th - 1e-12 and n >= minopp:  # 조건 없는 규칙: 4일 + 비율만 본다
        return [()]
    rules, rem = [], np.ones(n, bool)
    Gd = G & done
    while True:
        nb = int(rem.sum())
        if nb == 0:
            break
        base = int((done & rem).sum()) / nb      # 남은 기회 전체의 평소 비율
        p0 = max(base, 0.01)                     # 이항검정 기준 확률, 하한 0.01
        Gr, Gdr = G & rem, Gd & rem
        n1, k1 = Gr.sum(1), Gdr.sum(1)
        cands = _passing([(g,) for g in range(len(item))], n1, k1, base, p0, th, ptest)
        if not cands:                            # 단일 조건이 하나도 없을 때만 두 개 조합
            iu, ju = np.triu_indices(len(item), 1)
            keep = item[iu] != item[ju]
            iu, ju = iu[keep], ju[keep]
            N2 = Gr.astype(np.int32) @ Gr.T.astype(np.int32)
            K2 = Gdr.astype(np.int32) @ Gr.T.astype(np.int32)
            cands = _passing(list(zip(iu.tolist(), ju.tolist())), N2[iu, ju], K2[iu, ju], base, p0, th, ptest)
        if not cands:
            break
        cands.sort(key=lambda c: (-c[1], -c[2], c[0]))  # 맞춘 행동 수 → 비율 순
        gs = cands[0][0]
        rules.append(gs)
        rem &= ~np.all(G[list(gs)], axis=0)       # 이 규칙이 다루는 기회를 빼고 다시 찾는다
    return rules


def _passing(groups, n_in, k_in, base, p0, th, ptest):
    n_in, k_in = np.asarray(n_in), np.asarray(k_in)
    rate = np.where(n_in > 0, k_in / np.maximum(n_in, 1), 0.0)
    ok = (k_in >= 4) & (rate >= th - 1e-12) & (rate - base >= 0.2 - 1e-12)
    out = []
    for t in np.flatnonzero(ok):
        if ptest and binom.sf(int(k_in[t]) - 1, int(n_in[t]), p0) >= 0.001:
            continue
        out.append((groups[t], int(k_in[t]), float(rate[t])))
    return out


# ---------------------------------------------------------------- 가상의 한 사람

def make_world(rng, lv):
    weekdays = [d for d in range(DAYS) if d % 7 < 5]
    hol = {int(x) for x in rng.choice(weekdays, 3, replace=False)}  # 가상 공휴일 3일
    daytype = ["공휴일" if d in hol else ("주말" if d % 7 >= 5 else "평일") for d in range(DAYS)]
    T = np.array([[.6, .3, .1], [.35, .4, .25], [.25, .35, .4]])   # 날씨가 며칠씩 이어지게
    names = ["맑음", "흐림", "비"]
    s = [int(rng.choice(3, p=[.5, .3, .2]))]
    for _ in range(DAYS - 1):
        s.append(int(rng.choice(3, p=T[s[-1]])))
    weather = [names[i] for i in s]
    temp, e = [], 0.0
    for d in range(DAYS):                                          # 가을: 22도 → 5도, 비 오면 2도 낮게
        e = 0.6 * e + rng.normal(0, 2.4)
        temp.append(22 - 17 * d / (DAYS - 1) + e - (2 if weather[d] == "비" else 0))
    hum = [float(np.clip(55 + {"맑음": 0, "흐림": 8, "비": 25}[weather[d]] + rng.normal(0, 10), 20, 99))
           for d in range(DAYS)]
    indoor = [24 + 0.15 * (temp[d] - 15) + rng.normal(0, 0.7) for d in range(DAYS)]
    guest = [bool(rng.random() < (0.08 if daytype[d] == "평일" else 0.25)) for d in range(DAYS)]
    away = set()
    for _ in range(lv["trips"]):
        st = int(rng.integers(7, DAYS - 3))
        away |= set(range(st, st + 3))
    return dict(daytype=daytype, weather=weather, temp=temp, hum=hum, indoor=indoor, guest=guest, away=away)


def trigger_minute(name, d, w, rng):
    if d in w["away"]:
        return None
    dt = w["daytype"][d]
    if name == "TV 켜짐":
        return 22 * 60 + rng.normal(0, 25) if rng.random() < 0.9 else None
    if name == "기상":
        return 7 * 60 + rng.normal(0, 15) if dt == "평일" else 9 * 60 + rng.normal(0, 40)
    if name == "세탁 종료":
        return rng.uniform(10 * 60, 20 * 60) if rng.random() < 0.43 else None
    if name == "귀가":
        if dt == "평일":
            return 19 * 60 + rng.normal(0, 30) if rng.random() < 0.95 else None
        return 15 * 60 + rng.normal(0, 90) if rng.random() < 0.5 else None
    if name == "운동 끝":
        return 18 * 60 + rng.normal(0, 60) if rng.random() < 0.4 else None
    raise ValueError(name)


def context(w, d, minute):
    """11월 10일에 정한 조건 목록. 기온 5도, 습도 20%, 실내 온도 2도 단위(실내 온도 단위는 이 시험의 가정)."""
    slot = int(minute // 30) % 48
    return {
        "요일": WD[d % 7],
        "날짜 종류": w["daytype"][d],
        "시간대": f"{slot // 2:02d}:{slot % 2 * 30:02d}",
        "함께 있는 사람": "손님" if w["guest"][d] else "혼자",
        "날씨": w["weather"][d],
        "기온": f"{math.floor(w['temp'][d] / 5) * 5}도대",
        "습도": f"{int(w['hum'][d] // 20) * 20}%대",
        "실내 온도": f"{math.floor(w['indoor'][d] / 2) * 2}도대",
    }


class Pair:
    def __init__(self, name, trig, intent, q, w, occ, rng, lv):
        self.name, self.trig, self.noise = name, trig, intent is None
        self.days = [d for d in range(DAYS) if occ[trig][d] is not None]
        self.col = {d: i for i, d in enumerate(self.days)}
        ctx = [context(w, d, occ[trig][d]) for d in self.days]
        self.keys = sorted({(k, v) for c in ctx for k, v in c.items()})
        self.G = np.array([[c[k] == v for c in ctx] for k, v in self.keys], dtype=bool).reshape(len(self.keys), len(ctx))
        items = sorted({k for k, _ in self.keys})
        self.item = np.array([items.index(k) for k, _ in self.keys])
        nd = len(self.days)
        if self.noise:
            self.do = rng.random(nd) < q
        else:
            want = np.array([bool(intent(c)) for c in ctx], dtype=bool)
            self.do = np.where(want, rng.random(nd) < lv["c"], rng.random(nd) < lv["eps"])
        self.val = self.do ^ (rng.random(nd) < lv["m"])   # 관찰된 결과(잘못 볼 수 있음)
        self.unseen = rng.random(nd) < lv["u"]
        self.status = np.zeros(nd, np.int8)               # 0 아직, 1 기록됨, 2 계산에서 제외
        self.rules, self.changed = [], False
        self.helped = self.wrong = self.missed = 0
        self.first_help = None
        self.ever_rule = self.ever_plain = self.ever_guarded = False

    def fires(self, i):
        return any(all(self.G[g, i] for g in gs) for gs in self.rules)

    def describe(self):
        if not self.rules:
            return "규칙 없음"
        return " / ".join("조건 없음" if gs == () else " & ".join(f"{self.keys[g][0]}={self.keys[g][1]}" for g in gs)
                          for gs in self.rules)


def run_person(args):
    seed, cfg = args
    rng = np.random.default_rng(seed)
    lv = LEVELS[cfg["level"]]
    w = make_world(rng, lv)
    occ = {t: [trigger_minute(t, d, w, rng) for d in range(DAYS)] for t in TRIGGERS}
    seen = {t: [m is not None and rng.random() >= lv["mt"] for m in occ[t]] for t in TRIGGERS}
    pairs = ([Pair(n, t, f, None, w, occ, rng, lv) for n, t, f in HABITS]
             + [Pair(n, t, None, q, w, occ, rng, lv) for n, t, q in NOISE])
    warmup, react = cfg.get("warmup", 0), cfg.get("react", False)
    for d in range(DAYS):
        for p in pairs:                                   # 낮: 어젯밤 정한 규칙대로 나선다
            i = p.col.get(d)
            if i is None:
                continue
            would = bool(p.do[i])
            if not seen[p.trig][d]:                       # 트리거를 놓치면 나서지도, 기록하지도 못한다
                p.missed += would
                continue
            if d >= warmup and p.fires(i):
                if would:
                    p.helped += 1
                    p.first_help = d if p.first_help is None else p.first_help
                else:
                    p.wrong += 1
                if not react:
                    p.status[i] = 2                       # 설계대로: 로봇이 대신한 기회는 계산에서 뺀다
                elif would:
                    p.status[i], p.val[i] = 1, True       # 가정: 도움을 쓰면 '함'으로 센다
                elif rng.random() < 0.7:
                    p.status[i], p.val[i] = 1, False      # 가정: 원치 않으면 70%는 되돌린다 → '하지 않음'
                else:
                    p.status[i] = 2
            else:
                p.missed += would
                p.status[i] = 2 if p.unseen[i] else 1
            p.changed = p.changed or p.status[i] == 1
        for p in pairs:                                   # 밤: 그날까지의 기록으로 규칙을 다시 정한다
            if not p.changed:
                continue
            p.changed = False
            idx = np.flatnonzero(p.status == 1)
            p.rules = adopt(p.G[:, idx], p.val[idx], p.item, cfg["th"], cfg["ptest"], cfg.get("minopp", 0))
            p.ever_rule = p.ever_rule or bool(p.rules)
            p.ever_plain = p.ever_plain or () in p.rules
            p.ever_guarded = p.ever_guarded or any(gs != () for gs in p.rules)
    return {
        "habits": {p.name: dict(helped=p.helped, wrong=p.wrong, missed=p.missed, first_help=p.first_help,
                                final=p.describe()) for p in pairs if not p.noise},
        "noise": {p.name: dict(helped=p.helped, wrong=p.wrong, ever=p.ever_rule, ever_plain=p.ever_plain,
                               ever_guarded=p.ever_guarded, final_has=bool(p.rules), final=p.describe())
                  for p in pairs if p.noise},
    }


# ---------------------------------------------------------------- 설정과 집계

def configs():
    out = []
    for lvl in LEVELS:
        for th in (0.7, 0.8, 0.9, 1.0):
            out.append(dict(key=f"{lvl}|{th}", level=lvl, th=th, ptest=True))
        out.append(dict(key=f"{lvl}|0.8|우연검사없음", level=lvl, th=0.8, ptest=False))
    out.append(dict(key="보통|0.8|첫2주지켜보기", level="보통", th=0.8, ptest=True, warmup=14))
    out.append(dict(key="보통|0.8|조건없는규칙기회10번", level="보통", th=0.8, ptest=True, minopp=10))
    for th in (0.7, 0.8, 0.9, 1.0):
        out.append(dict(key=f"보통|{th}|반응반영(가정)", level="보통", th=th, ptest=True, react=True))
    return out


def summarize(runs):
    n = len(runs)
    hh = [sum(r["habits"][h]["helped"] for h in r["habits"]) for r in runs]
    hm = [sum(r["habits"][h]["missed"] for h in r["habits"]) for r in runs]
    wh = [sum(r["habits"][h]["wrong"] for h in r["habits"]) for r in runs]
    wn = [sum(r["noise"][x]["wrong"] for x in r["noise"]) for r in runs]
    fake = [any(r["noise"][x]["ever"] for x in r["noise"]) for r in runs]
    fake_plain = [any(r["noise"][x]["ever_plain"] for x in r["noise"]) for r in runs]
    fake_guarded = [any(r["noise"][x]["ever_guarded"] for x in r["noise"]) for r in runs]
    fake_final = [any(r["noise"][x]["final_has"] for x in r["noise"]) for r in runs]
    per = {}
    for h, *_ in HABITS:
        fh = [r["habits"][h]["first_help"] for r in runs]
        got = [d // 7 + 1 for d in fh if d is not None]
        helped = sum(r["habits"][h]["helped"] for r in runs)
        missed = sum(r["habits"][h]["missed"] for r in runs)
        per[h] = dict(
            처음도운주_중앙값=float(np.median(got)) if got else None,
            못도운사람비율=round(100 * (n - len(got)) / n, 1),
            도운비율=round(100 * helped / max(helped + missed, 1), 1),
            잘못나섬_사람당=round(sum(r["habits"][h]["wrong"] for r in runs) / n, 2),
            마지막규칙_상위=Counter(r["habits"][h]["final"] for r in runs).most_common(3),
        )
    noise = {x: dict(규칙생긴사람비율=round(100 * sum(r["noise"][x]["ever"] for r in runs) / n, 1),
                     잘못나섬_사람당=round(sum(r["noise"][x]["wrong"] for r in runs) / n, 2))
             for x, *_ in NOISE}
    return dict(
        사람수=n,
        도운횟수_사람당=round(sum(hh) / n, 1),
        도운비율=round(100 * sum(hh) / max(sum(hh) + sum(hm), 1), 1),
        잘못나섬_습관규칙_사람당=round(sum(wh) / n, 1),
        잘못나섬_가짜규칙_사람당=round(sum(wn) / n, 1),
        잘못나섬_전체_사람당=round((sum(wh) + sum(wn)) / n, 1),
        가짜규칙생긴사람비율=round(100 * sum(fake) / n, 1),
        조건없는가짜규칙생긴사람비율=round(100 * sum(fake_plain) / n, 1),
        조건붙은가짜규칙생긴사람비율=round(100 * sum(fake_guarded) / n, 1),
        가짜규칙12주째남은사람비율=round(100 * sum(fake_final) / n, 1),
        습관별=per,
        무작위행동별=noise,
    )


def self_check():
    """설계 문서의 계산 예시와 같은 답이 나오는지 확인한다."""
    # 4절 예시: 28일 모두 TV, 금요일 4일에만 맥주 → 조건 없는 규칙 탈락, '요일=금' 채택, 검정값 약 0.000416
    keys = [("요일", x) for x in WD] + [("시간대", "23:00")]
    days = list(range(28))
    G = np.array([[WD[d % 7] == v if k == "요일" else True for d in days] for k, v in keys], dtype=bool)
    done = np.array([d % 7 == 4 for d in days])
    item = np.array([0] * 7 + [1])
    rules = adopt(G, done, item)
    assert rules == [(4,)], rules
    p = binom.sf(3, 4, 4 / 28)
    assert abs(p - 0.000416) < 0.000001, p
    # 구현계획서 예시: 조건 없이 5일 중 4일 → 채택
    G5 = np.ones((1, 5), bool)
    assert adopt(G5, np.array([1, 1, 1, 1, 0], bool), np.array([0])) == [()]
    # 4번 중 3번(75%)은 조건 없이 탈락
    assert adopt(np.ones((1, 4), bool), np.array([1, 1, 1, 0], bool), np.array([0])) == []
    print("검사 통과: 금요일 예시 '요일=금' 채택, 검정값", round(p, 6), "/ 5일 중 4일 채택 / 4일 중 3일 탈락")


def write_report(res, n, secs):
    def row(key):
        s = res[key]
        return s
    L = []
    L.append("# 채택 기준 현실성 시험 결과\n")
    L.append(f"가상의 한 사람이 12주를 사는 기록을 설정마다 {n}명씩 만들어, 밤마다 규칙을 정하고 다음 날 그 규칙대로 나서게 했다. "
             f"모델은 부르지 않았다(비용 0원). 실행 시간 {secs:.0f}초.\n")
    L.append("숫자는 사람 한 명이 12주 동안 겪는 평균이다. '도운 횟수'는 사람이 원래 했을 일을 로봇이 먼저 한 횟수, "
             "'잘못 나섬'은 사람이 원래는 안 했을 때 로봇이 나선 횟수, '도운 비율'은 사람이 습관 행동을 한 날 중 로봇이 먼저 한 비율이다.\n")
    L.append("## 1. 현실 정도와 비율 기준에 따라\n")
    L.append("| 현실 정도 | 비율 기준 | 도운 횟수 | 도운 비율 | 잘못 나섬(진짜 습관) | 잘못 나섬(가짜 규칙) | 가짜 규칙이 한 번이라도 생긴 사람 | 12주째 가짜 규칙이 남은 사람 |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for lvl in LEVELS:
        for th in (0.7, 0.8, 0.9, 1.0):
            s = res[f"{lvl}|{th}"]
            L.append(f"| {lvl} | {int(th*100)}% | {s['도운횟수_사람당']} | {s['도운비율']}% | {s['잘못나섬_습관규칙_사람당']} | "
                     f"{s['잘못나섬_가짜규칙_사람당']} | {s['가짜규칙생긴사람비율']}% | {s['가짜규칙12주째남은사람비율']}% |")
    L.append("\n## 2. 우연 검사(p < 0.001)가 있을 때와 없을 때 (비율 기준 80%)\n")
    L.append("우연 검사는 조건을 붙인 규칙에만 적용된다. 그래서 가짜 규칙을 조건 붙은 것과 조건 없는 것으로 나눠 셌다.\n")
    L.append("| 현실 정도 | 우연 검사 | 조건 붙은 가짜 규칙이 생긴 사람 | 조건 없는 가짜 규칙이 생긴 사람 | 잘못 나섬(가짜 규칙) | 도운 횟수 |")
    L.append("|---|---|---:|---:|---:|---:|")
    for lvl in LEVELS:
        for k, lab in ((f"{lvl}|0.8", "있음"), (f"{lvl}|0.8|우연검사없음", "없음")):
            s = res[k]
            L.append(f"| {lvl} | {lab} | {s['조건붙은가짜규칙생긴사람비율']}% | {s['조건없는가짜규칙생긴사람비율']}% | "
                     f"{s['잘못나섬_가짜규칙_사람당']} | {s['도운횟수_사람당']} |")
    L.append("\n## 3. 습관별 (현실 정도 보통, 비율 기준 80%, 설계대로)\n")
    L.append("| 습관 | 처음 도운 주(중앙값) | 12주 안에 한 번도 못 도운 사람 | 도운 비율 | 잘못 나섬 | 12주째 규칙(가장 많은 것) |")
    L.append("|---|---:|---:|---:|---:|---|")
    s = res["보통|0.8"]
    for h, v in s["습관별"].items():
        top = v["마지막규칙_상위"][0]
        L.append(f"| {h} | {v['처음도운주_중앙값']} | {v['못도운사람비율']}% | {v['도운비율']}% | {v['잘못나섬_사람당']} | "
                 f"{top[0]} ({round(100*top[1]/n)}%) |")
    L.append("\n| 무작위 행동(규칙이 생기면 가짜) | 규칙이 생긴 사람 | 잘못 나섬 |")
    L.append("|---|---:|---:|")
    for x, v in s["무작위행동별"].items():
        L.append(f"| {x} | {v['규칙생긴사람비율']}% | {v['잘못나섬_사람당']} |")
    L.append("\n## 4. 고치는 방법 시험 (현실 정도 보통, 비율 기준 80%)\n")
    L.append("| 방법 | 도운 횟수 | 도운 비율 | 잘못 나섬(진짜 습관) | 잘못 나섬(가짜 규칙) | 12주째 가짜 규칙이 남은 사람 |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for k, lab in (("보통|0.8", "설계대로(로봇이 나선 날은 계산에서 뺌)"), ("보통|0.8|첫2주지켜보기", "첫 2주는 나서지 않고 지켜보기만"),
                   ("보통|0.8|조건없는규칙기회10번", "조건 없는 규칙도 기회 10번 이상 쌓인 뒤에만"),
                   ("보통|0.8|반응반영(가정)", "사람 반응을 계산에 넣기(쓰면 '함', 되돌리면 '하지 않음')")):
        s = res[k]
        L.append(f"| {lab} | {s['도운횟수_사람당']} | {s['도운비율']}% | {s['잘못나섬_습관규칙_사람당']} | "
                 f"{s['잘못나섬_가짜규칙_사람당']} | {s['가짜규칙12주째남은사람비율']}% |")
    L.append("\n## 5. 사람 반응을 계산에 넣었을 때의 비율 기준 비교 (현실 정도 보통)\n")
    L.append("| 비율 기준 | 도운 횟수 | 도운 비율 | 잘못 나섬(진짜 습관) | 잘못 나섬(가짜 규칙) | 12주째 가짜 규칙이 남은 사람 |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for th in (0.7, 0.8, 0.9, 1.0):
        s = res[f"보통|{th}|반응반영(가정)"]
        L.append(f"| {int(th*100)}% | {s['도운횟수_사람당']} | {s['도운비율']}% | {s['잘못나섬_습관규칙_사람당']} | "
                 f"{s['잘못나섬_가짜규칙_사람당']} | {s['가짜규칙12주째남은사람비율']}% |")
    L.append("\n## 이 시험의 가정\n")
    L.append("- 현실 정도: 이상적(습관을 늘 지키고 관찰 실수 없음), 보통(습관인 날 90% 실행, 아닌 날 5% 실행, 결과 못 봄 10%, "
             "반대로 잘못 봄 5%, 트리거 놓침 5%, 3일 외출 2번), 나쁨(80%, 10%, 20%, 10%, 10%, 외출 2번). 모두 정한 값이며 측정값이 아니다.")
    L.append("- 습관 6개(매일, 금요일, 평일, 비 오는 날, 월·수·금, 손님 올 때)와 조건과 무관한 무작위 행동 8개(15·30·45·60% 각 2개). "
             "트리거는 하루에 한 번이며, 트리거마다 발생 확률과 시각을 정해 두었다.")
    L.append("- 조건 목록은 11월 10일 결정(요일, 평일·주말·공휴일, 30분 시간대, 함께 있는 사람, 날씨, 기온 5도, 습도 20%, 실내 온도). "
             "실내 온도 단위 2도와 공휴일 3일은 이 시험의 가정이다. 날씨는 하루 하나로 두었다.")
    L.append("- 채택 기준은 설계 문서 4절 그대로다. 조건 없는 규칙은 서로 다른 날 4일·비율 기준, 조건 붙인 규칙은 여기에 20%p 상승과 "
             "단측 이항검정 p < 0.001(기준 확률은 남은 기회의 평소 비율, 하한 0.01). 조건은 최대 두 개, 단일 조건을 먼저 본다. "
             "고른 규칙이 다루는 기회를 빼고 다시 찾는다. 밤마다 그날까지의 기록 전체로 다시 정한다.")
    L.append("- '설계대로'는 로봇이 나선 날을 계산에서 뺀다(설계 문서 5절). '반응 반영'은 설계 문서에 숫자가 없어 이 시험이 정한 가정이다.")
    L.append("- 시각 후보(사건이 아니라 시각을 트리거로 쓰는 경우), 이미 함, 사람이 로봇보다 먼저 한 경우는 넣지 않았다.")
    (EXP / "결과표.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "검사":
        self_check()
        return
    self_check()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    cfgs = configs()
    tasks = [(seed, c) for c in cfgs for seed in range(n)]
    t0 = time.time()
    with ProcessPoolExecutor() as ex:
        outs = list(ex.map(run_person, tasks, chunksize=10))
    secs = time.time() - t0
    res = {}
    for ci, c in enumerate(cfgs):
        res[c["key"]] = summarize(outs[ci * n:(ci + 1) * n])
    (EXP / "data").mkdir(exist_ok=True)
    (EXP / "data" / "결과.json").write_text(json.dumps(dict(사람수=n, 설정=cfgs, 결과=res), ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    write_report(res, n, secs)
    print(f"끝: {len(tasks)}번 실행, {secs:.0f}초 → {EXP / '결과표.md'}")


if __name__ == "__main__":
    main()
