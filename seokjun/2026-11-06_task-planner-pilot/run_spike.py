"""Throwaway spike: compare two ways of writing rule actions in the night reflection.

template: actions must use one of three fixed forms.
free:     actions are free text but must be composable from atomic actions.
Same day log, same model/provider/settings; 3 runs each. Key comes only from the
OPENROUTER_API_KEY environment variable and is sent only in the Authorization header.
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "qwen/qwen3.5-27b"
PROVIDER = {"order": ["alibaba"], "allow_fallbacks": False, "require_parameters": True}
PRICE_IN, PRICE_OUT = 0.195e-6, 1.56e-6  # USD per token, Alibaba endpoint (checked 2026-11-06)
RUNS = 3

TEMPLATE_SPEC = """- action: written in EXACTLY one of the following three forms, filling the slots only
with the names and capabilities listed above:
  (A) `Operate the <appliance>: <capability>.`  e.g., `Operate the air conditioner: turn on at 26°C.`
  (B) `Take the <object> out of the <appliance> and place it <destination>.` where
      <destination> is exactly one of: `next to the person`, `inside the <appliance>`.
  (C) `Put the <object> from the <place> into the <appliance>.`
  Any other form is invalid."""

ATOMIC = """
# Atomic Actions (everything the robot does is a sequence of these)
- go(place or appliance): move there using the home map
- open(appliance) / close(appliance): physically open or close the appliance's door
- look(place or inside an appliance): check which objects are there
- pick(object): pick up an object in front of the robot (the robot's hand must be empty)
- place(object, place or inside an appliance): put the held object there
- set(appliance, capability): operate the appliance via its connection (only capabilities
  marked "via connection")
- read(appliance): read the appliance's current state
"""

FREE_SPEC = """- action: a NATURAL LANGUAGE description of how the robot should help, mirroring what the
human did and using only the names listed above. It must be achievable as a sequence of
the atomic actions listed above."""

CONDITIONS = {
    "template": {"PARTIAL_HINT": "i.e., it cannot be written in one of the three action forms below",
                 "ATOMIC_SECTION": "", "ACTION_SPEC": TEMPLATE_SPEC},
    "free": {"PARTIAL_HINT": "i.e., it cannot be composed from the atomic actions below",
             "ATOMIC_SECTION": ATOMIC, "ACTION_SPEC": FREE_SPEC},
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # never forward the Authorization header elsewhere


def build_prompt(name: str) -> str:
    text = (HERE / "prompt_base.txt").read_text(encoding="utf-8")
    for key, value in CONDITIONS[name].items():
        token = "{" + key + "}"
        if text.count(token) != 1:
            raise SystemExit(f"placeholder {token} not found exactly once")
        text = text.replace(token, value)
    return text


def parse_memory(content: str):
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    try:
        memory = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"JSON parse error: {exc}"
    if not isinstance(memory, dict) or "initial_state" not in memory or not isinstance(memory.get("states"), list):
        return None, "missing initial_state or states"
    return memory, None


def call(name: str, run: int, prompt: str, day_log: str, key: str) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": prompt},
                     {"role": "user", "content": [{"type": "text", "text": "Day log:\n" + day_log}]}],
        "temperature": 0.3,
        "reasoning": {"enabled": True},
        "max_tokens": 16384,
        "provider": PROVIDER,
        "stream": False,
        "plugins": [{"id": "context-compression", "enabled": False}],
    }
    request = Request(ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                               "Accept": "application/json"})
    started = time.perf_counter()
    record = {"condition": name, "run": run}
    try:
        with build_opener(NoRedirect).open(request, timeout=600) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        record.update(status="http_error", http_status=exc.code,
                      error_body=exc.read().decode("utf-8", "replace")[:1500])
        body = None
    except (URLError, TimeoutError, OSError) as exc:
        record.update(status="network_error", error=type(exc).__name__)
        body = None
    record["elapsed_seconds"] = round(time.perf_counter() - started, 1)
    if body is not None:
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = body.get("usage") or {}
        memory, error = parse_memory(message.get("content"))
        record.update(status="valid" if memory else "invalid", parse_error=error,
                      finish_reason=choice.get("finish_reason"), provider=body.get("provider"),
                      response_model=body.get("model"), usage=usage,
                      cost_usd=round(usage.get("prompt_tokens", 0) * PRICE_IN
                                     + usage.get("completion_tokens", 0) * PRICE_OUT, 5),
                      memory=memory, content=message.get("content"), reasoning=message.get("reasoning"))
    (OUT / f"{name}_{run}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main() -> None:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    OUT.mkdir(exist_ok=True)
    day_log = (HERE / "day_log.txt").read_text(encoding="utf-8")
    prompts = {name: build_prompt(name) for name in CONDITIONS}
    for name, prompt in prompts.items():
        (HERE / f"prompt_{name}.txt").write_text(prompt, encoding="utf-8")
    jobs = [(name, run) for name in CONDITIONS for run in range(1, RUNS + 1)]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        records = list(pool.map(lambda job: call(job[0], job[1], prompts[job[0]], day_log, key), jobs))
    total = 0.0
    for r in records:
        total += r.get("cost_usd", 0) or 0
        rules = sum(len(s.get("rules", [])) for s in (r.get("memory") or {}).get("states", []))
        print(f"{r['condition']:8s} run{r['run']}  {r['status']:13s} finish={r.get('finish_reason')} "
              f"provider={r.get('provider')} rules={rules} tokens_in={(r.get('usage') or {}).get('prompt_tokens')} "
              f"tokens_out={(r.get('usage') or {}).get('completion_tokens')} {r['elapsed_seconds']}s "
              f"${r.get('cost_usd')}" + (f" http={r.get('http_status')}" if r.get('http_status') else ""))
    print(f"total cost ~ ${total:.4f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
