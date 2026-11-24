"""TV 중계 실행.

  python -m tvrelay pair  --tv-host 192.168.0.23           TV 화면에 번호를 띄우고 입력받아 페어링 확인 → TV_PAIR_KEY로 쓸 값
  python -m tvrelay learn  --ir-port /dev/cu.usbserial-XXX       리모컨 신호 보기: 누르면 해석한 줄(NEC 0x4 0x8 등)이 찍힘
  python -m tvrelay record --ir-port /dev/cu.usbserial-XXX 이름  리모컨 버튼 하나를 원본으로 녹음해 이름으로 저장(구형 에어컨·셋톱)
  python -m tvrelay send   --ir-port /dev/cu.usbserial-XXX 이름  저장한 신호 쏘기
  python -m tvrelay codes                                         저장한 신호 목록
  TV_RELAY_TOKEN=... python -m tvrelay serve --host <Tailscale IP> --tv-host 192.168.0.23 --ir-port /dev/cu.usbserial-XXX [--stb 셋톱신호이름]
  TV_RELAY_TOKEN=... python -m tvrelay serve --fake        가짜 TV·가짜 아두이노로 띄우기(눈치서버 연결 시험)

토큰은 명령줄이 아니라 환경 변수 TV_RELAY_TOKEN으로만 받는다(셸 기록에 남지 않게). 눈치서버 .env의 TV_RELAY_TOKEN과 같은 값.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from . import codes as C
from . import ir as IR
from .monitor import Monitor
from .netcast import NetCast, NetCastError, reachable
from .server import Relay, serve


def _hex(s: str) -> int:
    return int(s, 0)


def cmd_pair(a) -> int:
    port = reachable(a.tv_host)
    if port is None:
        print(f"{a.tv_host}가 응답하지 않아요. TV가 켜져 있고 같은 공유기인지 보세요.")
        return 1
    nc = NetCast(a.tv_host, port)
    nc.detect_protocol()
    print(f"TV {a.tv_host}:{port} ({nc.protocol}) 모델: {(nc.device_info() or {}).get('model_name') or '모름'}")
    print("TV 화면에 번호를 띄웠어요." if nc.show_key() == 200 else "번호 띄우기 요청이 거절됐어요(메뉴가 열려 있으면 닫고 다시).")
    key = input("TV에 뜬 번호: ").strip()
    try:
        nc.pair(key)
    except (NetCastError, OSError) as e:
        print(f"실패: {e}")
        return 1
    print(f"페어링 성공. 중계를 띄울 때 TV_PAIR_KEY={key} 를 환경 변수로 주세요.")
    return 0


def cmd_learn(a) -> int:
    b = _bridge(a.ir_port)
    if not b:
        return 1
    print("수신 모듈에 리모컨을 대고 버튼을 누르세요. 끝내려면 Ctrl+C")
    seen = 0
    try:
        while True:
            for rx in b.rx[seen:]:
                print(f"  {rx['protocol']} 주소 0x{rx['address']:X} 명령 0x{rx['command']:X}")
            seen = len(b.rx)
            time.sleep(0.2)
    except KeyboardInterrupt:
        return 0
    finally:
        b.close()


def _bridge(port: str) -> IR.Bridge | None:
    b = IR.Bridge(port)
    if b.wait_ready():
        return b
    b.close()
    print("아두이노가 답하지 않아요. ir_bridge.ino를 올렸는지, 포트가 맞는지(ls /dev/cu.*), 시리얼 모니터를 닫았는지 보세요.")
    return None


def cmd_record(a) -> int:
    b = _bridge(a.ir_port)
    if not b:
        return 1
    try:
        print(f"'{a.name}': 수신 모듈(5cm 안)에 리모컨을 대고 버튼을 한 번 짧게 누르세요. ({a.timeout:.0f}초 기다림)")
        code = C.record(b, a.timeout)
    except ValueError as e:
        print(e)
        return 1
    finally:
        b.close()
    if not code:
        print("신호를 못 받았어요. 배선(수신 모듈 S → D2)과 거리를 보세요.")
        return 1
    C.save(a.name, code)
    d = code["decoded"]
    print(f"저장했어요: {a.name} (원본 {len(code['ticks'])}칸, 약 {sum(code['ticks']) * IR.TICK_US / 1000:.0f}ms)"
          + (f" · 해석: {d['protocol']} 0x{d['address']:X}/0x{d['command']:X}" if d else " · 해석 안 됨(원본으로 쏨)"))
    return 0


def cmd_send(a) -> int:
    try:
        code = C.get(a.name)
    except KeyError as e:
        print(e.args[0])
        return 1
    b = _bridge(a.ir_port)
    if not b:
        return 1
    try:
        for i in range(a.repeat):
            print(f"{a.name} 쏨: {IR.send_code(b, code)}")
            if i + 1 < a.repeat:
                time.sleep(a.gap)
    finally:
        b.close()
    return 0


def cmd_codes(a) -> int:
    codes = C.load()
    if not codes:
        print("저장한 신호가 없어요. python -m tvrelay record --ir-port … 이름")
    for name, c in codes.items():
        d = c.get("decoded")
        print(f"  {name:20s} {c['kind']:4s} " + (f"{len(c['ticks'])}칸" if c["kind"] == "raw" else f"0x{c['address']:X}/0x{c['command']:X}")
              + (f" · {d['protocol']} 0x{d['address']:X}/0x{d['command']:X}" if d else "") + f"  {c.get('at', '')}")
    return 0


def cmd_serve(a) -> int:
    token = os.environ.get("TV_RELAY_TOKEN", "")
    fake_tv = None
    if a.fake:
        from .fake import FakeSerial, FakeTV
        fake_tv = FakeTV(port=18080, boot_s=3.0, on=False)
        monitor = Monitor("127.0.0.1", (18080,)).start()
        nc = NetCast("127.0.0.1", 18080, key="123456")
        fs = FakeSerial(fake_tv)
        bridge = IR.Bridge("FAKE", opener=lambda: fs)
        bridge.wait_ready()
    else:
        if not a.tv_host:
            print("--tv-host가 필요해요(또는 --fake)")
            return 2
        port = reachable(a.tv_host) or 8080
        monitor = Monitor(a.tv_host).start()
        nc = NetCast(a.tv_host, port, key=os.environ.get("TV_PAIR_KEY") or None)
        bridge = None
        if a.ir_port:
            bridge = _bridge(a.ir_port)
            if not bridge:
                print("[경고] 아두이노 없이 띄워요. 켜기는 안 되고 끄기는 와이파이로만 합니다.")
    try:
        stb = C.get(a.stb) if a.stb else None
    except KeyError as e:
        print(e.args[0])
        return 2
    relay = Relay(monitor, nc, bridge, toggle_cmd=a.toggle, stb=stb)
    try:
        srv = serve(relay, token, a.host, a.port)
    except ValueError as e:
        print(e)
        return 2
    print(f"TV 중계: http://{a.host}:{a.port}" + ("  (가짜 TV·가짜 아두이노)" if a.fake else f"  TV {a.tv_host}")
          + f"  · 아두이노 {'연결' if relay._ir_ready() else '없음'} · 페어링 {'있음' if nc.key else '없음'}")
    print("끄려면 Ctrl+C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        monitor.stop()
        if bridge:
            bridge.close()
        if fake_tv:
            fake_tv.shutdown()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="tvrelay", description="동료 집 TV 중계(와이파이 상태 + 아두이노 적외선)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pair", help="TV 페어링 번호 확인")
    p.add_argument("--tv-host", required=True)
    p = sub.add_parser("learn", help="리모컨 신호 배우기")
    p.add_argument("--ir-port", required=True)
    p = sub.add_parser("record", help="리모컨 버튼 하나를 원본으로 녹음해 저장")
    p.add_argument("--ir-port", required=True)
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("name")
    p = sub.add_parser("send", help="저장한 신호 쏘기")
    p.add_argument("--ir-port", required=True)
    p.add_argument("--repeat", type=int, default=1, help="몇 번 쏠지(멀리서 안 먹을 때)")
    p.add_argument("--gap", type=float, default=0.3, help="여러 번 쏠 때 사이 초")
    p.add_argument("name")
    sub.add_parser("codes", help="저장한 신호 목록")
    p = sub.add_parser("serve", help="중계 HTTP 서버")
    p.add_argument("--host", default="127.0.0.1", help="받을 주소. 눈치서버에서 부르려면 이 노트북의 Tailscale IP")
    p.add_argument("--port", type=int, default=8530)
    p.add_argument("--tv-host", help="TV의 집 공유기 IP")
    p.add_argument("--ir-port", help="아두이노 시리얼 포트")
    p.add_argument("--toggle", type=_hex, default=IR.POWER_TOGGLE, help="배운 TV 전원 토글 명령(기본 0x08)")
    p.add_argument("--stb", metavar="이름", help="TV를 켠 뒤 쏠 셋톱 전원 신호(record로 저장한 이름)")
    p.add_argument("--fake", action="store_true", help="가짜 TV·가짜 아두이노")
    a = ap.parse_args()
    return {"pair": cmd_pair, "learn": cmd_learn, "record": cmd_record, "send": cmd_send, "codes": cmd_codes, "serve": cmd_serve}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
