"""DeepSeek 호출. 열쇠는 환경변수 DEEPSEEK_API_KEY에서 읽어 Authorization 머리글로만 보낸다.
오류 글에 열쇠가 섞이면 지운 뒤 남긴다. 표준 라이브러리만 쓴다.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

URL = "https://api.deepseek.com/chat/completions"
BALANCE_URL = "https://api.deepseek.com/user/balance"


def _key():
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY 환경변수가 없습니다")
    return key


def scrub(text, key):
    text = text.replace(key, "[열쇠 지움]") if key else text
    return re.sub(r"(sk-[A-Za-z0-9]{0,3})[A-Za-z0-9_\-]{4,}", r"\1...[지움]", text)


def _request(url, body=None, timeout=300):
    key = _key()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + key, "User-Agent": "atomic-plan-exp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {scrub(e.read().decode(errors='replace')[:400], key)}") from None
    except Exception as e:  # 연결 오류 등
        raise RuntimeError(f"{type(e).__name__}: {scrub(str(e), key)[:300]}") from None


def balance():
    return _request(BALANCE_URL, None, timeout=30)


def chat(messages, model, thinking, max_tokens=16000, retries=3):
    """돌려줌: 글, 생각 글, 토큰(입력·캐시·출력), 초, 실제 모델 이름."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "thinking": {"type": "enabled" if thinking else "disabled"}}
    last = None
    for attempt in range(retries):
        t0 = time.perf_counter()
        try:
            d = _request(URL, body)
        except RuntimeError as e:
            last = str(e)
            if "HTTP 4" in last and "HTTP 429" not in last:
                raise
            time.sleep(5 * (attempt + 1))
            continue
        msg = d["choices"][0]["message"]
        u = d.get("usage", {})
        return {
            "글": msg.get("content") or "",
            "생각": msg.get("reasoning_content") or "",
            "토큰": {"입력": u.get("prompt_tokens", 0), "캐시": u.get("prompt_cache_hit_tokens", 0),
                   "출력": u.get("completion_tokens", 0)},
            "초": round(time.perf_counter() - t0, 2),
            "모델": d.get("model", model),
            "끝난 까닭": d["choices"][0].get("finish_reason"),
        }
    raise RuntimeError(f"{retries}번 시도했지만 실패: {last}")


def parse_json(text):
    """글에서 첫 JSON 객체를 꺼낸다. 못 꺼내면 None."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None
