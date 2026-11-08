import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logprob_reliability as base  # noqa: E402  (runs nothing at import: main() guarded below)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logprob_reliability2_raw.json")

OPENAI_URL = base.OPENAI_URL
NEW_MODELS = [
    ("gpt-6-sol", OPENAI_URL, "OPENAI_API_KEY",
     {"model": "gpt-6-sol", "reasoning_effort": "none", "max_completion_tokens": 5}),
    ("gpt-6.1-terra", OPENAI_URL, "OPENAI_API_KEY",
     {"model": "gpt-6.1-terra", "reasoning_effort": "none", "max_completion_tokens": 5}),
]
ALL_MODELS = base.MODELS + NEW_MODELS

PURE = (
    "Answer with exactly one letter.\n"
    "Pick one of the two options. There is no right or wrong answer and no reason to prefer either.\n"
    "A) {x}\n"
    "B) {y}"
)


def pure_choice(cfg, x, y):
    name, url, key_env, b = cfg
    body = dict(b)
    body["messages"] = [{"role": "user", "content": PURE.format(x=x, y=y)}]
    body["logprobs"] = True
    body["top_logprobs"] = 5
    data, err = base.post(url, key_env, body)
    if err:
        return {"error": err}
    probs = base.letter_probs(data)
    if probs is None:
        return {"error": "logprobs not returned"}
    pa, pb = probs
    if pa + pb == 0:
        return {"error": "no A/B in top tokens"}
    return {"p_A": pa / (pa + pb), "answer": data["choices"][0]["message"].get("content")}


def main():
    results = {"full": {}, "pure": {}}
    # 1) same 8-item test on the two new models
    for cfg in NEW_MODELS:
        rows = []
        for item in base.ITEMS:
            per_order = {o: [base.ask(cfg, item, o) for _ in range(base.REPEATS)] for o in base.ORDERS}
            rows.append({"item": item[0], "expected": item[3], "runs": per_order})
            print(f"  done {cfg[0]} {item[0]}", file=sys.stderr)
        results["full"][cfg[0]] = rows
    # 2) pure A/B choice (no content) on all four models
    for cfg in ALL_MODELS:
        runs = []
        for x, y in (("Option one", "Option two"), ("Option two", "Option one")):
            for _ in range(base.REPEATS):
                runs.append(pure_choice(cfg, x, y))
        results["pure"][cfg[0]] = runs
        print(f"  done pure {cfg[0]}", file=sys.stderr)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    for name, rows in results["full"].items():
        print(f"\n===== {name} =====")
        print("item | expected | p(Likely) A=Likely mean [min-max] | p(Likely) A=Unlikely mean [min-max] | avg of orders | errors")
        max_gap = max_spread = 0.0
        extreme = total = 0
        first_err = None
        for row in rows:
            means, cells, errs = [], [], 0
            for o in base.ORDERS:
                vals = []
                for r in row["runs"][o]:
                    if r.get("p_likely") is None:
                        errs += 1
                        first_err = first_err or r.get("error")
                        continue
                    vals.append(r["p_likely"])
                    total += 1
                    extreme += r["p_likely"] < 0.01 or r["p_likely"] > 0.99
                if vals:
                    means.append(sum(vals) / len(vals))
                    max_spread = max(max_spread, max(vals) - min(vals))
                    cells.append(f"{means[-1]:.3f} [{min(vals):.3f}-{max(vals):.3f}]")
                else:
                    cells.append("n/a")
            avg = f"{sum(means) / len(means):.3f}" if len(means) == 2 else "n/a"
            if len(means) == 2:
                max_gap = max(max_gap, abs(means[0] - means[1]))
            print(f"{row['item']} | {row['expected']} | {cells[0]} | {cells[1]} | {avg} | {errs}")
        print(f"max gap between A/B orders: {max_gap:.3f} / max spread across repeats: {max_spread:.3f} / extreme: {extreme}/{total}")
        if first_err:
            print(f"first error: {first_err}")

    print("\n===== pure A/B choice (no content) : probability of letter A =====")
    for name, runs in results["pure"].items():
        vals = [r["p_A"] for r in runs if "p_A" in r]
        answers = [(r.get("answer") or "").strip()[:2] for r in runs if "p_A" in r]
        errs = [r["error"] for r in runs if "error" in r]
        if vals:
            print(f"{name}: mean p(A)={sum(vals) / len(vals):.3f} [{min(vals):.3f}-{max(vals):.3f}] answers={answers} errors={len(errs)}")
        else:
            print(f"{name}: no values, first error={errs[0] if errs else None}")
    print(f"\nraw saved: {OUT}")


if __name__ == "__main__":
    main()
