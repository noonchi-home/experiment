import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logprob_reliability as base  # noqa: E402  (main() guarded, nothing runs at import)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yesno_raw.json")
REPEATS = 3
MODELS = [
    ("gpt-6.1-terra", base.OPENAI_URL, "OPENAI_API_KEY",
     {"model": "gpt-6.1-terra", "reasoning_effort": "none", "max_completion_tokens": 5}),
    ("gpt-6-luna", base.OPENAI_URL, "OPENAI_API_KEY",
     {"model": "gpt-6-luna", "reasoning_effort": "none", "max_completion_tokens": 5}),
]
TEMPLATE = (
    "Observed so far: A person is typing on a laptop. An assistant places a can of soda on the desk next to them.\n"
    "Hypothesis about the person's mind: {h}\n"
    "Next observed action: {a}\n"
    "Given the hypothesis, would the next action happen? "
    "Answer with exactly one word: {opts}."
)
ORDERS = {"Yes-first": "Yes or No", "No-first": "No or Yes"}


def ask(cfg, item, order):
    name, url, key_env, b = cfg
    body = dict(b)
    body["messages"] = [{"role": "user", "content": TEMPLATE.format(h=item[1], a=item[2], opts=ORDERS[order])}]
    body["logprobs"] = True
    body["top_logprobs"] = 5
    data, err = base.post(url, key_env, body)
    if err:
        return {"error": err}
    lp = data["choices"][0].get("logprobs")
    if not lp or not lp.get("content"):
        return {"error": "logprobs not returned"}
    py = pn = 0.0
    for t in lp["content"][0].get("top_logprobs", []):
        tok = t["token"].strip().lower().rstrip(".")
        if tok == "yes":
            py += math.exp(t["logprob"])
        elif tok == "no":
            pn += math.exp(t["logprob"])
    usage = data.get("usage", {})
    return {"p_yes": py / (py + pn) if py + pn > 0 else None,
            "answer": data["choices"][0]["message"].get("content"),
            "in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")}


def main():
    results = {}
    for cfg in MODELS:
        rows = []
        for item in base.ITEMS:
            runs = {o: [ask(cfg, item, o) for _ in range(REPEATS)] for o in ORDERS}
            rows.append({"item": item[0], "expected": item[3], "runs": runs})
            print(f"  done {cfg[0]} {item[0]}", file=sys.stderr)
        results[cfg[0]] = rows
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    for name, rows in results.items():
        print(f"\n===== {name} =====")
        print("item | expected | P(yes) Yes-first [3 runs] | P(yes) No-first [3 runs] | errors")
        tin = tout = 0
        first_err = None
        for row in rows:
            cells, errs = [], 0
            for o in ORDERS:
                vals = []
                for r in row["runs"][o]:
                    tin += r.get("in") or 0
                    tout += r.get("out") or 0
                    if r.get("p_yes") is None:
                        errs += 1
                        first_err = first_err or r.get("error")
                        continue
                    vals.append(f"{r['p_yes']:.3f}")
                cells.append(", ".join(vals) if vals else "n/a")
            print(f"{row['item']} | {row['expected']} | {cells[0]} | {cells[1]} | {errs}")
        print(f"tokens total: in={tin} out={tout}")
        if first_err:
            print(f"first error: {first_err}")
    print(f"\nraw saved: {OUT}")


if __name__ == "__main__":
    main()
