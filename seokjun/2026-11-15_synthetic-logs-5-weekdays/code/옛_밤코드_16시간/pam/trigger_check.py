"""Check reflector trigger candidates with the 80% rule and a one-sided binomial test.

    Adopt(c -> a)  iff  k/n >= 0.8  and  sum_{i=k..n} C(n,i) p0^i (1-p0)^(n-i) < 0.001
                        p0 = max(other-time rate, 0.01)

Input per day: the moments when candidate c happened (already limited to the rule's
state), the moments when the person did action a, and the intervals when the person
was not visible. Times are seconds since midnight. A candidate is followed when the
action comes within 5 minutes after it and before the same candidate shows up again,
so only the last candidate before an action is credited with it. A candidate whose
window overlaps an unseen interval without an observed action is left out ("못 봄"). The other-time
rate counts 5-minute slots that neither touch a candidate's 5 minutes nor overlap an
unseen interval. Nothing here calls a model.
"""

from __future__ import annotations

from copy import deepcopy
from math import comb

from .contracts import validate_candidate_memory, validate_memory

FOLLOW_SECONDS = 300
SLOT_SECONDS = 300
RATE_MIN = 0.8
ALPHA = 0.001
FLOOR = 0.01


def binomial_tail(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def check_candidate(days: list[dict]) -> dict:
    """Count n, k and the other-time rate over all days so far, then apply both tests."""
    n = k = unknown = other_slots = slots_with_action = 0
    for day in days:
        candidates, actions, unseen = day["candidate"], day["action"], day["unseen"]
        ordered = sorted(candidates)
        for index, moment in enumerate(ordered):
            # Half-open window [low, high): the five minutes after the candidate,
            # cut short where the same candidate shows up again. Only the last
            # candidate before an action is credited with it.
            low, high = moment + 1, moment + FOLLOW_SECONDS + 1
            repeats = [later for later in ordered[index + 1:] if later > moment]
            if repeats and repeats[0] < high:
                high = repeats[0]
            if any(low <= action < high for action in actions):
                n, k = n + 1, k + 1
            elif any(start < high and end > low for start, end in unseen):
                unknown += 1
            else:
                n += 1
        for slot in range(day["start"], day["end"], SLOT_SECONDS):
            slot_end = slot + SLOT_SECONDS
            if any(slot <= moment + FOLLOW_SECONDS and slot_end > moment for moment in candidates):
                continue
            if any(start < slot_end and end > slot for start, end in unseen):
                continue
            other_slots += 1
            slots_with_action += any(slot <= action < slot_end for action in actions)
    base_rate = slots_with_action / other_slots if other_slots else 0.0
    p0 = max(base_rate, FLOOR)
    rate = k / n if n else 0.0
    p_value = binomial_tail(k, n, p0) if n else 1.0
    return {"n": n, "k": k, "unknown": unknown, "rate": rate, "base_rate": base_rate, "p0": p0,
            "p_value": p_value, "passed": n > 0 and rate >= RATE_MIN and p_value < ALPHA}


def predictor_fsm(reflector_fsm: dict, passed: set[tuple[str, str, str]]) -> dict:
    """Keep only the candidates in `passed` (state id, action, candidate) and join them with
    " or " into the paper's one-line trigger. Rules left without a candidate are dropped."""
    validate_candidate_memory(reflector_fsm)
    states = []
    for state in reflector_fsm["states"]:
        rules = []
        for rule in state["rules"]:
            kept = [candidate for candidate in rule["triggers"]
                    if (state["id"], rule["action"], candidate) in passed]
            if kept:
                rules.append({"trigger": " or ".join(kept), "action": rule["action"]})
        states.append({"id": state["id"], "description": state["description"],
                       "rules": rules, "next": deepcopy(state["next"])})
    return validate_memory({"initial_state": reflector_fsm["initial_state"], "states": states}, "fsm")
