"""중계 HTTP 서버: 가짜 TV·가짜 아두이노로 토큰, 상태, 켜기(적외선 + 셋톱), 끄기(와이파이), 앞 명령 중 거절을 시험한다.
눈치서버 src/devices/relay/client.ts가 보내고 읽는 모양 그대로다."""

import json
import socket
import threading
import urllib.error
import urllib.request

import pytest

from tvrelay import ir as IR
from tvrelay.fake import FakeSerial, FakeTV
from tvrelay.monitor import Monitor
from tvrelay.netcast import NetCast
from tvrelay.server import Relay, serve

TOKEN = "relay_token_for_tests_only"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def rig():
    made = {}

    def make(tv_on=False, key="123456", ir=True, discrete=True, stb=None):
        tv = FakeTV(port=free_port(), boot_s=0.3, on=tv_on)
        mon = Monitor("127.0.0.1", (tv.port,), interval=0.1).start()
        mon.wait_for("on" if tv_on else "off", 3)
        fs = FakeSerial(tv, discrete=discrete) if ir else None
        bridge = IR.Bridge("FAKE", opener=lambda: fs) if ir else None
        if bridge:
            bridge.wait_ready(2)
        relay = Relay(mon, NetCast("127.0.0.1", tv.port, key=key), bridge, stb=stb, on_wait=3, off_wait=3, log=lambda *_: None)
        srv = serve(relay, TOKEN, "127.0.0.1", free_port())
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        made.update(tv=tv, mon=mon, bridge=bridge, srv=srv)
        return f"http://127.0.0.1:{srv.server_address[1]}", tv, fs, relay
    yield make
    if made:
        made["srv"].shutdown()
        made["srv"].server_close()
        made["mon"].stop()
        if made["bridge"]:
            made["bridge"].close()
        made["tv"].shutdown()


def call(url, path, body=None, token=TOKEN):
    req = urllib.request.Request(url + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_token_and_state(rig):
    url, tv, _, _ = rig(tv_on=True)
    assert call(url, "/health", token="x") == (200, {"ok": True})
    assert call(url, "/api/devices/tv", token="wrong")[0] == 401
    code, body = call(url, "/api/devices/tv")
    assert code == 200 and body["power"] == "on" and body["ir"] is True


def test_on_by_ir_then_stb(rig):
    url, tv, fs, _ = rig(tv_on=False, stb={"kind": "nec", "address": 0x1, "command": 0x2})
    code, body = call(url, "/api/devices/tv/command", {"type": "on"})
    assert code == 200 and body == {"ok": True, "outcome": "done", "power": "on"}
    assert tv.on
    nec = [s for s in fs.sent if s.startswith("NEC")]
    assert nec[0].startswith("NEC 0x4 0xC4") and nec[-1].startswith("NEC 0x1 0x2")


def test_on_without_arduino_is_not_sent(rig):
    url, tv, _, _ = rig(tv_on=False, ir=False)
    code, body = call(url, "/api/devices/tv/command", {"type": "on"})
    assert body["outcome"] == "not_sent" and not body["ok"] and not tv.on


def test_on_unverified_when_tv_ignores(rig):
    url, tv, fs, relay = rig(tv_on=False)
    fs.tv = FakeTV(port=free_port(), on=False)              # 적외선이 다른 TV로 감(이 TV는 반응 없음)
    code, body = call(url, "/api/devices/tv/command", {"type": "on"})
    fs.tv.shutdown()
    assert body["ok"] and body["outcome"] == "unverified" and body["power"] == "off"


def test_off_by_wifi(rig):
    url, tv, fs, _ = rig(tv_on=True)
    code, body = call(url, "/api/devices/tv/command", {"type": "off"})
    assert body == {"ok": True, "outcome": "done", "power": "off"}
    assert tv.keys == [1] and not [s for s in fs.sent if s.startswith("NEC")]   # 적외선은 쓰지 않음


def test_off_falls_back_to_ir_without_pairing(rig):
    url, tv, fs, _ = rig(tv_on=True, key=None)
    code, body = call(url, "/api/devices/tv/command", {"type": "off"})
    assert body["outcome"] == "done" and not tv.on and any(s.startswith("NEC 0x4 0xC5") for s in fs.sent)


def test_bad_type_and_busy(rig):
    url, tv, _, relay = rig(tv_on=True)
    assert call(url, "/api/devices/tv/command", {"type": "level"})[0] == 400
    relay._busy.acquire()
    try:
        code, body = call(url, "/api/devices/tv/command", {"type": "off"})
    finally:
        relay._busy.release()
    assert code == 409 and body["outcome"] == "not_sent"


def test_short_token_refused():
    tv = FakeTV(port=free_port(), on=False)
    try:
        with pytest.raises(ValueError):
            serve(Relay(Monitor("127.0.0.1", (tv.port,))), "short")
    finally:
        tv.shutdown()
