"""누적 기회에만 적용하는 평가자용 채택 산술. 실제 학습기와 독립이다."""
from collections import Counter
from itertools import combinations
from math import comb
import re

from source import COMMON_GUARDS, clock


def group_first(rows):
    kept, repeated = [], []
    first = {}
    for row in sorted(rows, key=lambda r: (r["t"], r["id"])):
        key = row["id"]
        if key in first and row["t"] - first[key]["t"] < 3600:
            repeated.append((row, first[key]["t"]))
        else:
            kept.append(row)
            first[key] = row
    return kept, repeated


def stats(rows):
    counts = Counter(r["result"] for r in rows)
    k = counts["함"]
    total = k + counts["하지 않음"]
    dates = sorted({r["date"] for r in rows if r["result"] == "함"})
    return {"기회": len(rows), "함": k, "하지 않음": counts["하지 않음"], "이미 함": counts["이미 함"],
            "관찰 불가": counts["관찰 불가"], "일치날짜수": len(dates), "일치날짜": dates,
            "분모": total, "비율": k / total if total else None}


def enough(s):
    return s["일치날짜수"] >= 4 and s["분모"] > 0 and 5 * s["함"] >= 4 * s["분모"]


def choose_guards(rows, fields):
    selected, audit = [], []
    remaining = list(rows)
    while remaining and fields:
        base = stats(remaining)
        if not base["분모"]:
            break
        p0 = max(0.01, base["비율"])
        picked = None
        for size in (1, 2):
            pool = []
            for keys in combinations(fields, size):
                values = {tuple(r["guards"].get(key) for key in keys) for r in remaining}
                for vals in sorted(values, key=str):
                    if any(v in (None, "모름", "미상") for v in vals):
                        continue
                    cond = dict(zip(keys, vals))
                    subset = [r for r in remaining if matches(cond, r["guards"])]
                    s = stats(subset)
                    if not s["분모"]:
                        continue
                    n, k = s["분모"], s["함"]
                    tail = sum(comb(n, j) * p0**j * (1-p0)**(n-j) for j in range(k, n+1))
                    delta = s["비율"] - base["비율"]
                    ok = enough(s) and delta >= .2 - 1e-12 and tail < .001
                    result = {"조건": cond, "근거": s, "잔여기본비율": base["비율"], "상승폭": delta,
                              "단측p": tail, "통과": ok, "탐색차수": len(selected) + 1}
                    audit.append(result)
                    if ok:
                        priority = sum(1 for key in keys if "이력" in key or "직전" in key)
                        pool.append(((-k, priority, -s["비율"], tuple(fields.index(key) for key in keys), str(vals)), result))
            if pool:
                picked = min(pool, key=lambda x: x[0])[1]
                break
        if picked is None:
            break
        selected.append(picked)
        remaining = [r for r in remaining if not matches(picked["조건"], r["guards"])]
    return selected, audit


def matches(conditions, observed):
    return all(observed.get(k) == v for k, v in conditions.items())


def find_actions(day, spec):
    begin, finish, _ = spec
    starts = [t for t, _, txt in day.changes if re.search(begin, txt)]
    ends = [t for t, _, txt in day.changes if re.search(finish, txt)]
    actions = []
    for t in starts:
        if actions and actions[-1][1] is not None and t <= actions[-1][1]:
            continue
        end = next((u for u in ends if t <= u <= t+1800 and day.covered(t,u)), None)
        if actions and actions[-1][1] is None and t - actions[-1][0] <= 60:
            continue
        actions.append((t, end))
    return actions


def choose_time(days, action_dates):
    items = sorted((a, d.date) for d in days for a, _ in action_dates[d.date])
    if len({date for _, date in items}) < 4:
        return None
    best, earliest = 0, None
    for t in sorted({t for t, _ in items}):
        covered = len({d for u, d in items if t <= u <= t + 1800})
        if covered > best:
            best, earliest = covered, t
    return earliest if best >= 3 else None


def time_case(day, rule, t, observed, essential, event_rows=()):
    # 같은 작업 에피소드가 확인되지 않은 먼 과거의 행동은 오늘 이미 끝난 근거로 쓰지 않는다.
    nearby = [(a,b) for a,b in observed if t - 5400 <= a <= t + 1800]
    past = [(a,b) for a,b in nearby if b is not None and b < t]
    following = [(a,b) for a,b in nearby if t < a <= t+1800]
    ongoing = [(a,b) for a,b in nearby if a == t or (a < t and b is not None and t <= b)]
    evidence, checks = [], [(t, "확인필요", "시계만으로 대상의 현재 위치·재고와 사용자 선행 여부를 확인할 수 없음")]
    if ongoing:
        a, _ = ongoing[-1]
        result, reason = "관찰 불가", "시각 도달과 시작의 순서가 불명확하거나 이미 진행 중"
        evidence = [a]
        checks = [(t, "선행", "같은 행동을 시작한 사실이 그 시각까지 관찰됨")]
    elif past:
        a,b = past[-1]
        result, reason = "이미 함", "앞선 같은 시간대에 관찰한 동일 행동의 시작과 완료"
        evidence, checks = [a,b], [(t, "선행", "같은 시간대에 이미 끝낸 행동")]
    elif following:
        a,b = following[0]
        result, reason = "함", "예정 시각 이후 30분 안에 행동을 시작함"
        evidence = [a] + ([b] if b is not None else [])
        checks.append((a, "선행", "자연 재생에서 사용자가 먼저 행동을 시작함"))
    else:
        no_signal = essential and not any(t <= r["sec"] <= t + 1800 and
                    tuple(r[k] for k in ("기기","항목","값")) == tuple(essential) for r in day.signals)
        # 필수 기기의 특정 신호가 행동 시작보다 앞설 수도 있어 시작 직전의 신호도 확인한다.
        prior_signal = essential and any(t - 600 <= r["sec"] < t and
                       tuple(r[k] for k in ("기기","항목","값")) == tuple(essential) for r in day.signals)
        if no_signal and not prior_signal:
            result, reason = "하지 않음", "기록이 완전한 가전 로그에서 필수 신호가 없었음"
        else:
            result, reason = "관찰 불가", "관찰 위치·시간 또는 물건이 불명확하여 행동 부재를 증명할 수 없음"
    # 그 순간 같은 행동의 독립 사건에서 이미 확인된 실행 직전 상태만 재사용한다.
    for row in event_rows:
        for u, state, why in row["checks"]:
            if u == t and state != "확인필요":
                checks[0] = (t, state, why)
    return dict(id=rule, date=day.date, t=t, result=result, reason=reason, guards=day.guards(t),
                evidence=sorted(set(evidence)), checks=checks)


def classify(rule, spec, history, days, action_spec, actions, previous):
    name, trigger, action, kind, keys = spec
    keys = list(dict.fromkeys([*keys,*COMMON_GUARDS]))
    s = stats(history)
    tests, rules, time_info = [], [], None
    choice = lambda cond: {"경로":"사건", "조건":cond}
    status = "보류"
    if kind == "고정안전":
        rules, status = [choice({})], "설계 고정"
    elif kind == "관찰전용":
        status = "관찰 패턴 성립" if enough(s) else "관찰 전용"
    elif kind == "기기필수" and s["함"] > 0:
        rules, status = [choice({})], "기기 관계 확인"
    elif kind == "습관":
        if enough(s):
            rules = [choice({})]
        else:
            picked, tests = choose_guards(history, list(keys))
            rules = [choice(p["조건"]) for p in picked]
        if not rules and action_spec:
            t = choose_time(days, actions)
            if t is not None:
                time_rows = [time_case(d, rule, t, actions[d.date], action_spec[2]) for d in days]
                ts = stats(time_rows)
                time_info = {"시각":clock(t), "근거":ts, "날짜별결과":{r["date"]:r["result"] for r in time_rows}}
                if enough(ts):
                    rules = [{"경로":"시각", "시각":clock(t), "조건":{}}]
                else:
                    picked, time_tests = choose_guards(time_rows, keys)
                    time_info["조건검사"] = time_tests
                    rules = [{"경로":"시각","시각":clock(t),"조건":p["조건"]} for p in picked]
        if rules:
            status = "채택"
    if kind == "습관" and not rules and previous and previous["활성"]:
        # 자연 재생 기록에는 로봇 개입을 사용자가 되돌렸다는 관측이 없다.
        rules, status = previous["활성"], "기존 유지"
    return {"규칙ID":rule,"이름":name,"시작조건":trigger,"행동":action,"종류":kind,
            "상태":status,"활성":rules,"누적근거":s,"조건검사":tests,"시각검사":time_info}
