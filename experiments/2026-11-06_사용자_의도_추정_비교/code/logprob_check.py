import json
import math
import os
import re
import urllib.error
import urllib.request

PROMPT = (
    "Answer with exactly one letter.\n"
    "Observed so far: A person is typing on a laptop. An assistant places a can of soda on the desk next to them.\n"
    "Hypothesis about the person's mind: The person wants to keep focusing on work right now.\n"
    "Next observed action: The person shakes their head.\n"
    "Given the hypothesis, how likely is the next action?\n"
    "A) Likely\n"
    "B) Unlikely"
)


def scrub(text, secret):
    if secret:
        text = text.replace(secret, "[key hidden]")
    return re.sub(r"(sk-[A-Za-z0-9]{0,3})[A-Za-z0-9_\-]{4,}", r"\1...[hidden]", text)


def call(name, url, key_env, body):
    key = os.environ.get(key_env, "")
    if not key:
        print(f"[{name}] key env var missing")
        return
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
            "User-Agent": "logprob-check/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:600]
        print(f"[{name}] FAILED HTTP {e.code}: {scrub(msg, key)}")
        return
    except Exception as e:
        print(f"[{name}] FAILED {type(e).__name__}: {scrub(str(e), key)[:300]}")
        return
    ch = data["choices"][0]
    print(f"[{name}] model={data.get('model')} answer={ch['message'].get('content')!r}")
    lp = ch.get("logprobs")
    if not lp or not lp.get("content"):
        print(f"[{name}] LOGPROBS: NOT RETURNED (logprobs field = {json.dumps(lp)[:200]})")
    else:
        first = lp["content"][0]
        print(f"[{name}] LOGPROBS: RETURNED. first token {first['token']!r} p={math.exp(first['logprob']):.4f}")
        for t in first.get("top_logprobs", []):
            print(f"    top token {t['token']!r}: p={math.exp(t['logprob']):.4f}")
    u = data.get("usage", {})
    print(f"[{name}] tokens in={u.get('prompt_tokens')} out={u.get('completion_tokens')}")


msgs = [{"role": "user", "content": PROMPT}]

call(
    "gpt-6-luna",
    "https://api.openai.com/v1/chat/completions",
    "OPENAI_API_KEY",
    {
        "model": "gpt-6-luna",
        "messages": msgs,
        "reasoning_effort": "none",
        "logprobs": True,
        "top_logprobs": 5,
        "max_completion_tokens": 5,
    },
)

call(
    "deepseek-v4-pro",
    "https://api.deepseek.com/chat/completions",
    "DEEPSEEK_API_KEY",
    {
        "model": "deepseek-v4-pro",
        "messages": msgs,
        "thinking": {"type": "disabled"},
        "logprobs": True,
        "top_logprobs": 5,
        "max_tokens": 5,
    },
)
