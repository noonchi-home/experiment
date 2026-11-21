"""트리거 단계 POMDP: 시각 관찰과 시간 정보로 트리거를 세운다. 세워진 트리거에서 task 고르기는 task_pomdp.py가 한다.

트리거 조건은 FSM 규칙의 자연어 트리거를 장면 사실의 조건으로 옮긴 것이다(scenarios/<시나리오>/triggers.json).
FSM이 바뀌면 compile_triggers로 조건을 다시 검증하고 다시 묶는다. 검증을 통과한 규칙의 트리거만 세울 수 있다.

Kostavelis 외(2017)의 튜플 {S, A, Ω, R, O, T, b0}로 적으면:
S    장면 사실(변수마다 따로): 사람 위치, 사람 활동(종류), 물체마다 놓인 곳(또는 없음).
     트리거 조건을 만족하면 경계 수준 H(도움이 필요함), 아니면 L(지켜보기)이다.
     시간은 숨은 상태가 아니다: 영상 시작 시각 + 창 위치로 코드가 정하므로 조건을 만족하면 1, 아니면 0이다.
A    지켜보기(A_M, 다음 창을 본다) / 트리거 세우기(로봇이 관여해 task를 고르러 감).
Ω    VLM 보고(사람 위치, 활동 문장).
T    창마다 config/sensor.json의 stay 확률로 값을 유지하고, 나머지는 고르게 바뀐다.
O    P(보고 | 참값)은 config/sensor.json: 검출률, 오검출률, VLM 확신별 정확도(config/model.json),
     이웃 자리 혼동(주방 <-> 식사 공간), 활동 분류 정확도.
b0   고르게 시작한다.
R    config/lora.json: 세움이 맞으면 H→M(+0.5), 틀리면 L→M(-0.25), 지켜보기는 0.
트리거 확률    P(트리거) = P(H) = 1[시간 조건] x Π 변수 P(그 변수가 조건을 만족). 같은 변수의 조건은 묶어서 계산한다.
트리거 세우기  EV = P·gain - (1-P)·false_fire 가 0보다 크면 세운다(문턱 = false_fire / (gain + false_fire) = 0.33).
"""
from __future__ import annotations

import re

from .config import MODEL, load
from .lora import trigger_gain_cost
from .observation import PLACES, SURFACES

ABSENT, NONE, OTHER = "absent", "none", "other"
TIME_RANGE = re.compile(r"(\d{1,2}:\d{2})\s*[~\-–]\s*(\d{1,2}:\d{2})")


class TriggerPOMDPError(ValueError):
    pass


def _uniform(values) -> dict:
    return {v: 1 / len(values) for v in values}


def _normalize(b: dict) -> dict:
    z = sum(b.values())
    return {k: v / z for k, v in b.items()} if z else b


def _stay(b: dict, stay: float) -> dict:
    n = len(b)
    return {k: p * stay + (1 - stay) / n for k, p in b.items()}


def _hhmm(t: str) -> str:
    return t.zfill(5)


def clock(time: str) -> str:
    """"2026-11-03T07:00:04" -> "07:00:04"."""
    return time.split("T")[-1][:8]


def classify_activity(text: str, activities: dict) -> str:
    """활동 문장 -> 활동 종류. 종류마다 단어 묶음이 있고, 묶음마다 단어 하나 이상이 문장에 있어야 한다.
    예: drinking coffee = [drink, sip] 중 하나 + [coffee, mug, cup] 중 하나. 맞는 종류가 없으면 other."""
    t = f" {text} ".lower()
    return next((a for a, groups in activities.items() if all(any(w in t for w in g) for g in groups)), OTHER)


class SceneBelief:
    """트리거에 쓰이는 장면 사실의 belief. 변수마다 따로 둔다(변수 사이는 독립으로 근사)."""

    def __init__(self, labels: list[str], activities: dict, sensor: dict | None = None):
        self.s = sensor or load("sensor.json")
        self.acc = MODEL["decision"]["accuracy"]
        self.activities = activities
        self.places = PLACES + [NONE]
        self.surfaces = SURFACES + [ABSENT]
        self.person = _uniform(self.places)
        self.activity = _uniform(list(activities) + [OTHER])
        self.objects = {label: _uniform(self.surfaces) for label in labels}
        self.started = False

    # ── 관찰 모델 ───────────────────────────────────────────
    def _w(self, reported: str, true: str, acc: float, n_values: int) -> float:
        """P(VLM이 reported라고 말함 | 참값 true, 검출됨)."""
        if reported == true:
            return acc
        alias = self.s["place_alias"].get(true, {})
        if reported in alias:
            return alias[reported]
        rest = max(0.0, 1 - acc - sum(alias.values()))
        return rest / max(1, n_values - 2 - len(alias))  # 참값·없음·혼동 자리를 뺀 나머지에 고르게

    def observe_person(self, frame: dict) -> None:
        d, fa, n = self.s["detect"], self.s["false_alarm"], len(PLACES)
        people = frame["people"]
        if people:
            r = people[0]["location"]
            like = {t: fa / n if t == NONE else d * self._w(r, t, self.acc["high"], len(self.places)) for t in self.places}
        else:
            like = {t: (1 - fa) if t == NONE else (1 - d) for t in self.places}
        self.person = _normalize({t: p * like[t] for t, p in self.person.items()})

    def observe_activity(self, frame: dict) -> None:
        """사람이 보이지 않으면 활동에 대한 정보가 없다(유지 확률만 적용)."""
        if not frame["people"]:
            return
        c = classify_activity(frame["people"][0]["activity"], self.activities)
        acc, k = self.s["activity"]["accuracy"], len(self.activity)
        self.activity = _normalize({a: p * (acc if a == c else (1 - acc) / max(1, k - 1)) for a, p in self.activity.items()})

    def observe_object(self, label: str, frame: dict) -> None:
        seen = [o for o in frame["objects"] if o["label"] == label]
        d, fa, n = self.s["detect"], self.s["false_alarm"], len(SURFACES)
        if seen:
            o = max(seen, key=lambda o: self.acc.get(o["confidence"], 0))
            like = {t: fa / n if t == ABSENT else d * self._w(o["on"], t, self.acc[o["confidence"]], len(self.surfaces))
                    for t in self.surfaces}
        else:
            like = {t: (1 - fa) if t == ABSENT else (1 - d) for t in self.surfaces}
        self.objects[label] = _normalize({t: p * like[t] for t, p in self.objects[label].items()})

    # ── 한 창 ───────────────────────────────────────────────
    def update(self, frame: dict) -> None:
        st = self.s["stay"]
        if self.started:
            self.person = _stay(self.person, st["person"])
            self.activity = _stay(self.activity, st["activity"])
            self.objects = {k: _stay(b, st["object"]) for k, b in self.objects.items()}
        self.started = True
        self.observe_person(frame)
        self.observe_activity(frame)
        for label in self.objects:
            self.observe_object(label, frame)


def _groups(when: list[dict]) -> tuple[dict, list]:
    """트리거 조건 -> 변수별 허용 값 집합, 그리고 시간 조건 목록."""
    allowed: dict = {}
    times = []

    def narrow(key, keep=None, drop=None):
        cur = allowed.get(key)  # None: 모든 값, set: 이 값들만, ("NOT", set): 이 값들 빼고
        if keep is not None:
            k = set(keep)
            cur = k if cur is None else (k - cur[1] if isinstance(cur, tuple) else cur & k)
        if drop is not None:
            dset = set(drop)
            cur = ("NOT", dset) if cur is None else (("NOT", cur[1] | dset) if isinstance(cur, tuple) else cur - dset)
        allowed[key] = cur

    for atom in when:
        if "time" in atom:
            times.append([_hhmm(x) for x in atom["time"]])
        elif "person_at" in atom:
            narrow("person", keep=atom["person_at"])
        elif "person_not_at" in atom:
            narrow("person", drop=atom["person_not_at"])
        elif "activity" in atom:
            narrow("activity", keep=[atom["activity"]])
        elif "object" in atom:
            narrow(f"object:{atom['object']}", keep=atom.get("at"), drop=atom.get("not_at"))
        else:
            raise TriggerPOMDPError(f"unknown trigger atom: {atom}")
    return allowed, times


def in_time(time: str, times: list) -> bool:
    """시작 <= 시각 < 끝 (HH:MM). 시간 조건이 없으면 항상 참."""
    hhmm = clock(time)[:5]
    return all(a <= hhmm < b for a, b in times)


# ── FSM -> 트리거 (FSM이 바뀔 때마다 다시 검증) ──────────────
def compile_triggers(fsm: dict, tasks: list[str], conditions: list[dict]) -> tuple[list[dict], list[dict]]:
    """FSM 규칙마다 트리거 문장에 맞는 조건을 찾아 트리거로 묶는다. 같은 트리거 문장의 규칙은 한 트리거가 된다.

    검증(통과하지 못한 규칙은 트리거로 세우지 않고 issues에 남긴다):
      1. 규칙의 행동 문장이 tasks.json에 있다.
      2. 트리거 문장과 똑같은 rule을 가진 조건이 triggers.json에 있다(문장이 바뀌면 사람이 조건을 다시 옮겨야 한다).
      3. 조건의 state가 규칙이 있는 FSM 상태와 같다.
      4. 트리거 문장에 적힌 시간 범위(HH:MM~HH:MM)가 조건의 time과 같다.
    규칙이 하나도 없는 조건은 세우지 않는다(unused로 남긴다)."""
    by_rule = {c["rule"]: c for c in conditions}
    out: dict[str, dict] = {}
    issues = []
    for s in fsm["states"]:
        for r in s["rules"]:
            where = {"state": s["id"], "rule": r["trigger"], "action": r["action"]}
            if r["action"] not in tasks:
                issues.append({**where, "issue": "action is not in tasks.json"})
                continue
            c = by_rule.get(r["trigger"])
            if c is None:
                issues.append({**where, "issue": "no condition in triggers.json for this trigger text"})
                continue
            if c["state"] != s["id"]:
                issues.append({**where, "issue": f"condition is for state {c['state']}"})
                continue
            text_times = sorted([_hhmm(a), _hhmm(b)] for a, b in TIME_RANGE.findall(r["trigger"]))
            if text_times != sorted(_groups(c["when"])[1]):
                issues.append({**where, "issue": f"time range in text {text_times} != condition {_groups(c['when'])[1]}"})
                continue
            t = out.setdefault(c["id"], {**c, "tasks": []})
            t["tasks"].append(tasks.index(r["action"]))
    for c in conditions:
        if c["id"] not in out:
            issues.append({"state": c["state"], "rule": c["rule"], "issue": "unused: no FSM rule uses this trigger"})
    return list(out.values()), issues


class TriggerPOMDP:
    def __init__(self, triggers: list[dict], cfg: dict, sensor: dict | None = None):
        """triggers: compile_triggers의 결과. cfg: 시나리오 triggers.json(activities). 이득·비용은 config/lora.json."""
        self.triggers = triggers
        self.gain, self.false_fire = trigger_gain_cost()
        labels = sorted({k.split(":", 1)[1] for t in triggers for k in _groups(t["when"])[0] if k.startswith("object:")})
        self.belief = SceneBelief(labels, cfg["activities"], sensor)

    # ── 트리거 확률 by belief─────────────────────────────────
    def _var(self, key: str) -> dict:
        b = self.belief
        if key == "person":
            return b.person
        if key == "activity":
            return b.activity
        return b.objects[key.split(":", 1)[1]]

    @staticmethod
    def _p(dist: dict, rule) -> float:
        if isinstance(rule, tuple):  # ("NOT", 뺄 값)
            return sum(p for v, p in dist.items() if v not in rule[1])
        return sum(p for v, p in dist.items() if v in rule)

    def prob(self, trigger: dict, time: str) -> float:
        allowed, times = _groups(trigger["when"])
        if not in_time(time, times):
            return 0.0
        p = 1.0
        for key, rule in allowed.items():
            p *= self._p(self._var(key), rule)
        return p

    def ev(self, trigger: dict, p: float) -> float:
        return p * self.gain - (1 - p) * self.false_fire

    # ── 비교 기준: 한 창의 VLM 보고를 그대로 믿고 조건을 맞추기(w/o belief)) ──
    def baseline(self, trigger: dict, frame: dict) -> bool:
        allowed, times = _groups(trigger["when"])
        acts = self.belief.activities

        def holds(key, rule) -> bool:
            if key == "person":
                vals = {p["location"] for p in frame["people"]} or {NONE}
            elif key == "activity":
                vals = {classify_activity(p["activity"], acts) for p in frame["people"]} or {OTHER}
            else:
                vals = {o["on"] for o in frame["objects"] if o["label"] == key.split(":", 1)[1]} or {ABSENT}
            return bool(vals - rule[1]) if isinstance(rule, tuple) else bool(vals & set(rule))

        return in_time(frame["time"], times) and all(holds(k, r) for k, r in allowed.items())

    # ── 한 창: belief 갱신 -> 트리거 확률 -> 세우기 ─────────────
    def step(self, frame: dict) -> dict:
        self.belief.update(frame)
        rows = []
        for t in self.triggers:
            p = self.prob(t, frame["time"])
            rows.append({"id": t["id"], "state": t["state"], "tasks": t["tasks"], "p": round(p, 3),
                         "ev": round(self.ev(t, p), 3), "threshold": round(self.false_fire / (self.gain + self.false_fire), 3),
                         "fired": self.ev(t, p) > 1e-9, "baseline": self.baseline(t, frame)})
        b = self.belief
        return {"time": frame["time"], "frame": frame["frame"], "triggers": rows,
                "belief": {"person": self._top(b.person), "activity": self._top(b.activity),
                           **{f"object:{k}": self._top(v) for k, v in b.objects.items()}}}

    @staticmethod
    def _top(dist: dict) -> str:
        k = max(dist, key=dist.get)
        return f"{k} {dist[k]:.0%}"
