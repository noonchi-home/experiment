"""Coffee_man 시나리오를 여러 날 실행한다(API를 부르지 않는다). 하루 = 영상 관찰 기록(2초 창들) 한 번.

하루의 순서:
  1. FSM -> 트리거 검증·묶기(trigger_pomdp.compile_triggers). FSM이 바뀐 날마다 다시 한다.
  2. 스마트홈 허브(인덕션·식기세척기·냉장고)와 로봇에 가상으로 연결한다(noonchi/smarthome.py).
  3. 창마다: 트리거 POMDP로 믿음 갱신 -> 트리거가 서면 task POMDP가 20개 task 중 요청할 것을 고른다
     -> 허브·로봇에 요청한다(식기세척기 확인은 허브 응답에 따라 남은 시간 조회 / 내부 사진 요청).
  4. 하루가 끝나면 고른 task와 정답 task(data/Coffee_man/answer.json)를 비교해 믿음을 고치고,
     FSM 수정안을 믿음으로 반영·보류한다(noonchi/fsm_edit.py). 다음 날은 고친 FSM과 다시 검증한 트리거로 시작한다.

실행: python run_coffee.py [--case data/Coffee_man/live_qwen_rep1] [--hub dishwasher_running] [--days 3]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from noonchi import SmartHomeHub, VirtualRobot, load_frame  # noqa: E402
from noonchi.config import read_json  # noqa: E402
from noonchi.fsm_edit import BeliefGate, EditBelief, compare_with_answer, designed_rules, edited_fsm  # noqa: E402
from noonchi.lora import group_gain_cost  # noqa: E402
from noonchi.smarthome import execute  # noqa: E402
from noonchi.task_pomdp import TaskPOMDP, task_prior  # noqa: E402
from noonchi.trigger_pomdp import TriggerPOMDP, clock, compile_triggers  # noqa: E402


def load_scenario(d: Path) -> dict:
    sc = read_json(d / "scenario.json")
    spec = read_json(d / sc["task_specs_file"])
    return {"sc": sc, "tasks": read_json(d / sc["tasks_file"]), "fsm": read_json(d / sc["memory_files"]["fsm"]),
            "specs": [{**dict(zip(("gain", "cost"), group_gain_cost(t["group"]))), **t} for t in spec["tasks"]],
            "trig": read_json(d / sc["triggers_file"]), "hub": read_json(d / sc["hub_file"])}


def default_case(sc: dict) -> Path:
    found = sorted(p for p in (ROOT / sc["cases"]).iterdir() if (p / "frames").is_dir())
    if not found:
        raise SystemExit(f"no observation case in {sc['cases']}; run record_video_vlm.py first")
    return found[0]


def run_day(s: dict, fsm: dict, frames: list[dict], hub_state: dict, belief: EditBelief, log) -> dict:
    tasks = s["tasks"]
    triggers, issues = compile_triggers(fsm, tasks, s["trig"]["conditions"])
    hub, robot = SmartHomeHub(s["hub"], hub_state), VirtualRobot()
    link = {"hub": hub.connect(), "robot": robot.connect()}
    log(f"  connected: hub {sorted(link['hub']['devices'])}, robot ({link['robot']['can_do']})")
    log(f"  triggers: " + ("; ".join(f"{t['id']} -> tasks {t['tasks']}" for t in triggers) or "none"))
    for x in issues:
        log(f"  trigger check: [{x['state']}] {x['issue']} :: {x['rule'][:60]}")
    tp, chooser = TriggerPOMDP(triggers, s["trig"]), TaskPOMDP(tasks, s["specs"], belief)
    issued: dict[int, float] = {}
    windows, q_day = [], 0.0
    for f in frames:
        r = tp.step(f)
        act = "; ".join(p["activity"] for p in f["people"]) or "no one"
        trig = ", ".join(f"{t['id']} P{t['p']:.2f}/EV{t['ev']:+.2f}{' SET' if t['fired'] else ''}"
                         f"{' (one-frame: set)' if t['baseline'] else ''}" for t in r["triggers"]) or "no trigger"
        log(f"  {clock(f['time'])}  person {r['belief']['person']}, activity {r['belief']['activity']}  | {act[:50]}")
        log(f"            {trig}")
        row = {"time": f["time"], "belief": r["belief"], "triggers": r["triggers"], "chosen": []}
        for t in r["triggers"]:
            q_day = max(q_day, t["p"])
            if not t["fired"]:
                continue
            for c in chooser.decide(t["p"], hub):
                if c["chosen"]:
                    res = execute(tasks[c["task"]], s["specs"][c["task"]], hub, robot)
                    issued[c["task"]] = t["p"]
                    row["chosen"].append({**c, "trigger": t["id"], "result": res})
                    log(f"            -> task {c['task']} (P {c['p']:.2f}, EV {c['ev']:+.2f}) {tasks[c['task']]}")
                    if res.get("then"):
                        log(f"               {res['then']['because']} -> {res['then']['text']}")
        windows.append(row)
    return {"triggers": triggers, "trigger_issues": issues, "windows": windows, "issued": issued, "q_day": q_day,
            "hub_log": hub.log, "robot_log": robot.log}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=str(ROOT / "scenarios" / "Coffee_man"))
    ap.add_argument("--case", help="observation case folder (default: the first one in the scenario's cases)")
    ap.add_argument("--hub", default="dishwasher_running", help="hub.json variant for the start state")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "runs" / f"coffee-{datetime.now():%Y%m%d-%H%M%S}"))
    args = ap.parse_args()
    s = load_scenario(Path(args.scenario))
    tasks, fsm0, specs = s["tasks"], s["fsm"], s["specs"]
    case = Path(args.case) if args.case else default_case(s["sc"])
    frames = [load_frame(p) for p in sorted((case / "frames").glob("*.json"))]
    answer = set(read_json(ROOT / s["sc"]["answer_file"])["answer_tasks"])
    hub_state = s["hub"]["variants"][args.hub]

    start_trigger = s["trig"]["conditions"][0]
    designed = designed_rules(fsm0, tasks)
    prior = task_prior(fsm0, tasks, specs, read_json(ROOT / "config" / "fsm_edit.json")["prior"], start_trigger["state"])
    belief = EditBelief(len(tasks), designed, [x["gain"] for x in specs], [x["cost"] for x in specs], prior=prior)
    gate = BeliefGate(belief)
    candidates = {str(i): {"state": start_trigger["state"], "trigger": start_trigger["rule"]} for i in range(len(tasks))}
    enabled = set(designed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def log(text: str = "") -> None:
        print(text)
        lines.append(text)

    log(f"# Coffee_man: case {case.name}, hub start {args.hub}, answer tasks {sorted(answer)}")
    log("first belief per task (from the FSM): " + ", ".join(f"{i}:{p:.2f}" for i, p in prior.items()))
    days = []
    for day in range(1, args.days + 1):
        fsm = edited_fsm(fsm0, tasks, enabled, candidates)
        log(f"\n## day {day}  FSM rules: {sorted(enabled)}")
        d = run_day(s, fsm, frames, hub_state, belief, log)
        issued = set(d["issued"])
        log(f"  chosen {sorted(issued)} | answer {sorted(answer)} | right {sorted(issued & answer)}, "
            f"extra {sorted(issued - answer)}, missed {sorted(answer - issued)}")
        events, proposals = compare_with_answer(d["issued"], answer, d["q_day"], enabled, belief)
        new_enabled, decisions = gate.review(day, proposals, enabled, answer=lambda i: i in answer)
        log(f"  FSM edit proposals: {proposals or 'none'}")
        for x in decisions:
            log(f"    {x}")
        changed = new_enabled != enabled
        enabled = new_enabled
        fsm_next = edited_fsm(fsm0, tasks, enabled, candidates)
        if changed:
            trig_next, issues_next = compile_triggers(fsm_next, tasks, s["trig"]["conditions"])
            log(f"  FSM changed -> rules {sorted(enabled)}; triggers re-checked: "
                + ("; ".join(f"{t['id']} -> tasks {t['tasks']}" for t in trig_next) or "none")
                + (f" ({len(issues_next)} issue(s))" if issues_next else ", no issues"))
        else:
            log("  FSM kept")
        (out / f"fsm_day{day}.json").write_text(json.dumps(fsm_next, ensure_ascii=False, indent=2), encoding="utf-8")
        days.append({"day": day, "rules": sorted(d["triggers"][0]["tasks"]) if d["triggers"] else [],
                     "chosen": sorted(issued), "events": events, "proposals": proposals, "decisions": decisions,
                     "rules_after": sorted(enabled), "belief": {i: round(p, 3) for i, p in belief.p.items()},
                     "triggers": d["triggers"], "trigger_issues": d["trigger_issues"], "windows": d["windows"],
                     "hub_log": d["hub_log"], "robot_log": d["robot_log"]})
    summary = ["", "| day | chosen | right | extra | missed | FSM rules after |", "|---|---|---|---|---|---|"]
    summary += [f"| {x['day']} | {x['chosen']} | {sorted(set(x['chosen']) & answer)} | {sorted(set(x['chosen']) - answer)} "
                f"| {sorted(answer - set(x['chosen']))} | {x['rules_after']} |" for x in days]
    for t in summary:
        log(t)
    (out / "days.json").write_text(json.dumps(days, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "coffee.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nsaved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
