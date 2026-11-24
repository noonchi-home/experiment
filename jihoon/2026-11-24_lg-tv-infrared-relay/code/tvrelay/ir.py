"""아두이노 적외선 브리지(arduino/ir_bridge/ir_bridge.ino)와 USB 시리얼로 말하기.

  노트북 → 아두이노:  "NEC 0x4 0xC4 0" (주소 명령 반복) / "RAW 38 n t1 … tn" (원본 재생, 50us 단위) / "RAWON"·"RAWOFF" / "PING"
  아두이노 → 노트북:  "ready ir_bridge" / "ok ..." / "err ..." / "RX NEC 0x4 0x8" (해석한 신호)
                      / "RXRAW n t1 … tn" (RAWON일 때 원본) / "RXOVF" (원본이 버퍼를 넘침)
LG TV 신호(NEC, 주소 0x04): 전원 토글 0x08, 켜기 전용 0xC4, 끄기 전용 0xC5.
구형 에어컨·셋톱처럼 방식을 모르는 리모컨은 원본(켜짐·꺼짐 길이 목록)을 녹음해 그대로 다시 쏜다.
"""

from __future__ import annotations

import re
import threading
import time

LG_ADDRESS, POWER_TOGGLE, POWER_ON, POWER_OFF = 0x04, 0x08, 0xC4, 0xC5
RX_RE = re.compile(r"^RX\s+(\S+)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)")
SELF_ECHO_S = 0.6                     # 쏜 직후 수신 모듈이 자기 신호를 받은 것은 '배운 신호'에서 뺀다
TICK_US = 50                          # 원본 길이 한 칸
RAW_MAX = 750                         # 아두이노 원본 버퍼 칸 수(ir_bridge.ino RAW_BUFFER_LENGTH)
IR_COMMANDS = ("NEC", "ON", "OFF", "PWR", "RAW")


def parse_rx(line: str) -> dict | None:
    m = RX_RE.match(line.strip())
    if not m:
        return None
    return {"protocol": m.group(1), "address": int(m.group(2), 16), "command": int(m.group(3), 16)}


def parse_raw(line: str) -> list[int] | None:
    """'RXRAW n t1 … tn' → [t1 … tn] (50us 단위). 개수가 안 맞으면 None."""
    parts = line.strip().split()
    if len(parts) < 3 or parts[0] != "RXRAW" or not all(p.isdigit() for p in parts[1:]):
        return None
    n, ticks = int(parts[1]), [int(p) for p in parts[2:]]
    return ticks if len(ticks) == n else None


def serial_available() -> bool:
    try:
        import serial  # noqa: F401
        return True
    except ImportError:
        return False


def list_ports() -> list[dict]:
    try:
        from serial.tools import list_ports as lp
    except ImportError:
        return []
    return [{"device": p.device, "desc": p.description or ""} for p in lp.comports()]


class Bridge:
    """시리얼 연결 하나. 받은 줄은 읽기 스레드가 모으고, send는 'ok'/'err' 답을 기다린다."""

    def __init__(self, port: str, baud: int = 115200, opener=None):
        if opener is None:
            import serial
            opener = lambda: serial.Serial(port, baud, timeout=0.2)  # noqa: E731
        self.port = port
        self.ser = opener()
        self.lines: list[dict] = []              # [{t, text}]
        self.rx: list[dict] = []                 # 배운 신호 [{t, protocol, address, command}]
        self.raws: list[dict] = []               # 받은 원본 [{t, ticks}] (RAWON일 때)
        self.overflows = 0
        self.ready = False
        self.last_send = 0.0
        self._replies: list[str] = []
        self._cond = threading.Condition()
        self._stop = threading.Event()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self.ser.read(64)
            except Exception:  # noqa: BLE001 — 선이 빠짐
                self._stop.set()
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                self._line(raw.decode("utf-8", "replace").strip())

    def _line(self, text: str) -> None:
        if not text:
            return
        now = time.time()
        with self._cond:
            self.lines.append({"t": now, "text": text})
            del self.lines[:-200]
            if text.startswith("ready"):
                self.ready = True
            rx = parse_rx(text)
            if rx and now - self.last_send > SELF_ECHO_S:
                self.rx.append({"t": now, **rx})
                del self.rx[:-100]
            ticks = parse_raw(text) if text.startswith("RXRAW") else None
            if ticks and now - self.last_send > SELF_ECHO_S:
                self.raws.append({"t": now, "ticks": ticks})
                del self.raws[:-20]
            if text == "RXOVF":
                self.overflows += 1
            if text.startswith(("ok", "err")):
                self._replies.append(text)
            self._cond.notify_all()

    @property
    def alive(self) -> bool:
        return not self._stop.is_set()

    def send(self, cmd: str, timeout: float = 2.0) -> str:
        with self._cond:
            self._replies.clear()
            if cmd.split()[:1] and cmd.split()[0] in IR_COMMANDS:   # 빛을 쏘는 명령만(자기 신호 걸러 내기용)
                self.last_send = time.time()
            self.ser.write((cmd.strip() + "\n").encode())
            ok = self._cond.wait_for(lambda: bool(self._replies), timeout)
            reply = self._replies[0] if ok else ""
        if not reply:
            raise TimeoutError(f"아두이노가 답하지 않아요 ({cmd})")
        if reply.startswith("err"):
            raise RuntimeError(reply)
        return reply

    def nec(self, address: int, command: int, repeats: int = 0) -> str:
        return self.send(f"NEC 0x{address:X} 0x{command:X} {repeats}")

    def raw_report(self, on: bool) -> str:
        """받은 신호를 원본으로도 알릴지(녹음할 때만 켠다)."""
        return self.send("RAWON" if on else "RAWOFF")

    def send_raw(self, ticks: list[int], khz: int = 38) -> str:
        """원본 재생. 긴 에어컨 신호는 보내는 데 1초쯤 걸린다."""
        if not 1 <= len(ticks) <= RAW_MAX or not all(1 <= t <= 255 for t in ticks):
            raise ValueError(f"원본은 1~{RAW_MAX}칸, 칸마다 1~255(50us 단위)여야 해요")
        return self.send(f"RAW {khz} {len(ticks)} " + " ".join(map(str, ticks)), timeout=5.0)

    def wait_ready(self, timeout: float = 4.0) -> bool:
        """아두이노는 시리얼을 열면 다시 켜진다(약 2초). ready 줄 또는 PING 답을 기다린다."""
        with self._cond:
            if self._cond.wait_for(lambda: self.ready, timeout):
                return True
        try:
            self.send("PING", 1.5)
            self.ready = True
        except (TimeoutError, RuntimeError):
            pass
        return self.ready

    def close(self) -> None:
        self._stop.set()
        try:
            self.ser.close()
        except Exception:  # noqa: BLE001
            pass


def power_to(target: str, bridge: Bridge, monitor, address: int = LG_ADDRESS, mode: str = "auto",
             on_wait: float = 25.0, off_wait: float = 8.0, toggle_cmd: int = POWER_TOGGLE) -> dict:
    """적외선으로 TV를 target(on/off)으로 만들고 와이파이 상태로 확인한다.
    mode: discrete(전용 코드만) / toggle(토글만) / auto(전용 → 안 되면 토글). 토글은 지금 상태가 다를 때만 쏜다."""
    wait = on_wait if target == "on" else off_wait
    if monitor.state == target:
        return {"ok": True, "already": True, "method": None, "seconds": 0.0}
    tried = []
    if mode in ("discrete", "auto"):
        bridge.nec(address, POWER_ON if target == "on" else POWER_OFF)
        tried.append("discrete")
        s = monitor.wait_for(target, wait)
        if s is not None:
            return {"ok": True, "method": "discrete", "seconds": s, "tried": tried}
    if mode in ("toggle", "auto") and monitor.state != target:
        bridge.nec(address, toggle_cmd)
        tried.append("toggle")
        s = monitor.wait_for(target, wait)
        if s is not None:
            return {"ok": True, "method": "toggle", "seconds": s, "tried": tried}
    return {"ok": False, "method": None, "seconds": None, "tried": tried, "state": monitor.state}


def send_code(bridge: Bridge, code: dict) -> str:
    """저장한 신호 하나 쏘기: {"kind": "raw", "khz", "ticks"} 또는 {"kind": "nec", "address", "command"}."""
    if code.get("kind") == "raw":
        return bridge.send_raw(code["ticks"], int(code.get("khz", 38)))
    if code.get("kind") == "nec":
        return bridge.nec(int(code["address"]), int(code["command"]), int(code.get("repeats", 0)))
    raise ValueError(f"모르는 신호 종류: {code.get('kind')}")
