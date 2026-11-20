"""방법 1(바로 맡기기)과 방법 2(FSM 먼저)를 DeepSeek로 돌린다. 돈이 드는 명령이다.
사용 예: python -X utf8 run_llm.py --방법 바로 --판 설명 --문제 연습 --반복 1 --모델 deepseek-flash --생각 켬
--미리보기를 주면 모델을 부르지 않고 첫 문제의 글과 글자 수만 보여 준다.
이미 저장된 (문제, 반복)은 건너뛰므로 끊겨도 이어서 돌릴 수 있다.
"""
import argparse
import json
import pathlib
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import prompts
from llm import chat, parse_json
from world import Home, load_home, load_problems

DATA = pathlib.Path(__file__).resolve().parents[1] / "data"


def valid(ans):
    if not isinstance(ans, dict) or not isinstance(ans.get("할수있음"), bool) or not isinstance(ans.get("순서"), list):
        return "할수있음(참·거짓)과 순서(목록)가 없음"
    if not all(isinstance(a, list) and all(isinstance(x, str) for x in a) for a in ans["순서"]):
        return "순서의 행동이 글자 목록이 아님"
    return None


def ask(messages, model, thinking, log):
    """한 번 묻고 json을 꺼낸다. 비었거나 json이 아니면 한 번 더 묻는다."""
    for attempt in (1, 2):
        r = chat(messages, model, thinking)
        log.append(r)
        ans = parse_json(r["글"])
        if ans is not None:
            return ans
    return None


def solve(prob, home_json, method, variant, model, thinking):
    home = Home(home_json, prob.get("집_바꿈"))
    log, rec = [], {}
    try:
        if method == "바로":
            ans = ask(prompts.direct_messages(prob, home, variant), model, thinking, log)
        else:
            fsm = ask(prompts.fsm_messages_1(prob, home, variant), model, thinking, log)
            rec["FSM"] = fsm
            ans = None if fsm is None else ask(
                prompts.fsm_messages_2(prob, home, variant, json.dumps(fsm, ensure_ascii=False)), model, thinking, log)
        err = "json을 읽지 못함" if ans is None else valid(ans)
        rec.update({"할수있음": ans.get("할수있음") if not err else None, "순서": ans.get("순서") if not err else [],
                    "까닭": (ans or {}).get("까닭", "") if isinstance(ans, dict) else "", "오류": err})
    except RuntimeError as e:
        rec.update({"할수있음": None, "순서": [], "까닭": "", "오류": f"호출 실패: {e}"})
    rec["원문"] = [r["글"] for r in log]
    rec["생각 글자 수"] = [len(r["생각"]) for r in log]
    rec["호출 수"] = len(log)
    rec["토큰"] = {k: sum(r["토큰"][k] for r in log) for k in ("입력", "캐시", "출력")}
    rec["초"] = round(sum(r["초"] for r in log), 2)
    rec["응답 모델"] = log[-1]["모델"] if log else None
    return rec


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--방법", choices=["바로", "FSM"], required=True)
    ap.add_argument("--판", choices=["설명", "조건표"], required=True)
    ap.add_argument("--문제", choices=["본", "연습"], default="연습")
    ap.add_argument("--반복", type=int, default=1)
    ap.add_argument("--모델", default="deepseek-flash")
    ap.add_argument("--생각", choices=["켬", "끔"], default="켬")
    ap.add_argument("--동시", type=int, default=4)
    ap.add_argument("--미리보기", action="store_true")
    a = ap.parse_args()
    probs = load_problems("문제.jsonl" if a.문제 == "본" else "연습문제.jsonl")
    home_json = load_home()
    if a.미리보기:
        p = probs[0]
        msgs = prompts.direct_messages(p, Home(home_json, p.get("집_바꿈")), a.판)
        print(msgs[0]["content"][:1500], "\n...\n", msgs[1]["content"])
        print("글자 수: 시스템", len(msgs[0]["content"]), "/ 문제", len(msgs[1]["content"]))
        return
    DATA.mkdir(parents=True, exist_ok=True)
    out = DATA / f"{a.방법}_{a.판}_{a.문제}_{a.모델}_생각{a.생각}.jsonl"
    done = set()
    if out.exists():
        done = {(o["id"], o["반복"]) for o in map(json.loads, out.read_text(encoding="utf-8").splitlines()) if o.get("오류") is None or not str(o["오류"]).startswith("호출 실패")}
    jobs = [(p, r) for r in range(1, a.반복 + 1) for p in probs if (p["id"], r) not in done]
    lock = threading.Lock()

    def work(job):
        p, r = job
        rec = solve(p, home_json, a.방법, a.판, a.모델, a.생각 == "켬")
        rec = {"id": p["id"], "방법": a.방법, "판": a.판, "반복": r, "모델": a.모델, "생각": a.생각, **rec}
        with lock, open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(p["id"], r, "오류:" + rec["오류"] if rec["오류"] else ("할 수 있음" if rec["할수있음"] else "할 수 없음"),
              len(rec["순서"]), rec["토큰"], f"{rec['초']}초", flush=True)

    with ThreadPoolExecutor(a.동시) as ex:
        list(ex.map(work, jobs))
    print("저장:", out, "/ 새로 푼 수:", len(jobs))


if __name__ == "__main__":
    main()
