"""가상 스마트홈 허브와 가상 로봇. 모델이 고른 task를 둘 중 하나에 요청한다(실제 기기·네트워크는 없다).

허브   scenarios/<시나리오>/hub.json에 등록된 가전(인덕션, 식기세척기, 냉장고)만 다룬다. 연결(connect) 때 기기 목록을
       돌려주고, 상태 조회(status)와 명령(command)을 받는다. 등록되지 않은 기기·명령은 거부한다.
로봇   모든 행동을 할 수 있다고 가정한다. 요청을 받으면 수행했다고 답한다. 촬영 요청에는 가상 사진 주소를 돌려준다.
실행   task_specs.json의 via(hub / robot)대로 요청한다. then이 있는 task는 허브가 알려 준 상태에 따라 다음 요청을 고른다
       (예: 식기세척기 상태 확인 -> 가동 중이면 남은 시간 조회, 가동 종료면 로봇에게 내부 사진 요청).
"""
from __future__ import annotations

import copy


class HubError(RuntimeError):
    pass


class SmartHomeHub:
    def __init__(self, spec: dict, state: dict | None = None):
        """spec: hub.json. state: 기기별 처음 상태(케이스마다 다를 수 있음). 없으면 hub.json의 state."""
        self.name = spec["hub"]
        self.devices = {d: {"commands": v["commands"], "state": copy.deepcopy(v["state"])} for d, v in spec["devices"].items()}
        for d, s in (state or {}).items():
            self._device(d)["state"].update(s)
        self.connected = False
        self.log: list[dict] = []

    def connect(self) -> dict:
        self.connected = True
        return {"hub": self.name, "connected": True, "devices": {d: v["commands"] for d, v in self.devices.items()}}

    def _device(self, device: str) -> dict:
        if device not in self.devices:
            raise HubError(f"device not registered on the hub: {device}")
        return self.devices[device]

    def status(self, device: str) -> dict:
        return self.command(device, "status")

    def command(self, device: str, command: str, **args) -> dict:
        if not self.connected:
            raise HubError("hub is not connected")
        d = self._device(device)
        if command not in d["commands"]:
            raise HubError(f"{device} does not support {command}")
        s = d["state"]
        if command == "power_on":
            s["power"] = "on"
        elif command == "power_off":
            s["power"] = "off"
            if "cycle" in s:
                s["cycle"], s["remaining_min"] = "stopped", 0
        elif command == "start":  # 식기세척기 세척 시작
            s.update(power="on", cycle="running", remaining_min=args.get("minutes", 90))
        elif command == "set_timer":
            s["timer_min"] = args.get("minutes", 10)
        elif command == "set_temperature":
            s["temperature_c"] = args.get("celsius", s.get("temperature_c"))
        elif command == "remaining_time" and s.get("cycle") != "running":
            raise HubError(f"{device} is not running")
        out = {"device": device, "command": command, "state": dict(s)}
        self.log.append(out)
        return out


class VirtualRobot:
    def __init__(self):
        self.connected = False
        self.log: list[dict] = []

    def connect(self) -> dict:
        self.connected = True
        return {"robot": "virtual robot", "connected": True, "can_do": "any task"}

    def request(self, text: str, photo_of: str | None = None) -> dict:
        out = {"request": text, "done": True}
        if photo_of:
            out["photo"] = f"virtual://photo/{photo_of.replace(' ', '_')}"  # 가상 로봇이라 실제 사진은 없다
        self.log.append(out)
        return out


def execute(text: str, spec: dict, hub: SmartHomeHub, robot: VirtualRobot) -> dict:
    """task 하나를 허브나 로봇에 요청한다. then이 있으면 허브가 알려 준 상태(state_key 값)로 다음 요청을 고른다."""
    if spec["via"] == "hub":
        out = {"via": "hub", **hub.command(spec["device"], spec["command"], **spec.get("args", {}))}
    else:
        out = {"via": "robot", **robot.request(text, spec.get("photo_of"))}
    then = spec.get("then")
    if then:
        value = out["state"].get(then["state_key"])
        nxt = then["cases"].get(value)
        out["then"] = {"because": f"{then['state_key']}={value}", "text": nxt["text"] if nxt else "nothing more",
                       "result": execute(nxt["text"], nxt, hub, robot) if nxt else None}
    return out
