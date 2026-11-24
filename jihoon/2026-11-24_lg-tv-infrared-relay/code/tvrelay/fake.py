"""TV·아두이노 없이 시험하기: 가짜 NetCast TV(로컬 HTTP)와 가짜 아두이노(시리얼 흉내).

가짜 TV는 꺼지면 포트를 닫는다(진짜 TV처럼 응답 없음). 켜면 boot_s초 뒤에 다시 연다.
가짜 아두이노는 적외선 명령을 받으면 가짜 TV를 켜고 끈다. discrete=False면 켜기·끄기 전용 코드를 무시한다.
원본(RAW) 재생은 raw_sent에 남기고, on_raw가 있으면 그 원본으로 부른다(가짜 에어컨 등).
"""

from __future__ import annotations

import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.etree import ElementTree

from .ir import LG_ADDRESS, POWER_OFF, POWER_ON, POWER_TOGGLE


class FakeTV:
    def __init__(self, port: int = 18080, key: str = "123456", boot_s: float = 2.0, on: bool = True):
        self.port, self.key, self.boot_s = port, key, boot_s
        self.on, self.shown_key, self.keys = False, False, []
        self.session = "fake-session-1"
        self._srv: ThreadingHTTPServer | None = None
        self._lock = threading.Lock()
        if on:
            self._open()

    # ---- 전원 (포트 열고 닫기)
    def _open(self) -> None:
        tv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code: int, body: str = "") -> None:
                data = body.encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/xml")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path.startswith("/udap/api/data") and "rootservice" in self.path:
                    return self._send(200, "<envelope><device><modelName>47LM6700-UA</modelName>"
                                           "<friendlyName>LG Smart TV</friendlyName><uuid>fake</uuid></device></envelope>")
                if self.path.startswith("/roap/api/data"):
                    return self._send(200, "<envelope><data><level>12</level><mute>false</mute></data></envelope>")
                self._send(404)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
                try:
                    x = ElementTree.fromstring(body)
                except ElementTree.ParseError:
                    return self._send(400)
                if self.path == "/roap/api/auth":
                    if x.findtext("type") == "AuthKeyReq":
                        tv.shown_key = True
                        return self._send(200, "<envelope><ROAPError>200</ROAPError></envelope>")
                    if x.findtext("type") == "AuthReq" and x.findtext("value") == tv.key:
                        return self._send(200, f"<envelope><ROAPError>200</ROAPError><session>{tv.session}</session></envelope>")
                    return self._send(401)
                if self.path == "/roap/api/command":
                    if x.findtext("session") != tv.session:
                        return self._send(401)
                    code = int(x.findtext("value") or 0)
                    tv.keys.append(code)
                    self._send(200, "<envelope><ROAPError>200</ROAPError></envelope>")
                    if code == 1:
                        threading.Thread(target=tv.power, args=(False,), daemon=True).start()
                    return None
                self._send(404)

        ThreadingHTTPServer.allow_reuse_address = True
        self._srv = ThreadingHTTPServer(("127.0.0.1", self.port), H)
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        self.on = True

    def _close(self) -> None:
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()
            self._srv = None
        self.on = False

    def power(self, on: bool) -> None:
        with self._lock:
            if on == self.on:
                return
            if not on:
                time.sleep(0.2)                # 응답을 마저 보내고 끈다
                self._close()
                return
        time.sleep(self.boot_s)                # 부팅 시간
        with self._lock:
            if not self.on:
                self._open()

    def toggle(self) -> None:
        self.power(not self.on)

    def shutdown(self) -> None:
        self._close()


class FakeSerial:
    """serial.Serial처럼 read/write/close. 명령을 받아 가짜 TV를 움직인다."""

    def __init__(self, tv: FakeTV, discrete: bool = True):
        self.tv, self.discrete = tv, discrete
        self.out: "queue.Queue[bytes]" = queue.Queue()
        self.sent: list[str] = []
        self.raw_on = False
        self.raw_sent: list[list[int]] = []
        self.on_raw = None
        self._emit("ready ir_bridge raw=750")

    def _emit(self, line: str) -> None:
        self.out.put((line + "\n").encode())

    def read(self, n: int = 1) -> bytes:
        try:
            return self.out.get(timeout=0.1)
        except queue.Empty:
            return b""

    def write(self, data: bytes) -> int:
        line = data.decode().strip()
        self.sent.append(line)
        parts = line.split()
        if parts[:1] == ["PING"]:
            self._emit("ok pong")
        elif parts[:1] in (["RAWON"], ["RAWOFF"]):
            self.raw_on = parts[0] == "RAWON"
            self._emit(f"ok raw {'on' if self.raw_on else 'off'}")
        elif parts[:1] == ["RAW"] and len(parts) >= 4 and int(parts[2]) == len(parts) - 3:
            ticks = [int(t) for t in parts[3:]]
            self.raw_sent.append(ticks)
            self._emit(f"ok sent RAW {len(ticks)}")
            if self.on_raw:
                self._spawn(lambda: self.on_raw(ticks))
        elif parts[:1] == ["NEC"] and len(parts) >= 3:
            addr, cmd = int(parts[1], 16), int(parts[2], 16)
            self._emit(f"ok sent NEC 0x{addr:X} 0x{cmd:X}")
            if addr == LG_ADDRESS:
                if cmd == POWER_TOGGLE:
                    self._spawn(self.tv.toggle)
                elif self.discrete and cmd == POWER_ON:
                    self._spawn(lambda: self.tv.power(True))
                elif self.discrete and cmd == POWER_OFF:
                    self._spawn(lambda: self.tv.power(False))
        else:
            self._emit("err unknown")
        return len(data)

    def press_remote(self) -> None:
        """TV 리모컨 전원 버튼을 수신 모듈에 대고 누른 것처럼."""
        if self.raw_on:
            self._emit("RXRAW 67 180 90 " + " ".join(["11 11"] * 32) + " 11")
        self._emit(f"RX NEC 0x{LG_ADDRESS:X} 0x{POWER_TOGGLE:X}")
        self._spawn(self.tv.toggle)

    def press_raw(self, ticks: list[int]) -> None:
        """방식을 모르는 리모컨(구형 에어컨)을 누른 것처럼: 해석 줄 없이 원본만."""
        if self.raw_on:
            self._emit(f"RXRAW {len(ticks)} " + " ".join(map(str, ticks)))

    @staticmethod
    def _spawn(fn) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def close(self) -> None:
        pass
