"""LG NetCast TV(2012 NetCast 3.0 · 2013 NetCast 4.0)를 와이파이로 다루기. 표준 라이브러리만 씀.

경로와 키 코드는 Home Assistant가 쓰는 pylgnetcast 0.3.9와 같게 맞췄다.
  - 2012년형 이후: http://TV:8080/roap/api/{auth,command,data}
  - 2011년형 이전: http://TV:8080/hdcp/api/dtv_wifirc (명령만 /hdcp/api/command)
  - 모델 정보: /udap/api/data?target=rootservice.xml (User-Agent: UDAP/2.0)
페어링: AuthKeyReq를 보내면 TV 화면에 6자리 번호가 뜨고, 그 번호로 AuthReq → session을 받는다.
TV가 꺼지면 와이파이도 같이 꺼져서 응답이 없다 → '응답 있음 = 켜짐'으로 상태를 본다. 켜기는 와이파이로 못 한다.
"""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree

PORTS = (8080, 60128)
KEY_POWER, KEY_VOLUME_UP, KEY_VOLUME_DOWN, KEY_MUTE = 1, 24, 25, 26
XML = '<?xml version="1.0" encoding="utf-8"?>'


class NetCastError(Exception):
    pass


def reachable(host: str, ports=PORTS, timeout: float = 0.8) -> int | None:
    """TCP로 열린 포트를 찾는다(ping 권한 필요 없음). 열린 첫 포트, 없으면 None."""
    for p in ports:
        try:
            with socket.create_connection((host, p), timeout=timeout):
                return p
        except OSError:
            continue
    return None


def local_ip() -> str | None:
    """이 노트북의 공유기 쪽 IP. UDP connect는 패킷을 보내지 않고 길만 고른다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def discover(timeout: float = 3.0) -> list[dict]:
    """SSDP로 같은 공유기의 LG TV를 찾는다. [{ip, server, location}]"""
    found: dict[str, dict] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(0.5)
    try:
        for st in ("urn:schemas-udap:service:netrcu:1", "udap:rootservice", "ssdp:all"):
            msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
                   f"MX: 2\r\nST: {st}\r\nUSER-AGENT: UDAP/2.0\r\n\r\n")
            sock.sendto(msg.encode(), ("239.255.255.250", 1900))
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, (ip, _) = sock.recvfrom(4096)
            except socket.timeout:
                continue
            text = data.decode("utf-8", "replace")
            head = {k.strip().lower(): v.strip() for k, _, v in (ln.partition(":") for ln in text.split("\r\n")[1:]) if k}
            blob = text.lower()
            if "lg" in blob or "udap" in blob or "roap" in blob or ":8080/" in blob:
                found.setdefault(ip, {"ip": ip, "server": head.get("server", ""), "location": head.get("location", "")})
    except OSError:
        pass
    finally:
        sock.close()
    return list(found.values())


def scan(port: int = 8080, timeout: float = 0.3) -> list[str]:
    """노트북과 같은 /24 대역에서 port가 열린 기기(SSDP로 못 찾을 때). 이 집 공유기 안만 본다."""
    me = local_ip()
    if not me:
        return []
    base = me.rsplit(".", 1)[0]
    hosts = [f"{base}.{i}" for i in range(1, 255) if f"{base}.{i}" != me]
    with ThreadPoolExecutor(64) as ex:
        hits = ex.map(lambda h: h if reachable(h, (port,), timeout) else None, hosts)
    return [h for h in hits if h]


class NetCast:
    """한 TV와의 연결. 페어링 번호(key)가 있으면 명령 전에 session을 받는다."""

    def __init__(self, host: str, port: int = 8080, protocol: str = "roap", key: str | None = None, timeout: float = 3.0):
        self.host, self.port, self.protocol, self.key, self.timeout = host, port, protocol, key, timeout
        self.session: str | None = None

    # ---- HTTP
    def _url(self, kind: str, proto: str | None = None) -> str:
        proto = proto or self.protocol
        if proto == "hdcp" and kind != "command":
            kind = "dtv_wifirc"
        return f"http://{self.host}:{self.port}/{proto}/api/{kind}"

    def _req(self, url: str, body: str | None = None, ua: str | None = None) -> tuple[int, str]:
        headers = {"Content-Type": "application/atom+xml"}
        if ua:
            headers["User-Agent"] = ua
        req = urllib.request.Request(url, data=body.encode() if body is not None else None, headers=headers,
                                     method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    # ---- 알아보기
    def detect_protocol(self) -> str:
        """roap(2012~) 또는 hdcp(~2011). 둘 다 404면 roap로 둔다. 페어링 번호를 띄우지 않는 GET만 쓴다."""
        for proto in ("roap", "hdcp"):
            try:
                code, _ = self._req(self._url("data", proto) + "?target=volume_info")
            except OSError:
                continue
            if code != 404:
                self.protocol = proto
                return proto
        return self.protocol

    def device_info(self) -> dict | None:
        """모델명 등(UDAP rootservice.xml). 안 주는 TV도 있다."""
        try:
            code, text = self._req(f"http://{self.host}:{self.port}/udap/api/data?target=rootservice.xml", ua="UDAP/2.0")
            if code != 200:
                return None
            tree = ElementTree.fromstring(text.encode())
        except (OSError, ElementTree.ParseError):
            return None
        return {"model_name": tree.findtext("device/modelName"), "friendly_name": tree.findtext("device/friendlyName"),
                "uuid": tree.findtext("device/uuid")}

    # ---- 페어링
    def show_key(self) -> int:
        """TV 화면에 페어링 번호를 띄운다. HTTP 상태 코드를 돌려준다."""
        code, _ = self._req(self._url("auth"), XML + "<auth><type>AuthKeyReq</type></auth>")
        return code

    def pair(self, key: str | None = None) -> str:
        if key:
            self.key = key.strip()
        if not self.key:
            raise NetCastError("페어링 번호가 없어요")
        code, text = self._req(self._url("auth"), XML + f"<auth><type>AuthReq</type><value>{self.key}</value></auth>")
        if code != 200:
            raise NetCastError(f"페어링 실패 (HTTP {code}). 번호를 다시 확인하세요")
        try:
            session = ElementTree.fromstring(text.encode()).findtext("session")
        except ElementTree.ParseError:
            session = None
        if not session:
            raise NetCastError("TV가 session을 주지 않았어요")
        self.session = session
        return session

    # ---- 명령·조회
    def send_key(self, key_code: int) -> None:
        for attempt in range(2):                     # session이 만료됐으면 한 번 다시 페어링
            if not self.session:
                self.pair()
            body = XML + (f"<command><session>{self.session}</session><type>HandleKeyInput</type>"
                          f"<value>{key_code}</value></command>")
            code, _ = self._req(self._url("command"), body)
            if code == 200:
                return
            self.session = None
            if attempt:
                raise NetCastError(f"명령 실패 (HTTP {code})")

    def power_off(self) -> None:
        self.send_key(KEY_POWER)

    def volume(self) -> tuple[float, bool] | None:
        code, text = self._req(self._url("data") + "?" + urllib.parse.urlencode({"target": "volume_info"}))
        if code != 200:
            return None
        try:
            d = ElementTree.fromstring(text.encode()).find(".//data")
            return float(d.findtext("level")), d.findtext("mute") == "true"
        except (ElementTree.ParseError, AttributeError, TypeError, ValueError):
            return None
