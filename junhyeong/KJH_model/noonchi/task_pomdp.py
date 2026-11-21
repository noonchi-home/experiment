"""Task 단계 POMDP: 트리거가 서면 task 목록(tasks.json, 20개) 중 무엇을 요청할지 FSM과 믿음으로 고른다.

Kostavelis 외(2017)의 튜플 {S, A, Ω, R, O, T, b0}로 적으면:
S    task마다 "거주자가 이 상황에서 이 task를 원한다(H: 도움이 필요함) / 원하지 않는다(L)".
     믿음은 fsm_edit.EditBelief를 함께 쓴다(하루가 끝나면 정답 task와 비교한 결과로 갱신되고, FSM 규칙도 넣거나 뺀다).
A    task 20개. task_specs.json의 group으로 묶는다: task(A_T, 환경을 바꿈) / monitoring(A_M, 상태만 알아냄).
     고르지 않으면 지켜보기(보상 0)다.
Ω    트리거 확률 P(트리거)(trigger_pomdp.py)와 허브가 알려 주는 기기 상태.
T    상태도(FSM)가 전이를 정한다: 트리거 상태에서 FSM 전이로 이어진 다음 상태일수록 그 상태를 돕는 task를 원할 확률이 높다.
b0   FSM에서 온다(task_prior). 값은 config/fsm_edit.json의 prior.
     - FSM 규칙의 행동인 task: designed_rule
     - 트리거 상태에서 FSM 전이로 갈 수 있는 다음 상태(task의 serves)를 돕는 task:
       proposed_rule x 그 상태까지 갈 확률(reach, 전이마다 p를 곱함)
     - 그 밖: unrelated_rule
R    config/lora.json: 원할 때 H→L(+1.0). 원하지 않을 때 task는 L→H(-1.0), monitoring은 L→M(-0.25).
전제 조건  허브가 알려 주는 기기 상태(requires)로 정한다. 맞지 않으면 그 task는 고르지 않는다.
결정       P(task) = P(트리거) x 믿음,  EV = P·gain - (1-P)·cost 가 0보다 크면 요청한다(task마다 하루 한 번).
           한 트리거에서 여러 task를 함께 고를 수 있다. 문턱은 task 0.5, monitoring 0.2.
POMDP는 무엇을 요청할지만 정한다. 허브 응답에 따른 다음 요청 같은 실행은 smarthome.py가 맡는다.
"""
from __future__ import annotations

from .smarthome import SmartHomeHub


def reach(fsm: dict, start: str) -> dict[str, float]:
    """start에서 FSM 전이(next)를 따라 각 상태까지 갈 확률. 길이 여럿이면 가장 큰 값(한 단계 앞이 아니라 경로 전체)."""
    out = {start: 1.0}
    nxt = {s["id"]: s["next"] for s in fsm["states"]}
    todo = [start]
    while todo:
        s = todo.pop()
        for e in nxt.get(s, []):
            p = out[s] * e.get("p", 1.0)
            if p > out.get(e["to"], 0.0) + 1e-12:
                out[e["to"]] = p
                todo.append(e["to"])
    return out


def task_prior(fsm: dict, tasks: list[str], specs: list[dict], prior: dict, start: str) -> dict[int, float]:
    rules = {r["action"] for s in fsm["states"] for r in s["rules"]}
    r = reach(fsm, start)
    out = {}
    for i, (text, spec) in enumerate(zip(tasks, specs)):
        if text in rules:
            out[i] = prior["designed_rule"]
        elif spec.get("serves") in r and spec["serves"] != start:
            out[i] = prior["proposed_rule"] * r[spec["serves"]]
        else:
            out[i] = prior["unrelated_rule"]
    return out


def precondition(spec: dict, hub: SmartHomeHub) -> tuple[bool, str]:
    """허브는 연결되어 있으므로 등록 기기의 상태는 정확히 안다."""
    req = spec.get("requires")
    if req:
        state = hub.devices[req["device"]]["state"]
        bad = {k: state.get(k) for k, v in req.items() if k != "device" and state.get(k) != v}
        if bad:
            return False, f"hub: {req['device']} {bad}"
    return True, ""


class TaskPOMDP:
    def __init__(self, tasks: list[str], specs: list[dict], belief):
        """belief: fsm_edit.EditBelief(p[i] = 거주자가 task i를 원할 확률)."""
        if len(tasks) != len(specs):
            raise ValueError("task_specs.json needs exactly one entry per task in tasks.json")
        self.tasks, self.specs, self.b = tasks, specs, belief
        self.done: set[int] = set()  # 오늘 이미 요청한 task

    def decide(self, p_trigger: float, hub: SmartHomeHub) -> list[dict]:
        rows = []
        for i, spec in enumerate(self.specs):
            ok, why = precondition(spec, hub)
            w = self.b.p[i]
            p = p_trigger * w if ok else 0.0
            ev = p * spec["gain"] - (1 - p) * spec["cost"]
            rows.append({"task": i, "belief": round(w, 3), "p": round(p, 3), "ev": round(ev, 3), "blocked": why,
                         "chosen": ok and ev > 1e-9 and i not in self.done})
        for r in rows:
            if r["chosen"]:
                self.done.add(r["task"])
        return rows
