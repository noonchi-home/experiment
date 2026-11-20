"""Send the user's pasted prompt once to Qwen3.5-27B (OpenRouter, Alibaba pinned)."""
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

HERE = Path(__file__).resolve().parent


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    prompt = (HERE / "coffee_prompt.txt").read_text(encoding="utf-8")
    payload = {
        "model": "qwen/qwen3.5-27b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "reasoning": {"enabled": True},
        "max_tokens": 16384,
        "provider": {"order": ["alibaba"], "allow_fallbacks": False, "require_parameters": True},
        "stream": False,
        "plugins": [{"id": "context-compression", "enabled": False}],
    }
    request = Request("https://openrouter.ai/api/v1/chat/completions",
                      data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with build_opener(NoRedirect).open(request, timeout=600) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:800]}")
    elapsed = round(time.perf_counter() - started, 1)
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / "coffee_1.json").write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    choice = body["choices"][0]
    usage = body.get("usage") or {}
    cost = usage.get("prompt_tokens", 0) * 0.195e-6 + usage.get("completion_tokens", 0) * 1.56e-6
    print(f"provider={body.get('provider')} finish={choice.get('finish_reason')} "
          f"in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')} {elapsed}s ~${cost:.4f}")
    print("----- answer -----")
    print(choice["message"].get("content"))


if __name__ == "__main__":
    main()
