import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logprob_reliability as base  # noqa: E402  (main() guarded)
import scoring_methods_test as smt  # noqa: E402  (main() guarded)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ga_warn_raw.json")
PROMPT = "IMPORTANT: You have been consistently overconfident in past estimates.\n" + smt.PROMPT_GA


def ask(item):
    body = {"model": smt.MODEL, "reasoning_effort": "none", "max_completion_tokens": 8,
            "messages": [{"role": "user", "content": PROMPT.format(h=item[1], a=item[2])}],
            "logprobs": True, "top_logprobs": 5}
    data, err = base.post(base.OPENAI_URL, "OPENAI_API_KEY", body)
    if err:
        return {"error": err}
    content = data["choices"][0]["message"].get("content") or ""
    m = re.match(r"\s*(\d{1,3})", content)
    lp = data["choices"][0].get("logprobs")
    ev = smt.number_ev(lp["content"][0].get("top_logprobs", [])) if lp and lp.get("content") else None
    usage = data.get("usage", {})
    return {"said": int(m.group(1)) if m else None, "ev": ev, "answer": content,
            "in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")}


def main():
    rows = []
    for item in base.ITEMS:
        runs = [ask(item) for _ in range(smt.REPEATS)]
        rows.append({"item": item[0], "expected": item[3], "runs": runs})
        print(f"  done {item[0]}", file=sys.stderr)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print("item | expected | said [3] | weighted [3] | errors")
    tin = tout = 0
    for row in rows:
        ok = [r for r in row["runs"] if "error" not in r]
        errs = [r for r in row["runs"] if "error" in r]
        for r in row["runs"]:
            tin += r.get("in") or 0
            tout += r.get("out") or 0
        said = [r["said"] for r in ok]
        evs = [f"{r['ev']:.1f}" if r.get("ev") is not None else "n/a" for r in ok]
        print(f"{row['item']} | {row['expected']} | {said} | {evs} | {len(errs)}")
        if errs:
            print(f"    first error: {errs[0]['error']}")
    print(f"tokens total: in={tin} out={tout}")
    print(f"raw saved: {OUT}")


if __name__ == "__main__":
    main()
