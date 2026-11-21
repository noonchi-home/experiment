"""FSM 수정(PAM 반성 단계)에 belief을 둔다: 수정안은 그날 고른 task와 정답 task의 비교로 내고,
반영 여부는 규칙마다의 belief과 기대 이득으로 정한다. FSM이 바뀌면 트리거도 다시 검증한다(trigger_pomdp.compile_triggers).

숨은 상태  규칙(task)마다 "거주자가 이 규칙을 원한다 / 원하지 않는다". 처음 belief은 FSM에서 온다
           (task_pomdp.task_prior: 초기 FSM 규칙 designed_rule, FSM 다음 상태를 돕는 task proposed_rule x reach, 그 밖 unrelated_rule).
           같은 belief을 task_pomdp가 task를 고를 때 쓴다.
전이       없음: 선호는 며칠 사이에 바뀌지 않는다고 본다.
관찰       하루가 끝날 때의 증거(compare_with_answer). 트리거 POMDP가 그 상황이 맞다고 본 확률 q를 함께 쓴다.
           - task를 요청함 -> 정답에 있음(받아들임) / 없음(거절)
               P(받아들임 | 원함) = q·a_w + (1-q)·a_u,   P(받아들임 | 원하지 않음) = a_u   (상황이 아니었으면 원해도 거절)
           - task를 요청하지 않았지만 상황이라고 본 확률 q >= min_situation이고 정답에 있음 -> 거주자가 직접 함(보고 있음)
               P(보고 | 원함) = q·(a_w·d + (1-a_w)·fa) + (1-q)·fa   (원하지 않음은 a_w 대신 a_u)
           - 질문의 답(예 / 아니오): 정확도 answer_accuracy
결정       수정안(add: 규칙 넣기 / remove: 규칙 빼기)마다
               EV(add)    = P·이득 - (1-P)·방해 비용
               EV(remove) = (1-P)·방해 비용 - P·이득
               질문의 정보 가치 VOI = min(P·이득, (1-P)·방해 비용)   (답이 정확하다고 볼 때. add, remove 모두 같은 식)
           VOI > ask_cost이고 오늘 질문이 남았으면 먼저 묻는다(VOI가 큰 수정안부터). 그 뒤 EV > 0이면 반영하고,
           아니면 보류한다(pending_days 동안 매일 밤 다시 본다).
보상       이득·방해 비용은 task_pomdp와 같다(task의 group, config/lora.json). 질문은 Kostavelis 외(2017)의
           communication 행동(A_C)이고, ask_cost는 원하지 않는 질문의 보상 L→M(-0.25)에서 온다.
한 단계 앞만 본다.
"""
from __future__ import annotations

import copy

from .config import load
from .lora import ask_cost


# ── 규칙마다의 belief ─────────────────────────────────────────
class EditBelief:
    def __init__(self, n_tasks: int, designed: set[int], gain: list[float], cost: list[float], cfg: dict | None = None,
                 prior: dict[int, float] | None = None):
        """prior를 주면 그 값으로 시작한다(task_pomdp.task_prior). 없으면 FSM에 있음 / 없음 두 값."""
        self.c = cfg or load("fsm_edit.json")
        pr = self.c["prior"]
        self.p = dict(prior) if prior is not None else \
            {i: pr["designed_rule"] if i in designed else pr["proposed_rule"] for i in range(n_tasks)}
        self.gain, self.cost = gain, cost

    def _bayes(self, i: int, like_wanted: float, like_unwanted: float) -> None:
        p = self.p[i]
        z = p * like_wanted + (1 - p) * like_unwanted
        if z:
            self.p[i] = p * like_wanted / z

    def observe_response(self, i: int, accepted: bool, q: float) -> None:
        r = self.c["response"]
        aw, au = r["accept_if_wanted"], r["accept_if_unwanted"]
        w = q * aw + (1 - q) * au
        self._bayes(i, w if accepted else 1 - w, au if accepted else 1 - au)

    def observe_self_done(self, i: int, seen: bool, q: float) -> None:
        r, s = self.c["response"], self.c["self_done"]
        d, fa = s["detect"], s["false_alarm"]

        def like(a: float) -> float:
            x = q * (a * d + (1 - a) * fa) + (1 - q) * fa
            return x if seen else 1 - x

        self._bayes(i, like(r["accept_if_wanted"]), like(r["accept_if_unwanted"]))

    def observe_answer(self, i: int, yes: bool) -> None:
        a = self.c["answer_accuracy"]
        self._bayes(i, a if yes else 1 - a, 1 - a if yes else a)

    def ev(self, op: str, i: int) -> float:
        p, g, c = self.p[i], self.gain[i], self.cost[i]
        return p * g - (1 - p) * c if op == "add" else (1 - p) * c - p * g

    def voi(self, i: int) -> float:
        p = self.p[i]
        return min(p * self.gain[i], (1 - p) * self.cost[i])


class BeliefGate:
    """방법 2: 반성 단계의 수정안을 belief으로 거른다."""

    def __init__(self, belief: EditBelief, ask: bool = True):
        self.b, self.c = belief, belief.c
        self.questions = self.c["questions_per_day"] if ask else 0
        self.ask_cost = ask_cost()
        self.pending: dict[tuple[str, int], int] = {}  # (op, task) -> 마지막으로 제안된 날

    def review(self, day: int, proposals: list[tuple[str, int]], enabled: set[int], answer) -> tuple[set[int], list[dict]]:
        for prop in proposals:
            self.pending[prop] = day
        # 이미 이루어진 수정(넣을 규칙이 이미 있음 / 뺄 규칙이 이미 없음)과 오래된 수정안은 지운다
        self.pending = {(op, i): d for (op, i), d in self.pending.items()
                        if (op == "add") != (i in enabled) and day - d < self.c["pending_days"]}
        log, left, enabled = [], self.questions, set(enabled)
        for op, i in sorted(self.pending, key=lambda k: (-self.b.voi(k[1]), k)):
            v = self.b.voi(i)
            if left > 0 and v > self.ask_cost:
                yes = answer(i)
                self.b.observe_answer(i, yes)
                left -= 1
                log.append({"asked": i, "op": op, "voi": round(v, 3), "answer": yes, "p": round(self.b.p[i], 3)})
        for op, i in sorted(self.pending):
            ev = self.b.ev(op, i)
            if ev > 1e-9:
                (enabled.add if op == "add" else enabled.discard)(i)
                del self.pending[(op, i)]
                log.append({"applied": op, "task": i, "p": round(self.b.p[i], 3), "ev": round(ev, 3)})
            else:
                log.append({"held": op, "task": i, "p": round(self.b.p[i], 3), "ev": round(ev, 3)})
        return enabled, log


def compare_with_answer(issued: dict[int, float], answer: set[int], q_day: float, enabled: set[int],
                        belief: EditBelief) -> tuple[dict[int, dict], list[tuple[str, int]]]:
    """그날 고른 task(issued: task -> 고른 때의 P(트리거))와 정답 task를 비교해 belief를 고치고 수정안을 낸다.
      고름 + 정답      받아들임. FSM에 없으면 add
      고름 + 정답 아님  거절.    FSM에 있으면 remove
      안 고름 + 정답   거주자가 직접 함(보고 있음). FSM에 없으면 add
    q_day: 그날 P(트리거)의 최댓값(고르지 않은 task의 증거 무게)."""
    events, proposals = {}, []
    min_q = belief.c["self_done"]["min_situation"]
    for i in sorted(set(issued) | answer):
        if i in issued:
            ok = i in answer
            belief.observe_response(i, ok, issued[i])
            events[i] = {"acted": True, "accepted": ok, "q": round(issued[i], 3)}
            if ok and i not in enabled:
                proposals.append(("add", i))
            if not ok and i in enabled:
                proposals.append(("remove", i))
        else:
            events[i] = {"acted": False, "in_answer": True, "q": round(q_day, 3)}
            if q_day >= min_q:
                belief.observe_self_done(i, True, q_day)
                events[i]["seen_self_done"] = True
            if i not in enabled:
                proposals.append(("add", i))
        events[i]["p"] = round(belief.p[i], 3)
    return events, proposals


# ── FSM 파일 ────────────────────────────────────────────────
def designed_rules(fsm: dict, tasks: list[str]) -> set[int]:
    """FSM 규칙의 행동 문장 -> task 번호(PAM과 같이 행동 문장이 tasks.json과 똑같아야 한다)."""
    return {tasks.index(r["action"]) for s in fsm["states"] for r in s["rules"]}


def edited_fsm(fsm: dict, tasks: list[str], enabled: set[int], candidates: dict) -> dict:
    """켜진 규칙만 남긴 PAM 형식 FSM. 초기 FSM의 규칙은 원래 자리에 그대로 두고,
    새로 넣은 규칙은 candidates({task: {state, trigger}}: 그 task를 고른 트리거의 상태·문장)로 쓴다."""
    out = copy.deepcopy(fsm)
    for s in out["states"]:
        s["rules"] = [r for r in s["rules"] if tasks.index(r["action"]) in enabled]
    for i in sorted(set(enabled) - designed_rules(fsm, tasks)):
        c = candidates[str(i)]
        next(s for s in out["states"] if s["id"] == c["state"])["rules"].append({"trigger": c["trigger"], "action": tasks[i]})
    return out
