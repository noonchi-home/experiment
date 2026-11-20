"""방법 3: 계획기. 지금 모습에서 출발해, 조건표상 할 수 있는 원자 행동을 하나씩 붙여 보며
목표 모습이 나올 때까지 짧은 순서부터 찾는다(너비 우선 찾기). LLM을 부르지 않는다.
자리를 모르는 물건은 살펴보기(look)를 넣고, 살펴보면 있다고 가정해 순서를 짠다.
실행 때 없다고 나오면 로봇은 멈추고 할 수 없다고 알린다(world.execute).
"""
import copy
import json
import pathlib
import sys
import time
from collections import deque

from world import Home, load_home, load_problems, start_state, step, goal_met

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"
FULL_LIMIT = 300_000  # 관련 없는 곳까지 넓혀 찾을 때 볼 모습 수 상한


def impossible_reason(prob, home, s):
    """어떤 행동으로도 만들 수 없는 목표 사실이 있으면 그 까닭을 돌려준다."""
    goal = prob["목표"]
    known = set(s["물건"]) | set(s["모름"])
    for o, p in goal.get("물건", {}).items():
        if o not in known:
            return f"{o}이 집에 없음"
        if p not in home.places and s["물건"].get(o) != p:
            return f"{p}은 물건을 놓을 수 있는 곳이 아님"
    for g in goal.get("종류자리", []):
        if not any(o.startswith(g["종류"] + "_") for o in known):
            return f"{g['종류']}이 집에 없음"
    for o, kv in goal.get("물건상태", {}).items():
        for k, v in kv.items():
            if s["물건상태"].get(o, {}).get(k) != v:
                return f"{o}의 {k}을 {v}으로 바꾸는 행동이 없음"
    for k, v in goal.get("사람", {}).items():
        if s["사람"].get(k) != v:
            return f"사람의 {k}을 바꾸는 행동이 없음"
    for p, v in goal.get("자리상태", {}).items():
        if s["자리상태"].get(p) != v:
            return f"{p}의 상태를 바꾸는 행동이 없음"
    for dev, kv in goal.get("가전", {}).items():
        cmds = home.devices.get(dev, {}).get("명령", {})
        for k, v in kv.items():
            if s["가전"].get(dev, {}).get(k) == v:
                continue
            by_cmd = any(spec["바뀜"].get(k) in (v, "<입력>") for spec in cmds.values())
            by_wait = k == "운전" and v == "멈춤" and "운전" in home.devices.get(dev, {}).get("신호", [])
            if not (by_cmd or by_wait):
                return f"{dev}의 {k}을 {v}으로 바꾸는 명령이 없음"
    return None


def relevant_stands(prob, home, s):
    """목표에 관계된 물건·자리·문이 있는 서는곳만 고른다."""
    goal = prob["목표"]
    types = [g["종류"] for g in goal.get("종류자리", [])]
    objs = set(goal.get("물건", {})) | {o for o in s["물건"] if any(o.startswith(t + "_") for t in types)}
    objs |= set(s["모름"]) | ({s["손"]} if s["손"] else set())
    places = {s["물건"][o] for o in objs if s["물건"].get(o) in home.places}
    places |= {p for p in goal.get("물건", {}).values() if p in home.places}
    places |= {g["자리"] for g in goal.get("종류자리", []) if g["자리"] in home.places}
    for cands in s["모름"].values():
        places |= {p for p in cands if p in home.places}
    doors = {home.places[p][1] for p in places if home.places[p][1]} | set(goal.get("문", {}))
    for dev in goal.get("가전", {}):
        for spec in home.devices.get(dev, {}).get("명령", {}).values():
            doors |= set(spec.get("조건", {}).get("문", {}))
    for d in list(doors):
        gap = home.doors[d][2]
        if gap:
            places.add(gap)
    stands = {home.places[p][0] for p in places} | {home.doors[d][0] for d in doors} | {s["로봇"]}
    return stands


def candidates(prob, home, s, stands):
    here = s["로봇"]
    acts = [["go", st] for st in sorted(stands) if st != here]
    for d, (stand, _, _) in home.doors.items():
        if stand == here:
            acts += [["open", d], ["close", d]]
    local = [p for p, (stand, _) in home.places.items() if stand == here]
    if s["손"] is None:
        acts += [["pick", o] for o, loc in s["물건"].items() if loc in local and o not in s["모름"]]
    else:
        acts += [["place", s["손"], p] for p in local]
    for o, cands in s["모름"].items():
        acts += [["look", p, o] for p in cands if p in local]
    goal_dev = prob["목표"].get("가전", {})
    for dev, spec in home.devices.items():
        # 목표에 없는 가전은 조작하지 않는다(예: 세탁 중인 세탁기를 정지시켜 문을 여는 순서를 막는다)
        for cmd, c in (spec.get("명령", {}) if dev in goal_dev else {}).items():
            if "<입력>" in c["바뀜"].values():
                for k, v in c["바뀜"].items():
                    if v == "<입력>" and k in goal_dev.get(dev, {}):
                        acts.append(["set", dev, cmd, goal_dev[dev][k]])
            else:
                acts.append(["set", dev, cmd])
        if "운전" in spec.get("신호", []) and s["가전"].get(dev, {}).get("운전") == "작동 중":
            acts.append(["wait", dev, "운전", "멈춤"])
    return acts


def key(s):
    return (s["로봇"], s["손"], tuple(sorted(s["물건"].items())), tuple(sorted(s["문"].items())),
            tuple(sorted((d, k, v) for d, kv in s["가전"].items() for k, v in kv.items())), tuple(sorted(s["모름"])))


def search(prob, home, s0, stands, limit):
    """너비 우선 찾기. (순서, 본 모습 수) 또는 (None, 본 모습 수)."""
    if goal_met(prob["목표"], s0):
        return [], 1
    seen, queue = {key(s0)}, deque([(s0, [])])
    while queue:
        s, seq = queue.popleft()
        for a in candidates(prob, home, s, stands):
            t = copy.deepcopy(s)
            if step(a, t, home, set()):
                continue
            if a[0] == "look" and a[2] not in t["물건"]:
                t["물건"][a[2]] = a[1]  # 살펴보면 있다고 가정한다
            k = key(t)
            if k in seen:
                continue
            if goal_met(prob["목표"], t):
                return seq + [a], len(seen)
            seen.add(k)
            if len(seen) >= limit:
                return None, len(seen)
            queue.append((t, seq + [a]))
    return None, len(seen)


def plan(prob, home_json):
    home = Home(home_json, prob.get("집_바꿈"))
    s0 = start_state(home, prob)
    why = impossible_reason(prob, home, s0)
    if why:
        return {"할수있음": False, "순서": [], "까닭": why, "본 모습 수": 0}
    seq, n = search(prob, home, s0, relevant_stands(prob, home, s0), 10**9)
    if seq is None:  # 관계된 곳만으로 못 찾으면 집 전체로 넓혀 다시 찾는다
        seq, n2 = search(prob, home, s0, set(home.stands), FULL_LIMIT)
        n += n2
        if seq is None:
            why = "집 전체를 찾아도 목표 모습이 나오지 않음" if n2 < FULL_LIMIT else f"찾기 상한({FULL_LIMIT}) 도달"
            return {"할수있음": False, "순서": [], "까닭": why, "본 모습 수": n}
    return {"할수있음": True, "순서": seq, "까닭": "", "본 모습 수": n}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    which = sys.argv[1] if len(sys.argv) > 1 else "본"
    probs = load_problems("문제.jsonl" if which == "본" else "연습문제.jsonl")
    home_json = load_home()
    DATA.mkdir(parents=True, exist_ok=True)
    out = DATA / f"계획기_{which}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for p in probs:
            t0 = time.perf_counter()
            r = plan(p, home_json)
            r.update({"id": p["id"], "방법": "계획기", "판": "-", "반복": 1, "초": round(time.perf_counter() - t0, 4)})
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(p["id"], "할 수 있음" if r["할수있음"] else "할 수 없음", len(r["순서"]), r["까닭"], f"{r['초']}초")
    print("저장:", out)


if __name__ == "__main__":
    main()
