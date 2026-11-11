"""LLM 방법(바로 맡기기, FSM 먼저)에 줄 글을 만든다. 세 방법이 같은 집·같은 문제를 보도록,
집 정의는 world.Home에서, 원자 행동 글은 문제 폴더의 두 파일(설명만, 조건표)에서 그대로 가져온다.
"""
import json

from world import PROB_DIR, start_state

DOC = {"설명": "원자행동_설명.md", "조건표": "원자행동_조건표.md"}
RUN_RULES = [
    "행동 결과가 '됨'이 아니면 로봇은 다음 행동으로 넘어가지 않는다.",
    "look으로 살펴봤는데 대상이 없으면, 로봇은 거기서 멈추고 사용자에게 할 수 없다고 알린다.",
]
ACTION_FORMAT = (
    '["go", 서는곳], ["look", 놓는곳, 물건], ["open", 문], ["close", 문], ["pick", 물건] 또는 ["pick", 물건, 출발지], '
    '["place", 물건, 놓는곳], ["set", 가전, 명령] 또는 입력이 있는 명령은 ["set", 가전, 명령, 입력], '
    '["read", 가전, 항목], ["wait", 가전, 항목, 값]'
)
ANSWER_FORMAT = (
    "답은 json 객체 하나로만 쓴다. 다른 글은 쓰지 않는다.\n"
    '{"할수있음": true, "순서": [["go", "냉장고_앞"], ["open", "냉장고_문"]], "까닭": "한두 문장"}\n'
    "- 로봇이 할 수 없는 일이면 할수있음은 false, 순서는 []로 쓴다.\n"
    "- 이미 목표 모습이면 할수있음은 true, 순서는 []로 쓴다.\n"
    f"- 행동 하나는 이 형식 중 하나다: {ACTION_FORMAT}\n"
    "- 이름은 집 정의의 id를 글자 그대로 쓴다."
)


def home_text(home):
    places = [{k: v for k, v in p.items() if v is not None} for p in home.place_info.values()]
    doors = [{k: v for k, v in d.items() if v is not None} for d in home.door_info.values()]
    devices = [{k: v for k, v in d.items() if k != "문"} for d in home.devices.values()]
    data = {"서는곳": [{"id": k, "방": v} for k, v in home.stands.items()], "놓는곳": places, "문": doors, "가전": devices}
    return json.dumps(data, ensure_ascii=False)


def system_prompt(home, variant):
    doc = (PROB_DIR / DOC[variant]).read_text(encoding="utf-8")
    rules = "\n".join(f"- {r}" for r in home.rules + RUN_RULES)
    return (
        "너는 집안일 로봇의 작업 계획을 세운다. 로봇은 아래 원자 행동만 할 수 있다.\n\n"
        f"{doc}\n\n## 집 정의(json)\n{home_text(home)}\n\n## 집 규칙과 실행 규칙\n{rules}\n"
    )


def problem_text(prob, home):
    s = start_state(home, prob)
    s.pop("없음", None)
    return (f"## 할 일\n{prob['할일']}\n\n## 지금 모습(json)\n{json.dumps(s, ensure_ascii=False)}\n\n"
            f"## 목표 모습(json)\n{json.dumps(prob['목표'], ensure_ascii=False)}\n")


def direct_messages(prob, home, variant):
    return [{"role": "system", "content": system_prompt(home, variant)},
            {"role": "user", "content": problem_text(prob, home) + "\n지금 모습에서 목표 모습까지 가는 원자 행동 순서를 써라.\n\n" + ANSWER_FORMAT}]


FSM_FORMAT = (
    "답은 json 객체 하나로만 쓴다. 다른 글은 쓰지 않는다.\n"
    '{"상태들": [{"이름": "냉장고 열기", "하위 작업": "냉장고 문을 연다", "다음": [{"조건": "문이 열림", "상태": "맥주 꺼내기"}]}], '
    '"시작": "냉장고 열기", "끝 상태": ["완료"], "할수있음_예상": true}'
)


def fsm_messages_1(prob, home, variant):
    return [{"role": "system", "content": system_prompt(home, variant)},
            {"role": "user", "content": problem_text(prob, home) +
             "\n먼저 이 일을 FSM(유한 상태 기계)으로 적어라. 상태는 이 일을 나눈 하위 작업이고, 전이는 하위 작업이 "
             "끝나거나 실패했을 때 다음 상태로 가는 길이다. 원자 행동 순서는 아직 쓰지 않는다.\n\n" + FSM_FORMAT}]


def fsm_messages_2(prob, home, variant, fsm_text):
    return [{"role": "system", "content": system_prompt(home, variant)},
            {"role": "user", "content": problem_text(prob, home) + f"\n## 이 일의 FSM(json)\n{fsm_text}\n\n"
             "이 FSM을 따라, 지금 모습에서 목표 모습까지 가는 원자 행동 순서로 바꿔라.\n\n" + ANSWER_FORMAT}]
