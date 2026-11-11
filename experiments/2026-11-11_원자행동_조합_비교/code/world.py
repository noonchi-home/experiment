"""집 정의와 문제를 읽고, 고정한 조건표대로 원자 행동을 한 단계씩 따라간다.
계획기(planner.py)와 채점기(score.py)가 같은 규칙을 쓰도록 여기 한 곳에만 둔다.
"""
import copy
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
PROB_DIR = ROOT / "output" / "원자행동조합_문제"
ACTIONS = {"go": 1, "look": 2, "open": 1, "close": 1, "pick": (1, 2), "place": 2, "set": (2, 3), "read": 2, "wait": 3}


def load_home():
    return json.loads((PROB_DIR / "집.json").read_text(encoding="utf-8"))


def load_problems(name="문제.jsonl"):
    rows = (PROB_DIR / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(r) for r in rows if r.strip()]


class Home:
    """집 정의에 문제의 집_바꿈을 더한 것."""

    def __init__(self, home, change=None):
        change = change or {}
        self.rules = home["집 규칙"]
        self.stands = {s["id"]: s["방"] for s in home["서는곳"]}
        self.place_info = {p["id"]: p for p in home["놓는곳"]}
        for k, v in change.get("놓는곳_추가", {}).items():
            self.place_info[k] = {"id": k, "서는곳": v[0], "문": v[1], "설명": v[2]}
        self.places = {k: (p["서는곳"], p["문"]) for k, p in self.place_info.items()}
        self.door_info = {d["id"]: d for d in home["문"]}
        self.doors = {k: (d["서는곳"], d["달린 가전"], d["닫히는 자리"]) for k, d in self.door_info.items()}
        self.devices = {d["id"]: copy.deepcopy(d) for d in home["가전"]}
        for dev, cmds in change.get("명령_추가", {}).items():
            self.devices[dev]["명령"].update(copy.deepcopy(cmds))
        self.base = home["기본 모습"]


def start_state(home, prob):
    s = copy.deepcopy(home.base)
    c = prob["처음"]
    for k in ("로봇", "손"):
        if k in c:
            s[k] = c[k]
    for k in ("물건", "물건상태", "모름", "사람", "자리상태"):
        s[k] = {**s.get(k, {}), **copy.deepcopy(c.get(k, {}))}
    s["문"] = {**s["문"], **c.get("문", {})}
    s["잠긴문"] = list(c.get("잠긴문", []))
    s["가전"] = {d: dict(v) for d, v in s["가전"].items()}
    for dev, kv in c.get("가전", {}).items():
        s["가전"][dev] = {**s["가전"].get(dev, {}), **kv}
    s["없음"] = []
    sync_doors(s, home)
    return s


def sync_doors(s, home):
    """가전 값의 '문'(예: 냉장고 문)을 실제 문 상태와 맞춘다. 둘이 어긋난 채로 모델에 보이지 않게 한다."""
    for dev, spec in home.devices.items():
        door = spec.get("문")
        if door and "문" in s["가전"].get(dev, {}):
            s["가전"][dev]["문"] = s["문"][door]


def shape_error(a):
    """행동 한 줄의 모양이 맞는지 본다. 맞으면 None."""
    if not isinstance(a, list) or not a or not all(isinstance(x, str) for x in a):
        return "행동은 글자들의 목록이어야 함"
    n = ACTIONS.get(a[0])
    if n is None:
        return f"원자 행동이 아님: {a[0]}"
    ok = len(a) - 1 in n if isinstance(n, tuple) else len(a) - 1 == n
    return None if ok else f"{a[0]}의 인수 개수가 맞지 않음"


def step(a, s, home, absent):
    """조건표대로 한 단계를 해 본다. 할 수 없으면 까닭을 돌려주고, 하면 s를 바꾸고 None을 돌려준다."""
    err = shape_error(a)
    if err:
        return err
    kind, args = a[0], a[1:]
    places, doors, devices = home.places, home.doors, home.devices
    if kind == "go":
        if args[0] not in home.stands:
            return f"없는 서는곳 {args[0]}"
        s["로봇"] = args[0]
    elif kind == "look":
        scope, target = args
        if scope not in places:
            return f"없는 놓는곳 {scope}"
        stand, door = places[scope]
        if s["로봇"] != stand:
            return f"로봇이 {stand}에 없음"
        if door and s["문"][door] != "열림":
            return f"{door}이 닫혀 있어 볼 수 없음"
        if target in s["모름"]:
            del s["모름"][target]
            if target in absent:
                s["없음"].append(target)
    elif kind in ("open", "close"):
        d = args[0]
        if d not in doors:
            return f"없는 문 {d}"
        stand, dev, gap = doors[d]
        if s["로봇"] != stand:
            return f"로봇이 {stand}에 없음"
        if kind == "open":
            if s["문"][d] != "닫힘":
                return f"{d}이 닫혀 있지 않음"
            if d in s["잠긴문"]:
                return f"{d}이 잠겨 있음"
            if dev and s["가전"].get(dev, {}).get("운전") == "작동 중":
                return f"{dev} 작동 중에는 문을 열 수 없음"
            s["문"][d] = "열림"
        else:
            if s["문"][d] != "열림":
                return f"{d}이 열려 있지 않음"
            if gap and gap in s["물건"].values():
                return f"{gap}에 물건이 있어 닫을 수 없음"
            s["문"][d] = "닫힘"
        sync_doors(s, home)
    elif kind == "pick":
        obj = args[0]
        if s["손"] is not None:
            return "손이 비어 있지 않음"
        if obj in s["모름"]:
            return f"{obj}의 자리를 모름"
        if obj in absent or obj not in s["물건"]:
            return f"{obj}이 집에 없음"
        loc = s["물건"][obj]
        if loc not in places:
            return f"{obj}이 놓는곳에 없음({loc})"
        stand, door = places[loc]
        if s["로봇"] != stand:
            return f"로봇이 {stand}에 없음"
        if door and s["문"][door] != "열림":
            return f"{door}이 닫혀 있음"
        if len(args) > 1 and args[1] != loc:
            return "출발지가 다름"
        s["손"], s["물건"][obj] = obj, "로봇손"
    elif kind == "place":
        obj, dest = args
        if s["손"] != obj:
            return f"{obj}을 들고 있지 않음"
        if dest not in places:
            return f"없는 놓는곳 {dest}"
        stand, door = places[dest]
        if s["로봇"] != stand:
            return f"로봇이 {stand}에 없음"
        if door and s["문"][door] != "열림":
            return f"{door}이 닫혀 있음"
        s["물건"][obj], s["손"] = dest, None
    elif kind == "set":
        dev, cmd = args[0], args[1]
        spec = devices.get(dev, {}).get("명령", {}).get(cmd)
        if spec is None:
            return f"{dev}에 {cmd} 명령이 없음"
        needs_input = "<입력>" in spec["바뀜"].values()
        if needs_input != (len(args) == 3):
            return f"{dev} {cmd} 명령의 입력이 맞지 않음"
        for door, want in spec.get("조건", {}).get("문", {}).items():
            if s["문"][door] != want:
                return f"{door}이 {want}이어야 함"
        for d2, kv in spec.get("조건", {}).get("가전", {}).items():
            for k, v in kv.items():
                if s["가전"].get(d2, {}).get(k) != v:
                    return f"{d2} {k}이 {v}이어야 함"
        for k, v in spec["바뀜"].items():
            s["가전"].setdefault(dev, {})[k] = args[2] if v == "<입력>" else v
    elif kind == "read":
        dev, attr = args
        if attr not in devices.get(dev, {}).get("조회", []):
            return f"{dev}의 {attr} 조회 불가"
    elif kind == "wait":
        dev, attr, val = args
        if attr not in devices.get(dev, {}).get("신호", []):
            return f"{dev}가 {attr} 신호를 보내지 않음"
        if not (attr == "운전" and val == "멈춤" and s["가전"].get(dev, {}).get("운전") == "작동 중"):
            return "저절로 참이 될 수 없는 조건"
        s["가전"][dev]["운전"] = "멈춤"
    return None


def goal_met(goal, s):
    if any(s["물건"].get(o) != v for o, v in goal.get("물건", {}).items()):
        return False
    for g in goal.get("종류자리", []):
        if not any(o.startswith(g["종류"] + "_") and v == g["자리"] for o, v in s["물건"].items()):
            return False
    if any(s["물건상태"].get(o, {}).get(k) != v for o, kv in goal.get("물건상태", {}).items() for k, v in kv.items()):
        return False
    if any(s["문"].get(d) != v for d, v in goal.get("문", {}).items()):
        return False
    if any(s["가전"].get(d, {}).get(k) != v for d, kv in goal.get("가전", {}).items() for k, v in kv.items()):
        return False
    if any(s["사람"].get(k) != v for k, v in goal.get("사람", {}).items()):
        return False
    return all(s["자리상태"].get(p) == v for p, v in goal.get("자리상태", {}).items())


def execute(prob, seq, home, world=None):
    """순서를 실제처럼 따라간다. 살펴보기에서 물건이 없다고 나오면 로봇은 거기서 멈추고 할 수 없다고 알린다."""
    s = start_state(home, prob)
    absent = set()
    for o, loc in (world or {}).get("사실", {}).items():
        if loc == "없음":
            absent.add(o)
        else:
            s["물건"][o] = loc
    for i, a in enumerate(seq, 1):
        err = step(a, s, home, absent)
        if err:
            return {"끝": "실패", "단계": i, "까닭": err}
        if a[0] == "look" and a[2] in absent:
            return {"끝": "없음 확인 후 멈춤", "단계": i, "까닭": f"{a[2]}이 없음"}
    return {"끝": "목표 달성" if goal_met(prob["목표"], s) else "목표 못 이룸", "단계": len(seq), "까닭": ""}
