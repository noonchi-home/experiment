"""채점기 검사: 정답의 예시 순서는 모두 맞음으로, 일부러 틀린 답은 틀림으로 채점하는지 본다. 모델을 부르지 않는다."""
import sys

from score import ANS_DIR, DATA, judge, load_jsonl
from world import load_home, load_problems

sys.stdout.reconfigure(encoding="utf-8")
probs = {p["id"]: p for p in load_problems()}
answers = {a["id"]: a for a in load_jsonl(ANS_DIR / "정답.jsonl")}
home = load_home()
bad = []


def expect(pid, out, want_ok, want_kind=None):
    j = judge(probs[pid], answers[pid], out, home)
    if j["맞음"] != want_ok or (want_kind and j["갈래"] != want_kind):
        bad.append((pid, out, j))


for pid, a in answers.items():
    if a["할수있음"] == "예":
        expect(pid, {"할수있음": True, "순서": a["예시순서"]}, True, "성공")
        expect(pid, {"할수있음": False, "순서": []}, False, "할 수 있는데 못 한다고 함")
    elif a["할수있음"] == "아니오":
        expect(pid, {"할수있음": False, "순서": []}, True, "할 수 없음 맞힘")
        expect(pid, {"할수있음": True, "순서": [["go", "식탁_앞"]]}, False, "못 하는데 한다고 함")
    else:
        seq = next(w["예시"] for w in a["숨은세계"] if w["끝"] == "목표 달성")
        expect(pid, {"할수있음": True, "순서": seq}, True, "두 세계 모두 맞음")
        no_look = [x for x in seq if x[0] != "look"]
        expect(pid, {"할수있음": True, "순서": no_look}, False, "실행 실패")
expect("A14", {"할수있음": True, "순서": [["go", "냉장고_앞"], ["pick", "맥주캔_1"]]}, False, "실행 실패")
expect("C01", {"할수있음": True, "순서": [["go", "냉장고_앞"], ["open", "냉장고_문"]]}, False, "실행 실패")
expect("A14", {"할수있음": True, "순서": [["fly", "소파_앞"]]}, False, "실행 실패")
expect("A14", {"오류": "JSON을 읽지 못함"}, False, "형식 오류")
for o in load_jsonl(DATA / "계획기_본.jsonl"):
    expect(o["id"], o, True)
print("검사 실패" if bad else "채점기 검사: 모두 통과", len(bad))
for b in bad:
    print(b)
