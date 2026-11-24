"""중계 HTTP 서버: 눈치서버(EC2)가 Tailscale로 부른다. 눈치서버 src/devices/relay/client.ts와 짝이다.

  GET  /health                          → {"ok": true}                          (토큰 없이)
  GET  /api/devices/tv                  → {"power": "on"|"off"|"unknown", "since": ISO, "online": true, "ir": bool}
  POST /api/devices/tv/command {type}   → {"ok", "outcome": done|unverified|failed|not_sent, "power", "error"?}
  /api/* 요청은 Authorization: Bearer <TV_RELAY_TOKEN>이 맞아야 한다(401).

켜기: 적외선(켜기 전용 0xC4 → 안 되면 토글) → TV 와이파이 응답으로 확인 → 셋톱 신호(녹음해 둔 것, 있으면).
끄기: 와이파이(페어링돼 있으면) → 안 되면 적외선 → 응답이 없어지는지 확인.
쏘았는데 확인 못 하면 unverified(ok). 한 번에 한 명령만(앞 명령 중이면 409, not_sent).
"""

from __future__ import annotations

import hmac
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import ir as IR
from .monitor import Monitor
from .netcast import NetCast, NetCastError

TARGET = "tv"


class Relay:
    def __init__(self, monitor: Monitor, nc: NetCast | None = None, bridge: IR.Bridge | None = None,
                 address: int = IR.LG_ADDRESS, toggle_cmd: int = IR.POWER_TOGGLE, stb: dict | None = None,
                 on_wait: float = 25.0, off_wait: float = 8.0, log=None):
        self.monitor, self.nc, self.bridge = monitor, nc, bridge
        self.address, self.toggle_cmd, self.stb = address, toggle_cmd, stb
        self.on_wait, self.off_wait = on_wait, off_wait
        self.log = log or (lambda m: print(m, flush=True))
        self._busy = threading.Lock()

    def state(self) -> dict:
        snap = self.monitor.snapshot()
        since = datetime.fromtimestamp(snap["since"]).isoformat(timespec="seconds") if snap["since"] else None
        return {"power": snap["state"], "since": since, "online": True, "ir": bool(self.bridge and self.bridge.alive)}

    def command(self, kind: str) -> tuple[int, dict]:
        if kind not in ("on", "off"):
            return 400, {"ok": False, "outcome": "not_sent", "error": "type은 on 또는 off예요"}
        if not self._busy.acquire(blocking=False):
            return 409, {"ok": False, "outcome": "not_sent", "error": "앞 명령을 처리하는 중이에요"}
        try:
            r = self._on() if kind == "on" else self._off()
        except (TimeoutError, RuntimeError, OSError, NetCastError) as e:
            r = {"ok": False, "outcome": "failed", "error": f"{type(e).__name__}: {e}"}
        finally:
            self._busy.release()
        r["power"] = self.monitor.state
        self.log(f"명령 {kind}: {r['outcome']}" + (f" ({r['error']})" if r.get("error") else ""))
        return 200, r

    def _ir_ready(self) -> bool:
        return bool(self.bridge and self.bridge.alive)

    def _on(self) -> dict:
        if self.monitor.state == "on":
            return {"ok": True, "outcome": "done"}
        if not self._ir_ready():
            return {"ok": False, "outcome": "not_sent", "error": "아두이노가 연결돼 있지 않아 켤 수 없어요"}
        r = IR.power_to("on", self.bridge, self.monitor, self.address, "auto", self.on_wait, self.off_wait, self.toggle_cmd)
        if not r["ok"]:
            return {"ok": True, "outcome": "unverified", "error": f"적외선을 쏘았지만 {self.on_wait:.0f}초 안에 TV 응답이 없어요"}
        if self.stb:
            IR.send_code(self.bridge, self.stb)            # 셋톱도 켜야 화면이 나온다(녹음한 신호, 확인은 못 함)
        return {"ok": True, "outcome": "done"}

    def _off(self) -> dict:
        if self.monitor.state == "off":
            return {"ok": True, "outcome": "done"}
        if self.nc and self.nc.key:
            try:
                self.nc.power_off()
                if self.monitor.wait_for("off", self.off_wait) is not None:
                    return {"ok": True, "outcome": "done"}
            except (NetCastError, OSError) as e:
                self.log(f"와이파이 끄기 실패, 적외선으로: {e}")
        if not self._ir_ready():
            if self.nc and self.nc.key:
                return {"ok": True, "outcome": "unverified", "error": "와이파이로 보냈지만 꺼짐을 확인하지 못했어요"}
            return {"ok": False, "outcome": "not_sent", "error": "페어링도 아두이노도 없어 끌 수 없어요"}
        r = IR.power_to("off", self.bridge, self.monitor, self.address, "auto", self.on_wait, self.off_wait, self.toggle_cmd)
        if r["ok"]:
            return {"ok": True, "outcome": "done"}
        return {"ok": True, "outcome": "unverified", "error": "적외선을 쏘았지만 꺼짐을 확인하지 못했어요"}


def make_handler(relay: Relay, token: str):
    want = f"Bearer {token}".encode()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, code: int, obj: dict) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authed(self) -> bool:
            got = (self.headers.get("Authorization") or "").encode()
            if hmac.compare_digest(got, want):
                return True
            self._json(401, {"error": "토큰이 맞지 않아요"})
            return False

        def do_GET(self):
            if self.path == "/health":
                return self._json(200, {"ok": True})
            if not self._authed():
                return None
            if self.path == f"/api/devices/{TARGET}":
                return self._json(200, relay.state())
            self._json(404, {"error": "없는 경로"})

        def do_POST(self):
            if not self._authed():
                return None
            if self.path != f"/api/devices/{TARGET}/command":
                return self._json(404, {"error": "없는 경로"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except ValueError:
                return self._json(400, {"ok": False, "outcome": "not_sent", "error": "JSON이 아니에요"})
            code, out = relay.command(str(body.get("type")))
            self._json(code, out)

    return H


def serve(relay: Relay, token: str, host: str = "127.0.0.1", port: int = 8530) -> ThreadingHTTPServer:
    """서버를 띄워 돌려준다(serve_forever는 부르는 쪽이). 토큰이 없으면 띄우지 않는다."""
    if not token or len(token) < 16:
        raise ValueError("TV_RELAY_TOKEN을 16자 이상으로 정해 주세요(눈치서버와 같은 값)")
    return ThreadingHTTPServer((host, port), make_handler(relay, token))
