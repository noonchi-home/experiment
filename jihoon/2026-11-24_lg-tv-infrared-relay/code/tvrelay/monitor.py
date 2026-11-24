"""TV 켜짐·꺼짐 감시: 0.5초마다 포트가 열리는지 본다. 바뀐 시각을 남기고, 원하는 상태가 될 때까지 기다릴 수 있다."""

from __future__ import annotations

import threading
import time

from .netcast import PORTS, reachable


class Monitor:
    def __init__(self, host: str, ports=PORTS, interval: float = 0.5, off_after: int = 2, probe=reachable):
        self.host, self.ports, self.interval, self.off_after, self.probe = host, tuple(ports), interval, off_after, probe
        self.state = "unknown"              # on / off / unknown
        self.since = time.time()
        self.events: list[dict] = []        # [{t, state}]
        self.cond = threading.Condition()
        self._stop = threading.Event()
        self._miss = 0
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "Monitor":
        self.thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _set(self, state: str) -> None:
        with self.cond:
            if state != self.state:
                self.state, self.since = state, time.time()
                self.events.append({"t": self.since, "state": state})
                del self.events[:-200]
                self.cond.notify_all()

    def _run(self) -> None:
        while not self._stop.is_set():
            t0 = time.time()
            ok = self.probe(self.host, self.ports, min(0.8, self.interval * 1.6)) is not None
            if ok:
                self._miss = 0
                self._set("on")
            else:
                self._miss += 1                # 한 번 놓친 것으로 꺼짐이라 하지 않음
                if self._miss >= self.off_after or self.state == "unknown":
                    self._set("off")
            self._stop.wait(max(0.0, self.interval - (time.time() - t0)))

    def wait_for(self, state: str, timeout: float) -> float | None:
        """state가 될 때까지 기다린다. 걸린 초(이미 그 상태면 0), 시간 안에 안 되면 None."""
        t0 = time.time()
        with self.cond:
            ok = self.cond.wait_for(lambda: self.state == state or self._stop.is_set(), timeout)
        return round(time.time() - t0, 2) if ok and self.state == state else None

    def snapshot(self) -> dict:
        with self.cond:
            return {"state": self.state, "since": self.since, "events": list(self.events[-30:])}
