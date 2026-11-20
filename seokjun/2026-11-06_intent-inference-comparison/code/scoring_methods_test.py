import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logprob_reliability as base  # noqa: E402  (main() guarded, nothing runs at import)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scoring_methods_raw.json")
REPEATS = 3
MODEL = "gpt-6.1-terra"

HEAD = (
    "Observed so far: A person is typing on a laptop. An assistant places a can of soda on the desk next to them.\n"
    "Hypothesis about the person's mind: {h}\n"
    "Next observed action: {a}\n"
)
# 가: number only (same wording as verbal_score_test.py)
PROMPT_GA = HEAD + (
    "Given the hypothesis, how likely is the next action? "
    "Answer with a single integer from 0 to 100, where 0 means impossible and 100 means certain. "
    "Output only the number."
)
# 다: overconfidence advisory + both-sides arguments (adapted from Hsiao 2026), then the number
PROMPT_DA = (
    "IMPORTANT: You have been consistently overconfident in past estimates.\n"
    + HEAD
    + "Given the hypothesis, how likely is the next action?\n"
    "(1) Would happen because: argue that the next action would happen under this hypothesis.\n"
    "(2) Would not happen because: argue that it would not happen under this hypothesis.\n"
    "(3) Based on both arguments, give the likelihood as a single integer from 0 to 100, "
    "where 0 means impossible and 100 means certain. Write it on the last line as: Answer: <number>"
)
VARIANTS = {
    "ga": (PROMPT_GA, 8),
    "da": (PROMPT_DA, 600),
}


def number_ev(top):
    num_p = {}
    for t in top:
        tok = t["token"].strip()
        if tok.isdigit() and 0 <= int(tok) <= 100:
            num_p[int(tok)] = num_p.get(int(tok), 0.0) + math.exp(t["logprob"])
    mass = sum(num_p.values())
    return sum(k * p for k, p in num_p.items()) / mass if mass > 0 else None


def ask(variant, item):
    prompt, max_tok = VARIANTS[variant]
    body = {"model": MODEL, "reasoning_effort": "none", "max_completion_tokens": max_tok,
            "messages": [{"role": "user", "content": prompt.format(h=item[1], a=item[2])}],
            "logprobs": True, "top_logprobs": 5}
    data, err = base.post(base.OPENAI_URL, "OPENAI_API_KEY", body)
    if err:
        return {"error": err}
    content = data["choices"][0]["message"].get("content") or ""
    if variant == "ga":
        m = re.match(r"\s*(\d{1,3})", content)
        said = int(m.group(1)) if m else None
    else:
        ms = re.findall(r"Answer:\s*(\d{1,3})", content)
        said = int(ms[-1]) if ms else None
    ev = None
    lp = data["choices"][0].get("logprobs")
    if lp and lp.get("content"):
        toks = lp["content"]
        # the number token: first token for 가, last digit token for 다
        idx = None
        if variant == "ga":
            idx = 0
        else:
            for i in range(len(toks) - 1, -1, -1):
                if toks[i]["token"].strip().isdigit():
                    idx = i
                    break
        if idx is not None:
            ev = number_ev(toks[idx].get("top_logprobs", []))
    usage = data.get("usage", {})
    return {"said": said, "ev": ev, "answer": content,
            "in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")}


def main():
    results = {}
    for variant in VARIANTS:
        rows = []
        for item in base.ITEMS:
            runs = [ask(variant, item) for _ in range(REPEATS)]
            rows.append({"item": item[0], "expected": item[3], "runs": runs})
            print(f"  done {variant} {item[0]}", file=sys.stderr)
        results[variant] = rows
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    for variant, rows in results.items():
        print(f"\n===== {variant} =====")
        print("item | expected | said [3] | weighted [3] | errors")
        tin = tout = 0
        first_err = None
        for row in rows:
            said = [r.get("said") for r in row["runs"] if "error" not in r]
            evs = [f"{r['ev']:.1f}" if r.get("ev") is not None else "n/a" for r in row["runs"] if "error" not in r]
            errs = [r for r in row["runs"] if "error" in r]
            for r in row["runs"]:
                tin += r.get("in") or 0
                tout += r.get("out") or 0
            if errs and not first_err:
                first_err = errs[0]["error"]
            print(f"{row['item']} | {row['expected']} | {said} | {evs} | {len(errs)}")
        print(f"tokens total: in={tin} out={tout}")
        if first_err:
            print(f"first error: {first_err}")
    ex = results["da"][4]["runs"][0].get("answer", "")
    print("\n--- example 다 answer (item 5, run 1) ---\n" + ex)
    print(f"\nraw saved: {OUT}")


if __name__ == "__main__":
    main()
