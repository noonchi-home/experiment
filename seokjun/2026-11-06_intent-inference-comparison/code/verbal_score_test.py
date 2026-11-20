import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logprob_reliability as base  # noqa: E402  (main() guarded, nothing runs at import)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verbal_score_raw.json")
REPEATS = 3
CFG = ("gpt-6.1-terra", base.OPENAI_URL, "OPENAI_API_KEY",
       {"model": "gpt-6.1-terra", "reasoning_effort": "none", "max_completion_tokens": 8})

TEMPLATE = (
    "Observed so far: A person is typing on a laptop. An assistant places a can of soda on the desk next to them.\n"
    "Hypothesis about the person's mind: {h}\n"
    "Next observed action: {a}\n"
    "Given the hypothesis, how likely is the next action? "
    "Answer with a single integer from 0 to 100, where 0 means impossible and 100 means certain. "
    "Output only the number."
)


def ask(item):
    name, url, key_env, b = CFG
    body = dict(b)
    body["messages"] = [{"role": "user", "content": TEMPLATE.format(h=item[1], a=item[2])}]
    body["logprobs"] = True
    body["top_logprobs"] = 5
    data, err = base.post(url, key_env, body)
    if err:
        return {"error": err}
    content = data["choices"][0]["message"].get("content") or ""
    m = re.match(r"\s*(\d{1,3})", content)
    said = int(m.group(1)) if m else None
    # expected value over the number tokens offered at the first position
    ev = None
    lp = data["choices"][0].get("logprobs")
    if lp and lp.get("content"):
        num_p = {}
        for t in lp["content"][0].get("top_logprobs", []):
            tok = t["token"].strip()
            if tok.isdigit() and 0 <= int(tok) <= 100:
                num_p[int(tok)] = num_p.get(int(tok), 0.0) + math.exp(t["logprob"])
        mass = sum(num_p.values())
        if mass > 0:
            ev = sum(k * p for k, p in num_p.items()) / mass
    usage = data.get("usage", {})
    return {"said": said, "answer": content, "ev": ev,
            "in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")}


def main():
    rows = []
    for item in base.ITEMS:
        runs = [ask(item) for _ in range(REPEATS)]
        rows.append({"item": item[0], "expected": item[3], "runs": runs})
        print(f"  done {item[0]}", file=sys.stderr)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    print("item | expected | said (3 runs) | expected value from top-5 (3 runs) | errors")
    tin = tout = 0
    for row in rows:
        said = [r.get("said") for r in row["runs"] if "said" in r]
        evs = [f"{r['ev']:.1f}" if r.get("ev") is not None else "n/a" for r in row["runs"] if "said" in r]
        errs = [r["error"] for r in row["runs"] if "error" in r]
        for r in row["runs"]:
            tin += r.get("in") or 0
            tout += r.get("out") or 0
        print(f"{row['item']} | {row['expected']} | {said} | {evs} | {len(errs)}")
        if errs:
            print(f"    first error: {errs[0]}")
    print(f"tokens total: in={tin} out={tout}")
    print(f"raw saved: {OUT}")


if __name__ == "__main__":
    main()
