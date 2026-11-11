"""채점기: 방법마다 낸 답을 정답과 맞춰 본다. 정답 파일은 이 파일만 읽는다.
사용: python -X utf8 score.py [본|연습]  →  data/결과표_<문제>.md
"""
import collections
import json
import pathlib
import statistics
import sys

from world import ROOT, Home, execute, load_home, load_problems

ANS_DIR = ROOT / "실험정답" / "원자행동조합_정답"
DATA = pathlib.Path(__file__).resolve().parents[1] / "data"
# DeepSeek 단가(달러/100만 토큰). 돌리기 전에 공식 단가 페이지에서 확인한 값으로 채운다.
PRICE = {  # 피크 시간 단가(2026-11-11 확인, https://api-docs.deepseek.com/quick_start/pricing). 비피크는 절반이라 이 값은 최대치다.
    "deepseek-flash": {"입력": 0.3, "캐시": 0.006, "출력": 1.2},
    "deepseek-v4-pro": {"입력": 1.32, "캐시": 0.044, "출력": 3.96},
}


def load_jsonl(path):
    return [json.loads(r) for r in path.read_text(encoding="utf-8").splitlines() if r.strip()]


def judge(prob, ans, out, home_json):
    """답 하나를 채점한다. 갈래: 성공·할 수 없음 맞힘·두 세계 모두 맞음·못 하는데 한다고 함·
    할 수 있는데 못 한다고 함·실행 실패·형식 오류."""
    home = Home(home_json, prob.get("집_바꿈"))
    if out.get("오류"):
        return {"맞음": False, "갈래": "형식 오류", "까닭": out["오류"]}
    claim, seq, truth = out["할수있음"], out["순서"], ans["할수있음"]
    if truth == "아니오":
        if claim is False:
            return {"맞음": True, "갈래": "할 수 없음 맞힘", "까닭": ""}
        r = execute(prob, seq, home)
        return {"맞음": False, "갈래": "못 하는데 한다고 함", "까닭": f"{r['끝']} {r['까닭']}".strip()}
    if claim is False:
        return {"맞음": False, "갈래": "할 수 있는데 못 한다고 함", "까닭": out.get("까닭", "")}
    if truth == "예":
        r = execute(prob, seq, home)
        if r["끝"] == "목표 달성":
            return {"맞음": True, "갈래": "성공", "단계 수": len(seq), "까닭": ""}
        return {"맞음": False, "갈래": "실행 실패", "까닭": f"{r['단계']}단계 {r['끝']} {r['까닭']}".strip()}
    fails = []
    for w in ans["숨은세계"]:
        r = execute(prob, seq, home, w)
        want = "목표 달성" if w["끝"] == "목표 달성" else "없음 확인 후 멈춤"
        if r["끝"] != want:
            fails.append(f"[{w['이름']}] {r['단계']}단계 {r['끝']} {r['까닭']}".strip())
    if fails:
        return {"맞음": False, "갈래": "실행 실패", "까닭": " / ".join(fails)}
    return {"맞음": True, "갈래": "두 세계 모두 맞음", "단계 수": len(seq), "까닭": ""}


def cost(o):
    u, p = o.get("토큰") or {}, PRICE.get(o.get("모델"))
    if not u or not p:
        return None
    hit = u.get("캐시", 0)
    return ((u.get("입력", 0) - hit) * p["입력"] + hit * p["캐시"] + u.get("출력", 0) * p["출력"]) / 1e6


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    which = sys.argv[1] if len(sys.argv) > 1 else "본"
    probs = {p["id"]: p for p in load_problems("문제.jsonl" if which == "본" else "연습문제.jsonl")}
    answers = {a["id"]: a for a in load_jsonl(ANS_DIR / ("정답.jsonl" if which == "본" else "연습정답.jsonl"))}
    home_json = load_home()
    shortest = {r["id"]: len(r["순서"]) for r in load_jsonl(DATA / f"계획기_{which}.jsonl") if r["할수있음"]}
    groups = collections.defaultdict(list)
    for f in sorted(DATA.glob(f"*_{which}*.jsonl")):
        last = {(o["id"], o["반복"]): o for o in load_jsonl(f)}  # 다시 돌린 줄이 있으면 마지막 것만 쓴다
        for o in last.values():
            j = judge(probs[o["id"]], answers[o["id"]], o, home_json)
            groups[(o["방법"], o["판"], o.get("모델", "-"), o.get("생각", "-"))].append((o, j))

    truth = collections.Counter(a["할수있음"] for a in answers.values())
    head = ["# 원자 행동 조합 실험 결과" + ("" if which == "본" else " (연습 문제)"), "",
            f"문제 {len(probs)}개: 할 수 있음 {truth['예']}, 할 수 없음 {truth['아니오']}, 살펴봐야 앎 {truth['살펴봐야 앎']}. "
            "숫자는 반복마다 센 값의 평균이다.", "",
            "| 방법 | 판 | 모델 | 반복 | 전체 맞힘 | 할 수 있는 일 성공 | 할 수 없는 일 맞힘 | 못 하는데 한다고 함 | 할 수 있는데 못 한다고 함 | 실행 실패 | 군더더기(단계) | 반복마다 결과가 바뀐 문제 | 비용(최대 달러) | 시간(초) |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    detail = collections.defaultdict(dict)
    for (method, variant, model, think), rows in sorted(groups.items()):
        runs = sorted({o["반복"] for o, _ in rows})
        n = len(runs)

        def per_run(pred):
            return statistics.mean(sum(1 for o, j in rows if o["반복"] == r and pred(o, j)) for r in runs)

        ok_all = per_run(lambda o, j: j["맞음"])
        ok_can = per_run(lambda o, j: j["맞음"] and answers[o["id"]]["할수있음"] != "아니오")
        ok_cant = per_run(lambda o, j: j["맞음"] and answers[o["id"]]["할수있음"] == "아니오")
        false_yes = per_run(lambda o, j: j["갈래"] == "못 하는데 한다고 함")
        false_no = per_run(lambda o, j: j["갈래"] == "할 수 있는데 못 한다고 함")
        failed = per_run(lambda o, j: j["갈래"] in ("실행 실패", "형식 오류"))
        extra = [j["단계 수"] - shortest[o["id"]] for o, j in rows if j.get("단계 수") is not None and o["id"] in shortest]
        by_prob = collections.defaultdict(set)
        for o, j in rows:
            by_prob[o["id"]].add(j["맞음"])
            detail[o["id"]][f"{method}·{variant}"] = detail[o["id"]].get(f"{method}·{variant}", 0) + (1 if j["맞음"] else 0)
        unstable = sum(1 for v in by_prob.values() if len(v) > 1)
        costs = [c for o, _ in rows if (c := cost(o)) is not None]
        secs = sum(o.get("초", 0) for o, _ in rows)
        name = f"{method}" + ("" if think == "-" else f"(생각 {think})")
        head.append(f"| {name} | {variant} | {model} | {n} | {ok_all:.1f}/{len(probs)} | {ok_can:.1f}/{truth['예'] + truth['살펴봐야 앎']} | "
                    f"{ok_cant:.1f}/{truth['아니오']} | {false_yes:.1f} | {false_no:.1f} | {failed:.1f} | "
                    f"{(statistics.mean(extra) if extra else 0):.2f} | {unstable} | "
                    f"{(f'{sum(costs):.3f}' if costs else '-')} | {secs:.1f} |")
    cols = sorted({k for v in detail.values() for k in v})
    reps = {f"{m}·{v}": len({o['반복'] for o, _ in rows}) for (m, v, _, _), rows in groups.items()}
    head += ["", "## 문제별 맞힌 횟수", "", "| 번호 | 할 일 | 정답 | " + " | ".join(cols) + " |", "|---|---|---|" + "---|" * len(cols)]
    for pid, p in probs.items():
        cells = " | ".join(f"{detail[pid].get(c, 0)}/{reps[c]}" for c in cols)
        head.append(f"| {pid} | {p['할일']} | {answers[pid]['할수있음']} | {cells} |")
    fails = ["", "## 틀린 답의 까닭 (방법마다 앞 30개)", ""]
    for key, rows in sorted(groups.items()):
        bad = [(o, j) for o, j in rows if not j["맞음"]][:30]
        if bad:
            fails.append(f"### {key[0]} · {key[1]}")
            fails += [f"- {o['id']} 반복 {o['반복']}: {j['갈래']} — {j['까닭']}" for o, j in bad]
            fails.append("")
    out = DATA / f"결과표_{which}.md"
    out.write_text("\n".join(head + fails) + "\n", encoding="utf-8")
    print("\n".join(head[:len(groups) + 6]))
    print("저장:", out)


if __name__ == "__main__":
    main()
