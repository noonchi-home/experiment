"""Make one evening day (about 5 minutes, one line per second): a meal, a can of coffee, then
studying, which is a real video turned into text (runs/영상N/record.txt).
(저녁 하루 만들기: 밥 → 커피 캔 → 공부(실제 영상 글))

The synthetic lines are built from pieces of what Qwen 3.5 27B actually wrote when it watched
real videos: the four desk videos of this experiment and ai/artifacts/routine_vllm_fsm_2026-11-04
(eating from a bowl, drinking from a can, leaving the desk with a bowl). Each second is written
anew, so the same scene is said slightly differently from line to line, as Qwen does:
subject (The person / A person), seat phrase, activity phrase, object names, where they lie,
and three sentence shapes; after something is done, a few lines still say what was just done.

The person does four robot tasks themselves (scenarios/routine/tasks.json wording):
  bowl -> dishwasher, can of coffee -> next to the person (brought back on the same trip),
  empty can -> designated storage area, glass -> dishwasher (the real video).
What happens out of view is told by one sound line, as in the real video lines.
No model is called. The answer key goes to a separate file and is never given to a model.

Usage: python make_days.py --days 1 [--out ../data]
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
START = datetime(2026, 11, 18, 20, 0, 0)
SEED = 20261118
VIDEO_FIRST_LINE = 8  # the video lines start 8 s into each video (5 frames 2 s apart)

# ---------------------------------------------------------------- pieces (English, Korean)
SUBJECT = [("The person", "사람이")] * 7 + [("A person", "한 사람이")] * 2
SEAT = [("is sitting at the desk", "책상에 앉아"), ("is sitting at a desk", "책상에 앉아"),
        ("is seated at the desk", "책상에 앉아")]
ACT = {  # "-ing" phrase, Korean stem that takes "있고/있다"
    "typing": [("actively typing on a laptop", "노트북 타자를 열심히 치고"),
               ("typing on a laptop", "노트북 타자를 치고"),
               ("working on a laptop", "노트북으로 일하고"),
               ("focused on a laptop", "노트북에 집중하고"),
               ("using a laptop", "노트북을 쓰고")],
    "writing": [("actively writing in a notebook with a pen", "펜으로 공책에 열심히 쓰고"),
                ("writing in a notebook with a pen", "펜으로 공책에 쓰고"),
                ("holding a pen and writing in a notebook", "펜을 쥐고 공책에 쓰고")],
    "phone": [("actively using a smartphone", "휴대폰을 열심히 쓰고"),
              ("using their smartphone", "휴대폰을 쓰고"),
              ("looking at their phone", "휴대폰을 보고"),
              ("holding and looking at a smartphone", "휴대폰을 들고 보고"),
              ("focused on their smartphone", "휴대폰에 집중하고")],
    "eating": [("actively eating from a bowl with a spoon", "숟가락으로 그릇에 담긴 음식을 열심히 먹고"),
               ("eating from a bowl with a spoon", "숟가락으로 그릇에 담긴 음식을 먹고"),
               ("actively eating from a bowl of food", "그릇에 담긴 음식을 열심히 먹고")],
    "eating_phone": [("eating from a bowl while looking at their phone", "휴대폰을 보면서 그릇에 담긴 음식을 먹고"),
                     ("eating from a bowl while holding a phone in their other hand",
                      "다른 손에 휴대폰을 든 채 그릇에 담긴 음식을 먹고")],
    "resting": [("resting their hands on the table", "두 손을 책상 위에 올려놓고 쉬고"),
                ("looking ahead with their hands resting on the table", "두 손을 책상 위에 올려놓고 앞을 보고")],
    "stretching": [("stretching their arm upwards", "팔을 위로 뻗어 기지개를 켜고"),
                   ("stretching their arms", "두 팔을 뻗어 기지개를 켜고")],
}
OBJ = {
    ("glass", "water"): [("a glass of water", "물 잔"), ("a glass mug of water", "물이 든 유리 머그잔"),
                         ("a glass of water", "물이 든 유리잔")],
    ("bowl", "food"): [("a bowl of food", "음식이 담긴 그릇"), ("a bowl", "그릇"), ("a bowl of rice", "밥그릇")],
    ("bowl", "empty"): [("an empty bowl", "빈 그릇"), ("a used bowl", "다 먹은 그릇")],
    ("can", "full"): [("a can of coffee", "커피 캔"), ("a coffee can", "커피 캔"), ("a can", "캔")],
    ("can", "empty"): [("an empty can", "빈 캔"), ("an empty coffee can", "빈 커피 캔")],
    ("laptop", "on"): [("an open laptop", "펼친 노트북"), ("a laptop", "노트북")],
    ("notebook", "on"): [("a notebook", "공책"), ("an open notebook", "펼친 공책")],
    ("phone", "on"): [("a phone", "휴대폰"), ("a smartphone", "휴대폰")],
}
LOC_WITH = [("nearby", "근처에"), ("on the table", "책상 위에"), ("in front of them", "앞에"),
            ("resting nearby", "근처에"), ("resting on the table nearby", "근처 책상 위에")]
LOC_WHILE = [("nearby", "근처에"), ("on the table", "책상 위에"), ("on the desk", "책상 위에"),
             ("to their left", "왼쪽 책상 위에")]
PAST = {  # what was just done, said again for a few lines ("has ..., and is now ...")
    "sip_glass": [("has finished drinking from the glass, placed it back on the desk",
                   "유리컵으로 마시고 나서 책상에 다시 내려놓았고,"),
                  ("has just taken a drink from a glass of water, which is now resting on the table, and",
                   "방금 물 잔으로 한 모금 마셨고 잔은 책상 위에 있으며,")],
    "ate": [("has finished eating and set the spoon down in the bowl", "다 먹고 숟가락을 그릇에 내려놓았고,"),
            ("has just finished eating", "방금 다 먹었고,")],
    "can_down": [("has just sat down at the desk with a can of coffee, placing it on the table next to them, and",
                  "커피 캔을 들고 방금 책상에 앉아 캔을 옆 책상 위에 내려놓았고,")],
    "sip_can": [("has just placed the can back on the desk after taking a sip", "방금 캔으로 한 모금 마시고 책상에 다시 내려놓았고,"),
                ("has finished drinking from the can, placed it on the desk", "캔으로 마시고 나서 책상에 내려놓았고,")],
    "coffee_done": [("has finished the coffee and set the empty can down on the desk",
                     "커피를 다 마시고 빈 캔을 책상에 내려놓았고,"),
                    ("has finished drinking from the can, placed the empty can on the desk",
                     "캔으로 다 마시고 빈 캔을 책상에 내려놓았고,")],
    "back": [("has returned to the desk and sat down", "책상으로 돌아와 앉았고,"),
             ("has just sat down at the desk", "방금 책상에 앉았고,")],
    "stretched": [("has just finished stretching", "방금 기지개를 마쳤고,")],
}
EVENT = {  # one line each; {S} subject, {seat} seat phrase
    "reach_glass": [("{S} {seat} and has just reached out to grab the glass of water.",
                     "{K} 책상에 앉아 있고, 방금 물 잔을 잡으려고 손을 뻗었다.")],
    "drink_glass": [("{S} is currently holding a glass cup and drinking from it while sitting at the desk.",
                     "{K} 책상에 앉아 유리컵을 들고 마시고 있다."),
                    ("{S} is holding a glass mug to their mouth and drinking from it.",
                     "{K} 유리 머그잔을 입에 대고 마시고 있다.")],
    "last_bite": [("{S} {seat} and is taking the last spoonful from the bowl.",
                   "{K} 책상에 앉아 그릇에 남은 마지막 한 숟가락을 먹고 있다.")],
    "ate": [("{S} has finished eating and set the spoon down in the empty bowl.",
             "{K} 다 먹고 숟가락을 빈 그릇에 내려놓았다."),
            ("{S} {seat} with an empty bowl in front of them, appearing to have finished eating.",
             "{K} 빈 그릇을 앞에 두고 책상에 앉아 있고, 다 먹은 것처럼 보인다.")],
    "pick_bowl": [("{S} has finished eating and is holding the empty bowl, preparing to clear the table.",
                   "{K} 다 먹고 빈 그릇을 들고 있으며, 상을 치우려는 것처럼 보인다."),
                  ("{S} {seat} and is picking up the empty bowl with the spoon in it.",
                   "{K} 책상에 앉아 숟가락이 든 빈 그릇을 집어 들고 있다.")],
    "stand_bowl": [("{S} is standing at the desk holding the empty bowl.", "{K} 빈 그릇을 들고 책상 앞에 서 있다."),
                   ("{S} has stood up from the desk holding the empty bowl.", "{K} 빈 그릇을 들고 책상에서 일어섰다.")],
    "leave_bowl": [("{S} has picked up the bowl and is walking away from the desk towards the kitchen area.",
                    "{K} 그릇을 들고 책상에서 주방 쪽으로 걸어가고 있다."),
                   ("{S} has finished eating, picked up the bowl, and is leaving the desk area.",
                    "{K} 다 먹고 그릇을 집어 들고 책상 쪽을 떠나고 있다.")],
    "back_can": [("{S} has returned to the desk holding a can of coffee.", "{K} 커피 캔을 들고 책상으로 돌아왔다."),
                 ("{S} is walking back to the desk with a can of coffee in their hand.",
                  "{K} 손에 커피 캔을 들고 책상으로 돌아오고 있다.")],
    "can_down": [("{S} has just sat down at the desk with a can of coffee, placing it on the table next to them.",
                  "{K} 커피 캔을 들고 방금 책상에 앉았고, 캔을 옆 책상 위에 내려놓았다.")],
    "open_can": [("{S} {seat} and is opening a can of coffee.", "{K} 책상에 앉아 커피 캔을 따고 있다.")],
    "drink_can": [("{S} {seat} using a laptop and currently drinking from a can.",
                   "{K} 책상에 앉아 노트북을 쓰면서 캔으로 마시고 있다."),
                  ("{S} is holding a can of coffee to their mouth and drinking from it.",
                   "{K} 커피 캔을 입에 대고 마시고 있다.")],
    "can_back": [("{S} {seat} working on a laptop and has just placed the can back on the desk after taking a sip.",
                  "{K} 책상에 앉아 노트북으로 일하고 있고, 방금 캔으로 한 모금 마시고 책상에 다시 내려놓았다.")],
    "coffee_done": [("{S} has finished the coffee and set the empty can down on the desk.",
                     "{K} 커피를 다 마시고 빈 캔을 책상에 내려놓았다.")],
    "pick_can": [("{S} {seat} and is picking up the empty can from the desk.",
                  "{K} 책상에 앉아 책상 위의 빈 캔을 집어 들고 있다."),
                 ("{S} has stopped what they were doing and is picking up the empty can from the desk.",
                  "{K} 하던 일을 멈추고 책상에서 빈 캔을 집어 들고 있다.")],
    "stand_can": [("{S} has stood up from the desk holding the empty can.", "{K} 빈 캔을 들고 책상에서 일어섰다.")],
    "leave_can": [("{S} is holding the empty can and walking away from the desk.",
                   "{K} 빈 캔을 들고 책상에서 걸어 나가고 있다.")],
    "back_empty": [("{S} has returned to the desk empty-handed.", "{K} 빈손으로 책상으로 돌아왔다."),
                   ("{S} is walking back towards the desk area empty-handed.", "{K} 빈손으로 책상 쪽으로 돌아오고 있다.")],
}
AWAY = [("The person has left the desk area, leaving {O} on the table.", "사람은 책상 쪽을 떠났고, 책상 위에 {Q} 남아 있다."),
        ("The person is out of view; {O} remain on the desk.", "사람은 보이지 않고, 책상 위에 {Q} 있다."),
        ("The person is absent from the desk, leaving {O} on the table.", "사람은 책상에 없고, 책상 위에 {Q} 남아 있다.")]
SOUND = {"bowl": (" The sound of the bowl being placed in the dishwasher comes from the kitchen.",
                  " 주방에서 그릇을 식기세척기에 넣는 소리가 난다."),
         "can": (" The sound of the empty can being put away in the storage area comes from the kitchen.",
                 " 주방 쪽에서 빈 캔을 보관 장소에 두는 소리가 난다.")}


def josa(word: str, pair: tuple[str, str]) -> str:
    code = ord(word[-1]) - 0xAC00
    return word + (pair[0] if 0 <= code <= 11171 and code % 28 else pair[1])


def join_en(items: list[str]) -> str:
    return items[0] if len(items) == 1 else (" and ".join(items) if len(items) == 2
                                             else ", ".join(items[:-1]) + ", and " + items[-1])


def join_ko(items: list[str]) -> str:
    return items[0] if len(items) == 1 else (josa(items[0], ("과", "와")) + " " + items[1] if len(items) == 2
                                             else ", ".join(items))


class Writer:
    """Writes one line per second from the scene state, with Qwen-like variety."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.state = {"glass": "water", "bowl": None, "can": None, "laptop": "on", "notebook": "on", "phone": "on"}
        self.recent: tuple[str, int] | None = None  # (what was just done, lines left to say it again)

    def pick(self, options):
        return self.rng.choice(options)

    def objects(self, focus: list[str], skip: set[str]) -> list[tuple[str, str]]:
        chosen = []
        for name in focus:
            if self.state.get(name) and name not in skip and self.rng.random() < 0.85:
                chosen.append(self.pick(OBJ[(name, self.state[name])]))
        if self.rng.random() < 0.1:
            return []
        others = [n for n in ("laptop", "notebook", "phone") if self.state.get(n) and n not in skip and n not in focus]
        if others and (not chosen or (len(chosen) < 2 and self.rng.random() < 0.25)):
            name = self.pick(others)
            chosen.append(self.pick(OBJ[(name, self.state[name])]))
        return chosen

    def scene(self, act: str, focus: list[str]) -> tuple[str, str]:
        (s_en, s_ko), (seat_en, _) = self.pick(SUBJECT), self.pick(SEAT)
        a_en, a_ko = self.pick(ACT[act])
        skip = {"bowl"} if act.startswith("eating") else set()
        skip |= {"phone"} if "phone" in act else set()
        skip |= {"laptop"} if act == "typing" else set()
        objs = self.objects(focus, skip)
        if self.recent and self.recent[1] > 0 and self.rng.random() < 0.75:
            said = {"sip_glass": "glass", "ate": "bowl"}.get(self.recent[0], "can")
            objs = [o for o in objs if said not in o[0] and not (said == "glass" and "mug" in o[0])]
            p_en, p_ko = self.pick(PAST[self.recent[0]])
            self.recent = (self.recent[0], self.recent[1] - 1)
            with_objs = objs and self.rng.random() < 0.5
            tail_en = ", with " + join_en([o[0] for o in objs]) + " nearby" if with_objs else ""
            joint = " " if p_en.endswith(" and") else ", and "
            en = f"{s_en} {p_en}{joint}is now {a_en}{tail_en}."
            if with_objs:
                ko = f"{s_ko} {p_ko} 지금은 {a_ko} 있고, 근처에 {josa(join_ko([o[1] for o in objs]), ('이', '가'))} 있다."
            else:
                ko = f"{s_ko} {p_ko} 지금은 {a_ko} 있다."
            return en, ko
        if self.recent:
            self.recent = (self.recent[0], self.recent[1] - 1) if self.recent[1] > 0 else None
        if not objs:
            return f"{s_en} {seat_en} and {a_en}.", f"{s_ko} 책상에 앉아 {a_ko} 있다."
        o_en, o_ko = join_en([o[0] for o in objs]), join_ko([o[1] for o in objs])
        if self.rng.random() < 0.55:
            l_en, l_ko = self.pick(LOC_WITH)
            return (f"{s_en} {seat_en}, {a_en}, with {o_en} {l_en}.",
                    f"{s_ko} 책상에 앉아 {a_ko} 있고, {l_ko} {josa(o_ko, ('이', '가'))} 있다.")
        if " while " in a_en:  # one "while" per sentence
            l_en, l_ko = self.pick(LOC_WITH)
            return (f"{s_en} {seat_en}, {a_en}, with {o_en} {l_en}.",
                    f"{s_ko} 책상에 앉아 {a_ko} 있고, {l_ko} {josa(o_ko, ('이', '가'))} 있다.")
        l_en, l_ko = self.pick(LOC_WHILE)
        verb = "sits" if len(objs) == 1 else "sit"
        return (f"{s_en} {seat_en} {a_en}, while {o_en} {verb} {l_en}.",
                f"{s_ko} 책상에 앉아 {a_ko} 있고, {l_ko} {josa(o_ko, ('이', '가'))} 놓여 있다.")

    def event(self, name: str) -> tuple[str, str]:
        (s_en, s_ko), (seat_en, _) = self.pick(SUBJECT), self.pick(SEAT)
        en, ko = self.pick(EVENT[name])
        return en.format(S=s_en, seat=seat_en), ko.format(K=s_ko)

    def away(self, sound: str | None = None) -> tuple[str, str]:
        left = [self.pick(OBJ[(n, self.state[n])]) for n in ("glass", "laptop") if self.state.get(n)]
        if self.state.get("can"):
            left.insert(0, self.pick(OBJ[("can", self.state["can"])]))
        en, ko = self.pick(AWAY)
        en = en.format(O=join_en([o[0] for o in left]))
        ko = ko.format(Q=josa(join_ko([o[1] for o in left]), ("이", "가")))
        if sound:
            en, ko = en + SOUND[sound][0], ko + SOUND[sound][1]
        return en, ko


def video_lines(n: int) -> list[tuple[int, str, str]]:
    """(seconds into the video, English, Korean) from the real-video record."""
    folder = EXP / "runs" / f"영상{n}"
    en = [l for l in (folder / "record.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    ko = {l[:8]: l[11:] for l in (folder / "record_ko.txt").read_text(encoding="utf-8").splitlines() if l[:2] == "20"}
    return [(int(l[3:5]) * 60 + int(l[6:8]), l[11:], ko[l[:8]]) for l in en]


def build_day(day: int, video: int) -> tuple[list[tuple[str, str]], dict]:
    rng = random.Random(SEED + day)
    w = Writer(rng)
    lines: list[tuple[str, str]] = []
    key: dict[str, list[int] | int] = {}

    def mark(name: str, many: bool = False):
        t = len(lines)
        if many:
            key.setdefault(name, []).append(t)
        else:
            key[name] = t

    def scene(act: str, focus: list[str], seconds: int):
        for _ in range(seconds):
            lines.append(w.scene(act, focus))

    def event(name: str, seconds: int = 1):
        for _ in range(seconds):
            lines.append(w.event(name))

    # 1. Meal (bowl of food, glass of water on the desk). One sip of water partway through.
    w.state["bowl"] = "food"
    eat = rng.randint(55, 70)
    sip_at = rng.randint(15, eat - 20)
    phone_from = rng.randint(5, eat - 15)
    t = 0
    while t < eat:
        if t == sip_at:
            mark("sip_water", True)
            event("reach_glass"); event("drink_glass", rng.randint(2, 3))
            w.recent = ("sip_glass", rng.randint(3, 6)); t += 4; continue
        act = "eating_phone" if phone_from <= t < phone_from + 10 else "eating"
        scene(act, ["glass"], 1); t += 1
    mark("last_bite"); event("last_bite", 2)
    w.state["bowl"] = "empty"
    mark("finished_eating"); event("ate")
    w.recent = ("ate", rng.randint(3, 6))
    scene(rng.choice(["phone", "resting"]), ["bowl", "glass"], rng.randint(12, 30))
    # 2. Bowl to the dishwasher and a can of coffee back on the same trip.
    mark("pick_up_bowl"); event("pick_bowl", 2); event("stand_bowl", 2); event("leave_bowl", 2)
    w.state["bowl"] = None
    away = rng.randint(7, 11)
    mark("out_of_view_1")
    for i in range(away):
        if i == away // 2:
            mark("sound_bowl_in_dishwasher")
        lines.append(w.away("bowl" if i == away // 2 else None))
    event("back_can", 2)
    w.state["can"] = "full"
    mark("can_next_to_person"); event("can_down")
    w.recent = ("can_down", rng.randint(2, 4))
    # 3. Coffee: open, sips between typing and the phone, maybe a stretch, the last sip.
    event("open_can", 2)
    sips = rng.randint(2, 3)
    for k in range(sips):
        mark("sip_coffee", True)
        event("drink_can", rng.randint(2, 3)); event("can_back")
        w.recent = ("sip_can", rng.randint(2, 5))
        scene(rng.choice(["typing", "typing", "phone"]), ["can", "glass"], rng.randint(8, 18))
        if k == 0 and rng.random() < 0.6:
            scene("stretching", ["can"], rng.randint(3, 5)); w.recent = ("stretched", 2)
    mark("last_coffee"); event("drink_can", rng.randint(2, 3))
    w.state["can"] = "empty"
    mark("finished_coffee"); event("coffee_done")
    w.recent = ("coffee_done", rng.randint(3, 6))
    scene(rng.choice(["typing", "phone"]), ["can", "glass"], rng.randint(10, 35))
    # 4. Empty can to the storage area.
    mark("pick_up_can"); event("pick_can"); event("stand_can", 2); event("leave_can", 2)
    w.state["can"] = None
    away = rng.randint(5, 9)
    mark("out_of_view_2")
    for i in range(away):
        if i == away // 2:
            mark("sound_can_in_storage")
        lines.append(w.away("can" if i == away // 2 else None))
    event("back_empty", 2)
    w.recent = ("back", 3)
    scene("typing", ["glass"], rng.randint(6, 14))
    # 5. Studying: the real video lines, re-timed. Then a few seconds without the glass.
    clip_start = len(lines)
    key["video"] = video
    key["video_starts_at"] = clip_start
    for second, en, ko in video_lines(video):
        lines.append((en, ko))
    vk = json.loads((EXP / "answer_key.json").read_text(encoding="utf-8"))["videos"][f"영상{video}"]
    shift = clip_start - VIDEO_FIRST_LINE
    key["video_events"] = {name: ([[a + shift, b + shift] for a, b in v] if name == "sips"
                                  else [v[0] + shift, v[1] + shift] if name == "last_drink" else v + shift)
                           for name, v in vk.items() if name in ("sips", "last_drink", "empty_glass_down",
                                                                 "pick_up", "leave_view", "back_without_glass")}
    for second, en, _ in video_lines(video):
        if "The sound of" in en:
            key["video_events"]["sound_glass_in_dishwasher"] = clip_start + second - VIDEO_FIRST_LINE
    w.state["glass"] = None
    w.recent = None
    scene(rng.choice(["typing", "writing"]), ["notebook"], rng.randint(10, 20))
    return lines, key


def hms(seconds: int) -> str:
    return (START + timedelta(seconds=seconds)).strftime("%H:%M:%S")


def to_times(key: dict) -> dict:
    out = {}
    for name, value in key.items():
        if name == "video":
            out[name] = value
        elif isinstance(value, dict):
            out[name] = to_times(value)
        elif isinstance(value, list):
            out[name] = [to_times({"x": v})["x"] for v in value]
        else:
            out[name] = hms(value)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, nargs="+", required=True, help="몇 일째를 만들지 (1~4, 영상 번호와 같음)")
    parser.add_argument("--out", type=Path, default=EXP / "data")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    keys_path = args.out / "answer_key_days.json"
    keys = json.loads(keys_path.read_text(encoding="utf-8")) if keys_path.exists() else {}
    for day in args.days:
        lines, key = build_day(day, video=day)
        for path in (args.out / f"day{day}.txt", args.out / f"day{day}_ko.txt"):
            if path.exists():
                raise SystemExit(f"이미 있음: {path}")
        (args.out / f"day{day}.txt").write_text("".join(f"{hms(i)} | {en}\n" for i, (en, _) in enumerate(lines)),
                                                encoding="utf-8")
        (args.out / f"day{day}_ko.txt").write_text("".join(f"{hms(i)} | {ko}\n" for i, (_, ko) in enumerate(lines)),
                                                   encoding="utf-8")
        keys[f"day{day}"] = to_times(key)
        print(f"day{day}: {len(lines)}줄 ({len(lines) // 60}분 {len(lines) % 60}초), 영상{day}은 {hms(key['video_starts_at'])}부터")
    keys_path.write_text(json.dumps(keys, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
