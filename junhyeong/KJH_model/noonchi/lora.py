"""로봇 경계 수준(Level of Robot Alert, LoRA)으로 보상을 정한다. Kostavelis 외, HCI International 2017의 설계 틀.

상태 묶음   S_H(도움이 필요함), S_M(로봇이 이미 관여함), S_L(도움이 필요 없음, 지켜보기만 함).
행동 묶음   A_T task(환경을 바꿈), A_C communication(거주자에게 묻기·알림), A_M monitoring(상태만 알아냄).
보상        경계 수준이 낮아지면 양수, 높아지면 음수, M→M은 고르게(config/lora.json reward).
            행동 묶음마다 원할 때(H에서)와 원하지 않을 때(L에서) 어느 수준으로 가는지 정해 두고,
            gain = R[H][원할 때 수준], cost = -R[L][원하지 않을 때 수준]으로 바꾼다.
그래서 트리거(trigger_pomdp), task 고르기(task_pomdp), FSM 수정(fsm_edit)의 이득·비용이 모두 같은 표에서 나온다.
"""
from __future__ import annotations

from .config import load

LORA = load("lora.json")
GROUPS = list(LORA["groups"])


def reward(a: str, b: str) -> float:
    """경계 수준 a -> b의 보상."""
    return LORA["reward"][a][b]


def _gain_cost(spec: dict) -> tuple[float, float]:
    return reward("H", spec["to_if_needed"]), -reward("L", spec["to_if_not"])


def group_gain_cost(group: str) -> tuple[float, float]:
    """행동 묶음 -> (gain, cost)."""
    if group not in LORA["groups"]:
        raise ValueError(f"unknown action group: {group} (allowed: {', '.join(GROUPS)})")
    return _gain_cost(LORA["groups"][group])


def trigger_gain_cost() -> tuple[float, float]:
    """트리거를 세움 = 로봇이 지켜보기에서 관여로 넘어감."""
    return _gain_cost(LORA["trigger"])


def ask_cost() -> float:
    """질문 한 번(A_C)을 원하지 않을 때의 비용."""
    return group_gain_cost("communication")[1]
