import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ip_run as r  # noqa: E402  (main() guarded; reuses call() with retries and usage counting)
from ip_scenes import SCENES  # noqa: E402

OUT = os.path.join(HERE, "fsm_test_raw.json")

# step 1: record -> FSM (observable facts only)
CONVERT = (
    "Below is an observation record from a home where a robot helps a user.\n\n"
    "[Observation record]\n{record}\n\n"
    "[Task]\n"
    "Rewrite this record as a finite-state machine (FSM) of the user's activity.\n"
    "- A state is what the user is doing during a time span.\n"
    "- A transition is an observed event that moved the user from one state to another "
    "(a robot action, a user action, or something someone said).\n"
    "- Observed actions or speech that did not change the state go in that state's \"observed\" list.\n"
    "- Use only what is in the record. Do not add feelings, intentions, or reasons.\n"
    "- Every line of the record must appear somewhere in the FSM.\n"
    "- Output only JSON in this form and nothing else:\n"
    "{{\"states\": [{{\"id\": \"S0\", \"time\": \"...\", \"user_activity\": \"...\", \"observed\": [\"...\"]}}], "
    "\"transitions\": [{{\"from\": \"S0\", \"to\": \"S1\", \"time\": \"...\", \"trigger\": \"...\"}}]}}"
)
# step 2: same question as direct_ask.py, but the record is given as the FSM
ASK = (
    "You are a robot that helps people at home. Below is the record observed so far, "
    "written as a finite-state machine (FSM) of the user's activity.\n\n"
    "[Observation record as an FSM]\n{fsm}\n\n"
    "[Task]\n"
    "What state of mind did this user have at the moment the robot acted?\n"
    "- A state of mind means what the user wants, or why they would act a certain way.\n"
    "- Answer in one sentence."
)


def parse_obj(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def main():
    out = []
    for s in SCENES:
        fsm = None
        for _ in range(2):
            data, err = r.call([{"role": "user", "content": CONVERT.format(record="\n".join(s["lines"]))}], 2000, False)
            if err:
                break
            fsm = parse_obj(data["choices"][0]["message"].get("content"))
            if fsm:
                break
        if not fsm:
            out.append({"id": s["id"], "error": err or "FSM parse failed"})
            print(f"[{s['id']}] FSM ERROR {err}")
            continue
        fsm_text = json.dumps(fsm, ensure_ascii=False, indent=1)
        data, err = r.call([{"role": "user", "content": ASK.format(fsm=fsm_text)}], 300, False)
        ans = None if err else (data["choices"][0]["message"].get("content") or "").strip()
        out.append({"id": s["id"], "title": s["title"], "hidden": s["hidden"], "fsm": fsm, "answer": ans, "error": err})
        print(f"[{s['id']}] {s['title']} | hidden: {s['hidden']}\n    {ans if ans else 'ERROR ' + str(err)}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"convert_prompt": CONVERT, "ask_prompt": ASK, "results": out}, f, ensure_ascii=False, indent=1)
    for sid in (1, 9):
        x = next(o for o in out if o["id"] == sid)
        if "fsm" in x:
            print(f"\n--- FSM example, scene {sid} ---\n" + json.dumps(x["fsm"], ensure_ascii=False, indent=1))
    u = r.usage_total
    cost = u["in"] * r.PRICE_IN + u["out"] * r.PRICE_OUT
    print(f"\ncalls={u['calls']} errors={u['errors']} in={u['in']} out={u['out']} cost=${cost:.4f}")
    print(f"raw saved: {OUT}")


if __name__ == "__main__":
    main()
