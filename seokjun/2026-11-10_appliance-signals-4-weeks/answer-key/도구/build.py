"""평가자 자료 생성. 원본 날짜 폴더를 하루씩 열어 전날 상태를 적용한다."""
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
import argparse
import json

import morning_gold
import day_gold
import evening_gold
from learning import classify, find_actions, group_first, matches, time_case
from source import COMMON_GUARDS, DEFAULT_INPUT, ROOT, Day, clock, seconds, write_jsonl


MODULES = (morning_gold, day_gold, evening_gold)
RULES = {k:v for mod in MODULES for k,v in mod.RULES.items()}
ACTIONS = {k:v for mod in MODULES for k,v in mod.ACTIONS.items()}
assert len(RULES) == sum(len(mod.RULES) for mod in MODULES)
LABEL = {"가능":"실행", "확인필요":"대기", "위험":"대기", "선행":"취소", "불필요":"취소"}


def available(id, prior, guards, route):
    if RULES[id][3] == "고정안전":
        return route == "사건"
    return any(r["경로"] == route and matches(r["조건"], guards) for r in prior.get(id, {}).get("활성", []))


def event_record(day, row, group=None):
    return {"날짜": day.date, "규칙ID":row["id"], "기회시각":clock(row["t"]),
            "분류":"첫 기회" if group is None else "60분 안의 반복",
            "대표시각":clock(row["t"] if group is None else group), "조건":row["guards"], "사후결과":row["result"],
            "사후판독이유":row["reason"],"근거":[day.evidence(t) for t in row["evidence"]]}


def retrospective(kind, decision, result):
    if kind in ("관찰전용","고정안전"):
        return "장면·안전 기준을 직접 대조"
    if result == "관찰 불가":
        return "자연행동 판독 불가"
    if decision == "실행":
        return {"함":"뒤의 자연행동과 일치", "하지 않음":"뒤의 자연행동과 불일치·오개입 후보",
                "이미 함":"중복 개입 후보"}[result]
    if decision == "취소":
        return "이미 했거나 사람이 맡은 동작과 대조"
    return "뒤의 자연행동은 판단 시점 이후 자료"


def run_day(day, event_rows, repeated, prior, action_instances):
    attempts = [(r,"사건",False) for r in event_rows] + [(r,"사건",True) for r,_ in repeated]
    for key, info in prior.items():
        for rule in info["활성"]:
            if rule["경로"] == "시각":
                t = seconds(rule["시각"])
                related = [r for r in event_rows if r["id"] == key]
                case = time_case(day,key,t,action_instances[key][day.date],ACTIONS[key][2],related)
                attempts.append((case,"시각",False))
    points = defaultdict(list)
    for row, route, duplicate in sorted(attempts, key=lambda a: a[0]["t"]):
        key = row["id"]
        name, _, act, kind, _ = RULES[key]
        enabled = available(key, prior, row["guards"], route)
        for t, state, reason in row["checks"]:
            if duplicate:
                judgment, reason = "미개입", "같은 시작 신호의 첫 기회로부터 60분 이내. 새 도움을 시작하지 않음"
            elif kind == "관찰전용":
                judgment, reason = "미개입", "관찰 전용 장면. " + reason
            elif not enabled:
                judgment = "미개입"
                reason = ("전날 활성 규칙에 맞는 시작 조건이 없음. " if prior.get(key,{}).get("활성") else
                          "전날 밤까지 이 도움을 시작할 규칙이 확정되지 않음. ") + reason
            else:
                judgment = LABEL[state]
            points[(t,act)].append({"규칙ID":key,"규칙이름":name,"경로":route,"기회시각":clock(row["t"]),
                                    "판정":judgment,"이유":reason,"현재확인":state,
                                    "사후자연결과":row["result"],"사후대조":retrospective(kind,judgment,row["result"])})
            if judgment in ("취소","실행","미개입"):
                break
    records = []
    for (t,act), items in sorted(points.items()):
        # 동일 시각·행동은 한 번 채점한다. 명확한 사용자 선행·위험은 다른 시작 신호보다 우선한다.
        priorities = {"취소":0,"실행":1,"대기":2,"미개입":3}
        def priority(p):
            return -1 if p["판정"] == "대기" and p["현재확인"] == "위험" else priorities[p["판정"]]
        best = min(items,key=priority)
        records.append({"날짜":day.date,"시각":clock(t),"행동":act,"예상판정":best["판정"],"이유":best["이유"],
                        "전날밤":(date.fromisoformat(day.date)-timedelta(days=1)).isoformat(),
                        "규칙ID":sorted({i["규칙ID"] for i in items}),"근거":day.evidence(t),"세부":items})
    return records


def build(source, target):
    target.mkdir(parents=True, exist_ok=True)
    days, history, actions = [], defaultdict(list), defaultdict(dict)
    nights, events, decisions, signals, manifest = [],[],[],[],[]
    prior, signal_memory = {}, {}
    for folder in sorted(source.iterdir()):
        if not folder.is_dir():
            continue
        day = Day(folder)
        day.prior_signals = signal_memory.copy()
        days.append(day)
        rows = [r for mod in MODULES for r in mod.cases(day)]
        for row in rows:
            assert row["id"] in RULES and all(g in RULES[row["id"]][4] for g in row["guards"]), (row["id"],row["guards"])
            row["guards"] = {**day.guards(row["t"]), **row["guards"]}
        first, repeated = group_first(rows)
        for key,spec in ACTIONS.items():
            actions[key][day.date] = find_actions(day,spec)
        for row in first:
            history[row["id"]].append(row)
            events.append(event_record(day,row))
        for row,t in repeated:
            events.append(event_record(day,row,t))
        today = run_day(day,first,repeated,prior,actions)
        decisions.extend(today)
        by_t, related = defaultdict(list), defaultdict(set)
        for r in today:
            by_t[r["시각"]].append({"행동":r["행동"],"판정":r["예상판정"]})
        for r in rows:
            for t in r["evidence"]:
                related[clock(t)].add(r["id"])
        for r in day.signals:
            signals.append({**{k:v for k,v in r.items() if k != "sec"},"날짜":day.date,
                            "동시각판정":by_t[r["시각"]],"근거로참조한규칙":sorted(related[r["시각"]])})
        current = {k:classify(k,spec,history[k],days,ACTIONS.get(k),actions.get(k,{}),prior.get(k)) for k,spec in RULES.items()}
        next_date = (date.fromisoformat(day.date)+timedelta(days=1)).isoformat()
        for k,r in current.items():
            old = prior.get(k,{}).get("활성",[])
            if r["종류"] == "고정안전":
                change = "설계 고정"
            elif old == r["활성"]:
                change = "유지" if old else "미채택"
            else:
                change = "신규" if not old else "변경"
            nights.append({"날짜":day.date,"다음적용일":next_date,"변화":change,**r})
        manifest.append({"날짜":day.date,"원본SHA256":day.hashes,"신호":len(day.signals),"관찰":len(day.obs)})
        for row in day.signals:
            signal_memory[row["기기"],row["항목"]] = {**row,"날짜":day.date}
        prior = current
    write_jsonl(target / "밤별규칙.jsonl", nights)
    write_jsonl(target / "시각별판단.jsonl", decisions)
    write_jsonl(target / "원본근거와기회.jsonl", events)
    write_jsonl(target / "전체신호색인.jsonl", signals)
    write_jsonl(target / "원본지문.jsonl", manifest)
    return nights, decisions, events, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=Path, default=ROOT / "채점자료")
    args = parser.parse_args()
    build(args.input,args.out)
