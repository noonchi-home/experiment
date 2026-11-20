import json
import math
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import logprob_reliability as base  # noqa: E402  (main() guarded; provides post() with key scrubbing)
from ip_scenes import SCENES  # noqa: E402

OUT = os.path.join(HERE, "ip_run_raw.json")
MODEL = "gpt-6.1-terra"
PRICE_IN, PRICE_OUT = 1.0 / 1e6, 5.0 / 1e6
METHODS = {"ga": {"warn": False, "threshold": 30.0}, "ga_warn": {"warn": True, "threshold": 40.0}}
MAX_REGEN = 3
WORKERS_PER_METHOD = 3
WARN = "IMPORTANT: You have been consistently overconfident in past estimates."

P1 = (
    "You are a robot that helps people at home. Below is the record observed so far.\n\n"
    "[Observation record]\n{pre}\n\n"
    "[What the robot is about to do, and why]\n{robot}\nRule behind this action: {rule}\n\n"
    "[Task]\n"
    "List candidate states of mind this user might have at the moment the robot does this.\n"
    "- A state of mind means what the user wants, or why they would act a certain way. Write states of mind, not actions.\n"
    "- Give up to 10 candidates that do not overlap in meaning.\n"
    "- Write each candidate as one sentence.\n"
    "- Output only a single JSON array and nothing else. Example: [\"…\", \"…\"]"
)
P2 = (
    "You are a robot that helps people at home. Below is the record observed so far.\n\n"
    "[Observation record]\n{record}\n\n"
    "[Why the robot did this]\nRule behind this action: {rule}\n\n"
    "[Assume this is the user's state of mind]\n{cand}\n\n"
    "[Next observation]\n{current}\n\n"
    "Assuming this state of mind, how likely is the next observation?\n"
    "0 means it would never happen, and 100 means it would certainly happen.\n"
    "Output only a single integer from 0 to 100."
)
P3 = (
    "You are a robot that helps people at home. Below is the record observed so far.\n\n"
    "[Observation record]\n{record}\n\n"
    "[Why the robot did this]\nRule behind this action: {rule}\n\n"
    "[Candidate states of mind already considered]\n{existing}\n\n"
    "[Task]\n"
    "The candidates already considered do not explain the last line well.\n"
    "Propose new candidate states of mind that can explain the entire record so far.\n"
    "- Give up to 10 new candidates that do not overlap in meaning with the ones already considered.\n"
    "- A state of mind means what the user wants, or why they would act a certain way. Write states of mind, not actions.\n"
    "- Write each candidate as one sentence.\n"
    "- Output only a single JSON array and nothing else."
)

usage_total = {"in": 0, "out": 0, "calls": 0, "errors": 0}
LOCK = threading.Lock()


def call(messages, max_tokens, want_logprobs):
    body = {"model": MODEL, "reasoning_effort": "none", "max_completion_tokens": max_tokens, "messages": messages}
    if want_logprobs:
        body["logprobs"] = True
        body["top_logprobs"] = 5
    for attempt in range(4):
        data, err = base.post(base.OPENAI_URL, "OPENAI_API_KEY", body)
        if not err:
            u = data.get("usage", {})
            with LOCK:
                usage_total["in"] += u.get("prompt_tokens") or 0
                usage_total["out"] += u.get("completion_tokens") or 0
                usage_total["calls"] += 1
            return data, None
        if not any(s in err for s in ("HTTP 429", "HTTP 5", "Timeout", "URLError", "RemoteDisconnected")):
            break
        time.sleep(2 ** attempt)
    with LOCK:
        usage_total["errors"] += 1
    return None, err


def parse_list(text):
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return [s.strip() for s in arr if isinstance(s, str) and s.strip()]


def gen_candidates(prompt):
    for _ in range(2):
        data, err = call([{"role": "user", "content": prompt}], 1200, False)
        if err:
            return None, err
        arr = parse_list(data["choices"][0]["message"].get("content"))
        if arr is not None:
            return arr[:10], None
    return None, "could not parse candidate list"


def number_ev(top):
    num_p = {}
    for t in top:
        tok = t["token"].strip()
        if tok.isdigit() and 0 <= int(tok) <= 100:
            num_p[int(tok)] = num_p.get(int(tok), 0.0) + math.exp(t["logprob"])
    mass = sum(num_p.values())
    return sum(k * p for k, p in num_p.items()) / mass if mass > 0 else None


def score(scene, rec_lines, current, cand, warn):
    prompt = P2.format(record="\n".join(rec_lines), rule=scene["rule"], cand=cand, current=current)
    if warn:
        prompt = WARN + "\n" + prompt
    data, err = call([{"role": "user", "content": prompt}], 8, True)
    if err:
        return {"error": err}
    content = data["choices"][0]["message"].get("content") or ""
    m = re.match(r"\s*(\d{1,3})", content)
    said = int(m.group(1)) if m else None
    lp = data["choices"][0].get("logprobs")
    ev = number_ev(lp["content"][0].get("top_logprobs", [])) if lp and lp.get("content") else None
    if ev is None and said is not None:
        ev = float(said)
    return {"said": said, "ev": ev, "answer": content}


def split_scene(scene):
    lines = scene["lines"]
    who = [re.match(r"^\S+\s+(User|Robot|Friend|Roommate)\b", ln).group(1) for ln in lines]
    r = who.index("Robot")
    return lines[:r], lines[r], lines[r + 1:], who[r + 1:]


def run_method(scene, pre, robot, after, after_who, init_cands, method):
    cfg = METHODS[method]
    cands = list(init_cands)
    scores = {}  # (cand_idx, after_idx) -> result
    regens = []
    user_idx = [i for i, w in enumerate(after_who) if w == "User"]

    def rec_upto(i):  # record lines shown when scoring after[i]
        return pre + [robot] + after[:i]

    def score_jobs(pairs):
        with ThreadPoolExecutor(WORKERS_PER_METHOD) as ex:
            futs = {p: ex.submit(score, scene, rec_upto(p[1]), after[p[1]], cands[p[0]], cfg["warn"]) for p in pairs}
            for p, f in futs.items():
                scores[p] = f.result()

    for i in user_idx:
        score_jobs([(c, i) for c in range(len(cands))])
        while True:
            best = max((scores[(c, i)].get("ev") or 0.0) for c in range(len(cands)))
            if best >= cfg["threshold"] or len(regens) >= MAX_REGEN:
                break
            existing = "\n".join(f"{k + 1}. {c}" for k, c in enumerate(cands))
            prompt = P3.format(record="\n".join(pre + [robot] + after[:i + 1]), rule=scene["rule"], existing=existing)
            new, err = gen_candidates(prompt)
            seen = {c.lower() for c in cands}
            new = [c for c in (new or []) if c.lower() not in seen]
            regens.append({"at_line": after[i], "best_before": best, "added": new, "error": err})
            if not new:
                break
            start = len(cands)
            cands.extend(new)
            score_jobs([(c, j) for c in range(start, len(cands)) for j in user_idx if j <= i])

    def ranking(key):
        logs = []
        for c in range(len(cands)):
            s = 0.0
            for i in user_idx:
                v = scores[(c, i)].get(key)
                v = float(v) if v is not None else 50.0
                s += math.log(max(v / 100.0, 1e-6))
            logs.append(s)
        mx = max(logs)
        ps = [math.exp(x - mx) for x in logs]
        tot = sum(ps)
        order = sorted(range(len(cands)), key=lambda c: -ps[c])
        return [{"cand": cands[c], "p": ps[c] / tot} for c in order]

    per_cand = [{"cand": cands[c], "ev": [scores[(c, i)].get("ev") for i in user_idx],
                 "said": [scores[(c, i)].get("said") for i in user_idx]} for c in range(len(cands))]
    errors = sum(1 for v in scores.values() if "error" in v)
    return {"candidates": cands, "regens": regens, "per_cand": per_cand,
            "rank_ev": ranking("ev"), "rank_said": ranking("said"), "score_errors": errors}


def main():
    results = []
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            results = json.load(f)
    done = {r["id"] for r in results}
    t0 = time.time()
    for scene in SCENES:
        if scene["id"] in done:
            continue
        pre, robot, after, after_who = split_scene(scene)
        init, err = gen_candidates(P1.format(pre="\n".join(pre), robot=robot, rule=scene["rule"]))
        if err:
            print(f"scene {scene['id']}: candidate generation failed: {err}", file=sys.stderr)
            results.append({"id": scene["id"], "error": err})
            continue
        with ThreadPoolExecutor(2) as ex:
            futs = {m: ex.submit(run_method, scene, pre, robot, after, after_who, init, m) for m in METHODS}
            out = {m: f.result() for m, f in futs.items()}
        results.append({"id": scene["id"], "title": scene["title"], "hidden": scene["hidden"],
                        "initial_candidates": init, "methods": out})
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        cost = usage_total["in"] * PRICE_IN + usage_total["out"] * PRICE_OUT
        print(f"scene {scene['id']} done | calls {usage_total['calls']} errors {usage_total['errors']} "
              f"| cost so far ${cost:.3f} | {time.time() - t0:.0f}s", file=sys.stderr)
        if cost > 4.0:
            print("stopping: cost above $4 safety line", file=sys.stderr)
            break

    cost = usage_total["in"] * PRICE_IN + usage_total["out"] * PRICE_OUT
    print(f"\nTOTAL calls={usage_total['calls']} errors={usage_total['errors']} "
          f"in={usage_total['in']} out={usage_total['out']} cost=${cost:.3f} time={time.time() - t0:.0f}s")
    for r in results:
        if "error" in r:
            print(f"\n[{r['id']}] ERROR {r['error']}")
            continue
        print(f"\n[{r['id']}] {r['title']} | hidden: {r['hidden']}")
        for m, o in r["methods"].items():
            print(f"  ({m}) cands={len(o['candidates'])} regens={len(o['regens'])} score_errors={o['score_errors']}")
            for k, x in enumerate(o["rank_ev"][:3]):
                print(f"     ev#{k + 1} {x['p'] * 100:5.1f}%  {x['cand']}")
            x = o["rank_said"][0]
            print(f"     said#1 {x['p'] * 100:5.1f}%  {x['cand']}")
    print(f"\nraw saved: {OUT}")


if __name__ == "__main__":
    main()
