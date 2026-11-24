"""원본 녹음·재생(구형 에어컨·셋톱): 가짜 아두이노로 녹음 → 저장 → 다시 쏘기, 해석되는 리모컨(NEC)은 해석도 같이 남기기,
버퍼 넘침, 셋톱 신호를 TV 켠 뒤 쏘기를 시험한다."""

import socket
import threading

import pytest

from tvrelay import codes as C
from tvrelay import ir as IR
from tvrelay.fake import FakeSerial, FakeTV
from tvrelay.monitor import Monitor
from tvrelay.server import Relay

AIRCON = [180, 90] + [11, 33, 11, 11] * 60 + [11]          # 구형 에어컨 같은 긴 원본(해석 안 됨)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def rig():
    tv = FakeTV(port=free_port(), boot_s=0.3, on=False)
    fs = FakeSerial(tv)
    b = IR.Bridge("FAKE", opener=lambda: fs)
    assert b.wait_ready(2)
    yield tv, fs, b
    b.close()
    tv.shutdown()


def press_later(fn, *args, delay=0.3):
    threading.Timer(delay, fn, args).start()


def test_parse_raw():
    assert IR.parse_raw("RXRAW 3 180 90 11") == [180, 90, 11]
    assert IR.parse_raw("RXRAW 4 180 90 11") is None
    assert IR.parse_raw("RX NEC 0x4 0x8") is None


def test_record_unknown_remote_then_replay(rig, tmp_path):
    tv, fs, b = rig
    press_later(fs.press_raw, AIRCON)
    code = C.record(b, timeout=3, settle=0.2)
    assert code["kind"] == "raw" and code["ticks"] == AIRCON and code["decoded"] is None
    assert fs.raw_on is False                                 # 녹음이 끝나면 원본 알림을 끈다
    path = tmp_path / "codes.json"
    C.save("aircon_on", code, path)
    assert IR.send_code(b, C.get("aircon_on", path)) == f"ok sent RAW {len(AIRCON)}"
    assert fs.raw_sent == [AIRCON]


def test_record_nec_keeps_decoded(rig):
    tv, fs, b = rig
    press_later(fs.press_remote)
    code = C.record(b, timeout=3, settle=0.3)
    assert len(code["ticks"]) == 67 and code["decoded"] == {"protocol": "NEC", "address": 4, "command": 8}


def test_record_timeout_and_overflow(rig):
    tv, fs, b = rig
    assert C.record(b, timeout=0.3) is None
    press_later(fs._emit, "RXOVF", delay=0.1)
    with pytest.raises(ValueError):
        C.record(b, timeout=2)


def test_send_raw_checks_size(rig):
    _, _, b = rig
    with pytest.raises(ValueError):
        b.send_raw([0, 10])
    with pytest.raises(ValueError):
        b.send_raw([10] * (IR.RAW_MAX + 1))


def test_names_and_missing(tmp_path):
    with pytest.raises(ValueError):
        C.save("에어컨 켜기", {"kind": "nec", "address": 1, "command": 2}, tmp_path / "c.json")
    with pytest.raises(KeyError):
        C.get("none", tmp_path / "c.json")


def test_relay_sends_stb_after_tv_on(rig):
    tv, fs, b = rig
    mon = Monitor("127.0.0.1", (tv.port,), interval=0.1).start()
    try:
        mon.wait_for("off", 3)
        stb = {"kind": "raw", "khz": 38, "ticks": [100, 50, 10, 20, 10]}
        code, body = Relay(mon, None, b, stb=stb, on_wait=3, log=lambda *_: None).command("on")
        assert body["outcome"] == "done" and tv.on and fs.raw_sent == [stb["ticks"]]
    finally:
        mon.stop()
