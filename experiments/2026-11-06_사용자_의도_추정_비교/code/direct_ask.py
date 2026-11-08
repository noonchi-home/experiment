import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ip_run as r  # noqa: E402  (main() guarded; reuses call() with retries and usage counting)
from ip_scenes import SCENES  # noqa: E402

OUT = os.path.join(HERE, "direct_ask_raw.json")
PROMPT = (
    "You are a robot that helps people at home. Below is the record observed so far.\n\n"
    "[Observation record]\n{record}\n\n"
    "[Task]\n"
    "What state of mind did this user have at the moment the robot acted?\n"
    "- A state of mind means what the user wants, or why they would act a certain way.\n"
    "- Answer in one sentence."
)


def main():
    out = []
    for s in SCENES:
        prompt = PROMPT.format(record="\n".join(s["lines"]))
        data, err = r.call([{"role": "user", "content": prompt}], 300, False)
        ans = None if err else (data["choices"][0]["message"].get("content") or "").strip()
        out.append({"id": s["id"], "title": s["title"], "hidden": s["hidden"], "answer": ans, "error": err})
        print(f"[{s['id']}] {s['title']} | hidden: {s['hidden']}\n    {ans if ans else 'ERROR ' + str(err)}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"prompt": PROMPT, "results": out}, f, ensure_ascii=False, indent=1)
    u = r.usage_total
    cost = u["in"] * r.PRICE_IN + u["out"] * r.PRICE_OUT
    print(f"\ncalls={u['calls']} errors={u['errors']} in={u['in']} out={u['out']} cost=${cost:.4f}")
    print(f"raw saved: {OUT}")


if __name__ == "__main__":
    main()
