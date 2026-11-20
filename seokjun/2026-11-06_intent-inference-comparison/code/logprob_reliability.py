import json
import math
import os
import re
import sys
import urllib.error
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logprob_reliability_raw.json")
REPEATS = 3

TEMPLATE = (
    "Answer with exactly one letter.\n"
    "Observed so far: A person is typing on a laptop. An assistant places a can of soda on the desk next to them.\n"
    "Hypothesis about the person's mind: {h}\n"
    "Next observed action: {a}\n"
    "Given the hypothesis, how likely is the next action?\n"
    "{opts}"
)
ORDERS = {
    "A=Likely": ("A) Likely\nB) Unlikely", "A"),
    "A=Unlikely": ("A) Unlikely\nB) Likely", "B"),
}

DRINK_NOW = "The person wants to drink something right now."
NO_DRINK = "The person does not want any drink."
FOCUS = "The person wants to keep focusing on work right now."
FOCUS_LATER = "The person wants to keep focusing on work right now and may drink later."
ITEMS = [
    ("1 drink_now + drinks", DRINK_NOW, "The person picks up the can and drinks from it immediately.", "high"),
    ("2 no_drink + drinks", NO_DRINK, "The person picks up the can and drinks from it immediately.", "low"),
    ("3 focus + shakes head", FOCUS, "The person shakes their head.", "high"),
    ("4 drink_now + shakes head", DRINK_NOW, "The person shakes their head.", "low"),
    ("5 focus_later + moves aside", FOCUS_LATER, "The person moves the can aside and keeps typing.", "high"),
    ("6 no_drink + returns can", NO_DRINK, "The person carries the can back to where it was originally kept.", "high"),
    ("7 no_drink + moves aside", NO_DRINK, "The person moves the can aside and keeps typing.", "high"),
    ("8 drink_now + moves aside", DRINK_NOW, "The person moves the can aside and keeps typing.", "low"),
]

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODELS = [
    ("gpt-6-luna", OPENAI_URL, "OPENAI_API_KEY",
     {"model": "gpt-6-luna", "reasoning_effort": "none", "max_completion_tokens": 5}),
    ("deepseek-v4-pro", DEEPSEEK_URL, "DEEPSEEK_API_KEY",
     {"model": "deepseek-v4-pro", "thinking": {"type": "disabled"}, "max_tokens": 5}),
]
SOL_PROBE = ("gpt-6.1-sol", OPENAI_URL, "OPENAI_API_KEY",
             {"model": "gpt-6.1-sol", "reasoning_effort": "low", "max_completion_tokens": 200})


def scrub(text, secret):
    if secret:
        text = text.replace(secret, "[key hidden]")
    return re.sub(r"(sk-[A-Za-z0-9]{0,3})[A-Za-z0-9_\-]{4,}", r"\1...[hidden]", text)


def post(url, key_env, body):
    key = os.environ.get(key_env, "")
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key,
                 "User-Agent": "logprob-check/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {scrub(e.read().decode(errors='replace')[:400], key)}"
    except Exception as e:
        return None, f"{type(e).__name__}: {scrub(str(e), key)[:300]}"


def letter_probs(data):
    lp = data["choices"][0].get("logprobs")
    if not lp or not lp.get("content"):
        return None
    pa = pb = 0.0
    for t in lp["content"][0].get("top_logprobs", []):
        tok = t["token"].strip()
        if tok in ("A", "A)", "A."):
            pa += math.exp(t["logprob"])
        elif tok in ("B", "B)", "B."):
            pb += math.exp(t["logprob"])
    return pa, pb


def ask(model_cfg, item, order_name):
    name, url, key_env, base = model_cfg
    h, a = item[1], item[2]
    opts, likely_letter = ORDERS[order_name]
    body = dict(base)
    body["messages"] = [{"role": "user", "content": TEMPLATE.format(h=h, a=a, opts=opts)}]
    body["logprobs"] = True
    body["top_logprobs"] = 5
    data, err = post(url, key_env, body)
    if err:
        return {"error": err}
    probs = letter_probs(data)
    if probs is None:
        return {"error": "logprobs not returned", "answer": data["choices"][0]["message"].get("content")}
    pa, pb = probs
    mass = pa + pb
    p_likely = None
    if mass > 0:
        p_likely = (pa if likely_letter == "A" else pb) / mass
    usage = data.get("usage", {})
    return {"p_likely": p_likely, "mass": mass, "answer": data["choices"][0]["message"].get("content"),
            "in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens")}


def main():
    results = {}
    # 1) gpt-6.1-sol probe (official guide says no 'none' effort -> logprobs likely rejected)
    probe = ask(SOL_PROBE, ITEMS[0], "A=Likely")
    print(f"[gpt-6.1-sol probe] {probe}")
    results["gpt-6.1-sol-probe"] = probe
    models = list(MODELS)
    if "p_likely" in probe:
        models.append(SOL_PROBE)

    for cfg in models:
        name = cfg[0]
        rows = []
        for item in ITEMS:
            per_order = {}
            for order_name in ORDERS:
                runs = [ask(cfg, item, order_name) for _ in range(REPEATS)]
                per_order[order_name] = runs
            rows.append({"item": item[0], "expected": item[3], "runs": per_order})
            print(f"  done {name} {item[0]}", file=sys.stderr)
        results[name] = rows
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    # summary
    for cfg in models:
        name = cfg[0]
        print(f"\n===== {name} =====")
        print("item | expected | p(Likely) A=Likely mean [min-max] | p(Likely) A=Unlikely mean [min-max] | min mass | errors")
        dir_ok = 0
        max_gap = 0.0
        max_spread = 0.0
        extreme = total = 0
        tin = tout = 0
        for row in results[name]:
            cells = []
            means = []
            errs = 0
            masses = []
            for order_name in ORDERS:
                vals = []
                for r in row["runs"][order_name]:
                    if r.get("p_likely") is None:
                        errs += 1
                        continue
                    vals.append(r["p_likely"])
                    masses.append(r["mass"])
                    tin += r.get("in") or 0
                    tout += r.get("out") or 0
                    total += 1
                    if r["p_likely"] < 0.01 or r["p_likely"] > 0.99:
                        extreme += 1
                if vals:
                    m = sum(vals) / len(vals)
                    means.append(m)
                    spread = max(vals) - min(vals)
                    max_spread = max(max_spread, spread)
                    cells.append(f"{m:.3f} [{min(vals):.3f}-{max(vals):.3f}]")
                else:
                    cells.append("n/a")
            if len(means) == 2:
                max_gap = max(max_gap, abs(means[0] - means[1]))
                avg = sum(means) / 2
                if (row["expected"] == "high" and avg > 0.5) or (row["expected"] == "low" and avg < 0.5):
                    dir_ok += 1
            mm = f"{min(masses):.3f}" if masses else "n/a"
            print(f"{row['item']} | {row['expected']} | {cells[0]} | {cells[1]} | {mm} | {errs}")
        print(f"direction matches my expectation: {dir_ok}/{len(ITEMS)}")
        print(f"max gap between A/B orders (same item): {max_gap:.3f}")
        print(f"max spread across {REPEATS} repeats: {max_spread:.3f}")
        print(f"extreme values (<0.01 or >0.99): {extreme}/{total}")
        print(f"tokens total: in={tin} out={tout}")
    print(f"\nraw saved: {OUT}")


if __name__ == "__main__":
    main()
