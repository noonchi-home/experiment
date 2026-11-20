from bisect import bisect_right
from collections import defaultdict
from datetime import date
from pathlib import Path
import hashlib
import json


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT.parent / "input" / "일별입력"
OUTCOMES = {"함", "하지 않음", "이미 함", "관찰 불가"}
READINESS = {"가능", "확인필요", "선행", "불필요", "위험"}
COMMON_GUARDS = ("요일","날짜종류","시간대","관찰위치","날씨","채널","동석자","실내온도구간")


def seconds(stamp):
    h, m, s = map(int, stamp.split(":"))
    return h * 3600 + m * 60 + s


def clock(t):
    return f"{t // 3600:02}:{t // 60 % 60:02}:{t % 60:02}"


def load_jsonl(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8-sig").splitlines() if s.strip()]


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


class Day:
    def __init__(self, folder):
        self.date = folder.name
        self.obs, self.changes, self.ticks = [], [], []
        self.frames, self.lines = {}, {}
        for line_no, line in enumerate((folder / "관찰.txt").read_text(encoding="utf-8").splitlines(), 1):
            stamp, loc, txt = line.split(" / ", 2)
            t = seconds(stamp)
            self.obs.append((t, loc, txt))
            self.frames[t] = (loc, txt)
            self.lines[t] = line_no
            if not self.ticks or self.ticks[-1] != t - 4 or self.frames[self.ticks[-1]] != (loc, txt):
                self.changes.append((t, loc, txt))
            self.ticks.append(t)
        self.signals = [dict(row, sec=seconds(row["시각"])) for row in load_jsonl(folder / "가전신호.jsonl")]
        self.prior_signals = {}
        self.by_time = defaultdict(list)
        for row in self.signals:
            self.by_time[row["sec"]].append(row)
        self.skies = json.loads((folder / "weather.json").read_text(encoding="utf-8"))
        self.temperatures = load_jsonl(folder / "실내온도.jsonl")
        self.hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}

    def frame(self, t):
        return self.frames.get(t)

    def weather(self, t):
        return self.skies[t // 3600]["날씨"]

    def last_signal(self, device, event, t):
        latest = self.prior_signals.get((device,event))
        for row in self.signals:
            if row["sec"] > t:
                break
            if (row["기기"],row["항목"]) == (device,event):
                latest = {**row,"날짜":self.date}
        return latest

    def guards(self, t):
        weekday = date.fromisoformat(self.date).weekday()
        ch = self.last_signal("TV","채널",t)
        power = self.last_signal("TV","전원",t)
        channel = "모름"
        if power and power["값"] == "켜짐" and ch and (ch["날짜"],ch["sec"]) >= (power["날짜"],power["sec"]):
            channel = ch["값"]
        guest = "모름"
        for _, _, text in self.obs[bisect_right(self.ticks,t-1801):bisect_right(self.ticks,t)]:
            if "방문객" in text:
                guest = "방문객 있음"
            if "현관문이 닫히고 현관 안쪽에는 사용자만" in text:
                guest = "모름"
        band = int(self.temperatures[t // 1800]["값_C"] // 2) * 2
        return {"요일":"월화수목금토일"[weekday], "날짜종류":"평일" if weekday < 5 else "주말",
                "시간대":f"{t//3600:02}시대","관찰위치":self.frames.get(t,("모름",""))[0],
                "날씨":"비" if self.weather(t) == "비" else "비 없음","채널":channel,"동석자":guest,
                "실내온도구간":f"{band}도 이상 {band+2}도 미만"}

    def covered(self, a, b):
        return bisect_right(self.ticks, b) - bisect_right(self.ticks, a - 1) == (b - a) // 4 + 1

    def evidence(self, t):
        out = {"시각": clock(t)}
        if t in self.frames:
            out.update({"관찰줄": self.lines[t], "위치": self.frames[t][0], "관찰": self.frames[t][1]})
        if self.by_time.get(t):
            out["신호ID"] = [r["신호ID"] for r in self.by_time[t]]
        return out

    def case(self, rule, t, result, evidence, checks, guards=None, reason=""):
        if result not in OUTCOMES or not checks or checks[0][0] != t:
            raise ValueError((self.date, rule, t, result, checks))
        if any(state not in READINESS or when < t or when % 4 for when, state, _ in checks):
            raise ValueError((rule, checks))
        times = sorted(set([t] + list(evidence)))
        if any(v not in self.frames and v not in self.by_time for v in times):
            raise ValueError((self.date, rule, "원본 근거 부재", times))
        return dict(id=rule, t=t, date=self.date, result=result, evidence=times,
                    checks=sorted(checks, key=lambda x: x[0]), guards=guards or {}, reason=reason)
