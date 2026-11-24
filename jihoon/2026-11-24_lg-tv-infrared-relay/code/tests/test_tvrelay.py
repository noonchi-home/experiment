"""TV 중계: 가짜 NetCast TV·가짜 아두이노로 페어링·끄기·상태 감시·적외선 켜기(전용 → 토글 대신)를 시험한다."""

import socket
import threading
import time

import pytest

from tvrelay import ir as IR
from tvrelay.fake import FakeSerial, FakeTV
from tvrelay.monitor import Monitor
from tvrelay.netcast import NetCast, NetCastError, reachable


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until(fn, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def tv():
    t = FakeTV(port=free_port(), boot_s=0.3)
    yield t
    t.shutdown()


@pytest.fixture
def bridge(tv):
    made = []

    def make(discrete=True):
        fs = FakeSerial(tv, discrete=discrete)
        b = IR.Bridge("FAKE", opener=lambda: fs)
        assert b.wait_ready(2)
        made.append(b)
        return b, fs
    yield make
    for b in made:
        b.close()


@pytest.fixture
def monitor(tv):
    m = Monitor("127.0.0.1", (tv.port,), interval=0.1).start()
    yield m
    m.stop()


def test_netcast_pair_power_off_and_info(tv):
    nc = NetCast("127.0.0.1", tv.port)
    assert nc.detect_protocol() == "roap"
    assert nc.device_info()["model_name"].startswith("47LM6700")
    assert nc.show_key() == 200 and tv.shown_key
    with pytest.raises(NetCastError):
        nc.pair("000000")
    nc.pair("123456")
    assert nc.volume() == (12.0, False)
    nc.power_off()
    assert tv.keys == [1]
    assert wait_until(lambda: reachable("127.0.0.1", (tv.port,), 0.2) is None)


def test_monitor_sees_off_and_on(tv, monitor):
    assert monitor.wait_for("on", 3) is not None
    threading.Thread(target=tv.power, args=(False,)).start()
    assert monitor.wait_for("off", 3) is not None
    threading.Thread(target=tv.power, args=(True,)).start()
    s = monitor.wait_for("on", 3)
    assert s is not None and s >= 0.2                     # 부팅 시간만큼 늦게
    assert [e["state"] for e in monitor.events] == ["on", "off", "on"]


def test_parse_rx_and_learning(bridge):
    assert IR.parse_rx("RX NEC 0x4 0x8") == {"protocol": "NEC", "address": 4, "command": 8}
    assert IR.parse_rx("ok sent NEC 0x4 0x8") is None
    b, fs = bridge()
    assert b.send("PING") == "ok pong"
    with pytest.raises(RuntimeError):
        b.send("HELLO")
    fs.press_remote()
    assert wait_until(lambda: b.rx, 2)
    assert b.rx[0]["command"] == IR.POWER_TOGGLE


def test_self_echo_not_learned(bridge):
    b, _ = bridge()
    b.nec(4, 0x08)
    b._line("RX NEC 0x4 0x8")                            # 쏜 직후 수신 모듈이 자기 신호를 받은 것
    assert b.rx == []


@pytest.mark.parametrize("discrete,method", [(True, "discrete"), (False, "toggle")])
def test_power_to_falls_back_to_toggle(bridge, monitor, discrete, method):
    b, fs = bridge(discrete)
    monitor.wait_for("on", 3)
    r = IR.power_to("off", b, monitor, mode="auto", off_wait=2)
    assert r["ok"] and r["method"] == method
    r = IR.power_to("on", b, monitor, mode="auto", on_wait=2)
    assert r["ok"] and r["method"] == method
    sent = len(fs.sent)
    assert IR.power_to("on", b, monitor)["already"]      # 이미 켜져 있으면 쏘지 않음
    assert len(fs.sent) == sent


def test_power_to_reports_failure_when_tv_ignores(bridge, monitor, tv):
    b, fs = bridge(discrete=False)
    monitor.wait_for("on", 3)
    r = IR.power_to("off", b, monitor, mode="discrete", off_wait=0.8)
    assert not r["ok"] and r["tried"] == ["discrete"] and tv.on
