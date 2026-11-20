"""Make the one-hour morning record and its answer key (아침 1시간 합성 기록 5일과 정답표 만들기).

One person living alone, on five weekday mornings from 07:00 to 08:00: waking up,
opening the curtains, washing (out of view), cereal and a cup of water at the table, a
can of coffee from the fridge on the sofa with the TV on, then packing the laptop and
leaving. Each morning is simulated in time order and the simulation keeps track of what a
line depends on (where the person is, the cup and the bowl on the table, the spoon in
hand, the coffee can, the curtains, the TV, the room light), so no line contradicts an
earlier one. `story_problems` checks a finished day again.

The record is written the way the real PAM predictor writes when it watches a video
(ai/artifacts/routine_vllm_fsm_2026-11-04/*/predictions.jsonl): every line describes the
scene (posture, what the person is doing, things lying around), the wording drifts from
line to line, what was just done is still mentioned for a few seconds, and between the
planned events the person yawns, stretches, chews, looks around, checks the phone and
changes the channel. Start times move by a few minutes from day to day. See vocabulary.py.

No model is called. A record holds only `HH:MM:SS | sentence`, one line every 2 seconds
from 07:00:00 to 07:59:58 (1,800 lines). The answer key goes to a separate file and must
never be given to a model.

Usage (writes files; run only for the experiment):
    python make_records.py --out ../data
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Callable

from vocabulary import (CURTAIN_PLACES, CURTAINS_CLOSED, CURTAINS_OPEN, ELSEWHERE, EVENTS, LEFT, POSTURE, STATES,
                        TASKS, TV_ON, WORDS)

SEED = 20261116
STEP = 2                     # seconds between record lines
FOLLOW = 300                 # "within 5 minutes"
DAY_START, DAY_END = 7 * 3600, 8 * 3600
DAYS = range(1, 6)
LATE_CURTAIN_DAY = 2         # stays in the room over five minutes after getting up; the curtains wait until after washing
NEAR_PHONE_DAYS = (1, 3, 4)  # one more phone check after the meal, within five minutes before the cup goes away
CALL_THEN_CAN_DAYS = (1, 2)  # the call comes just before the coffee is finished and the can put away
UNSEEN_LIGHT_DAYS = (3, 5)   # leaves as soon as the bag is on; the light goes off out of view
THINGS_AT = {"deskside": "desk"}                 # standing by the desk, the desk is still in view
# Small movements, and the shortest time before the same one comes again.
RARE = {"stretch": 20 * 60, "yawn": 8 * 60, "rub_eyes": 12 * 60, "look_around": 3 * 60, "shift_position": 4 * 60,
        "change_channel": 5 * 60, "check_time": 8 * 60, "adjust_cushion": 60 * 60}


def sec(text: str) -> int:
    hours, minutes, seconds = map(int, text.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def hms(value: int) -> str:
    return f"{value // 3600:02d}:{value // 60 % 60:02d}:{value % 60:02d}"


NIGHTS_2_TO_5 = (2, 3, 4, 5)
RULES = (
    {"id": "R1", "state": "wake", "task": 10,
     "candidates": [{"event": "get_out_of_bed", "expected_nights": (5,)}],
     "forbidden": ["walk_to_curtains"]},
    {"id": "R2", "state": "breakfast", "task": 1,
     "candidates": [{"event": "finish_drinking", "expected_nights": NIGHTS_2_TO_5},
                    {"event": "look_at_phone", "expected_nights": ()}],
     "forbidden": ["pick_up_dishes", "carry_dishes_to_kitchen"]},
    {"id": "R3", "state": "breakfast", "task": 6,
     "candidates": [{"event": "finish_meal", "expected_nights": NIGHTS_2_TO_5},
                    {"event": "wipe_mouth", "expected_nights": ()}],
     "forbidden": ["pick_up_dishes", "carry_dishes_to_kitchen"]},
    {"id": "R4", "state": "breakfast", "task": 2,
     "candidates": [{"event": "finish_meal", "expected_nights": NIGHTS_2_TO_5}],
     "forbidden": ["take_coffee_from_fridge", "carry_coffee_to_sofa"]},
    {"id": "R5", "state": "rest", "task": 3,
     "candidates": [{"event": "finish_coffee", "expected_nights": NIGHTS_2_TO_5},
                    {"event": "phone_rings", "expected_nights": (2,)}],
     "forbidden": ["pick_up_empty_can", "carry_can_to_bin"]},
    {"id": "R6", "state": "leaving", "task": 7,
     "candidates": [{"event": "put_on_bag", "expected_nights": NIGHTS_2_TO_5}],
     "forbidden": ["walk_to_light_switch"]},
)

CASES = (
    {"id": "occasional_miss", "ko": "가끔 빠지는 습관", "rule": "R1", "candidate": "get_out_of_bed", "true_habit": "예",
     "note": "침대에서 일어나 1분 안에 커튼을 연다. 2일째만 일어나서 6분 넘게 방에서 이불을 개고 휴대폰을 보다가 씻으러 "
             "나가고, 커튼은 씻고 와서 연다. 5일째 밤(5번 중 4번 = 80%)에야 통과한다."},
    {"id": "daily_habit", "ko": "매일 하는 습관", "rule": "R2", "candidate": "finish_drinking", "true_habit": "예",
     "note": "아침을 먹다가 물을 다 마시고, 2~4분 뒤 컵을 식기세척기에 넣는다. 5일 모두."},
    {"id": "one_signal_two_habits", "ko": "신호 하나에 습관 둘 (그릇)", "rule": "R3", "candidate": "finish_meal",
     "true_habit": "예", "note": "시리얼을 다 먹고 1.5~3분 뒤 그릇을 식기세척기에 넣는다. 5일 모두."},
    {"id": "coffee", "ko": "신호 하나에 습관 둘 (커피)", "rule": "R4", "candidate": "finish_meal", "true_habit": "예",
     "note": "그릇과 컵을 넣은 뒤 바로 냉장고에서 캔 커피를 꺼내 소파 옆 탁자에 놓는다. 다 먹고 2~3.5분 뒤다. 5일 모두."},
    {"id": "empty_can", "ko": "다 마신 캔", "rule": "R5", "candidate": "finish_coffee", "true_habit": "예",
     "note": "커피를 다 마시고 1~2분 뒤 TV를 끄고 빈 캔을 보관함에 넣는다. 5일 모두."},
    {"id": "unseen", "ko": "못 봄", "rule": "R6", "candidate": "put_on_bag", "true_habit": "예",
     "note": "가방을 메고 30초 안에 방 불을 끄고 나간다. 3·5일째는 가방을 메자마자 나가서 불은 안 보이는 곳에서 끈다"
             "(기록에 없음). 못 본 날을 빼야 계속 통과한다."},
    {"id": "repeated_candidate", "ko": "식사 중에도 하는 동작", "rule": "R3", "candidate": "wipe_mouth",
     "true_habit": "아니요", "note": "식사 중간에 1~2번, 다 먹고 1번 입을 닦는다. 그릇이 따라오는 건 마지막 1번뿐이다."},
    {"id": "frequent_event", "ko": "자주 있는 사건", "rule": "R2", "candidate": "look_at_phone", "true_habit": "아니요",
     "note": "아침 먹는 동안 휴대폰을 2~3번 본다. 1·3·4일째에만 다 먹고 한 번 더 봐서, 그게 컵 넣기 5분 안이다."},
    {"id": "early_coincidence", "ko": "처음 며칠에 겹친 우연", "rule": "R5", "candidate": "phone_rings",
     "true_habit": "아니요 (기준의 약점)",
     "note": "전화는 매일 소파에서 받는다. 1·2일째는 통화 직후 커피를 다 마셔서 캔 치우기가 우연히 5분 안에 따라온다. "
             "3~5일째는 전화가 일찍 와서 캔 치우기가 8분 넘게 뒤다. 2일째 밤에만 통과한다."},
    {"id": "part_of_action", "ko": "행동의 일부", "rule": None, "candidate": None, "true_habit": "아니요",
     "note": "모든 행동 앞에 그 행동을 하러 가는 줄이 있다. 각 규칙의 forbidden 사건이 예측 모델용 FSM에 들어가면 실패다."},
)


class _Day:
    """Builds one morning in time order and keeps track of what each line depends on."""

    def __init__(self, day: int, rng: random.Random):
        self.day, self.rng = day, rng
        self.t = DAY_START
        self.state, self.place = "wake", "bed"   # place: a key of vocabulary.POSTURE
        self.segments: list[dict] = []
        # What lies on the table, the side table by the sofa and the desk: name -> how the record words it.
        self.things: dict[str, dict[str, str]] = {"table": {"napkins": "a napkin holder"},
                                                  "sofa": {"remote": "a TV remote"},
                                                  "desk": {"laptop": "a laptop", "charger": "a laptop charger"}}
        self.cup: str | None = None              # the cup on the table: "full" or "empty"
        self.hand: str | None = None             # "spoon" while it is in hand
        self.curtains = False
        self.tv = False
        self.last: dict[str, int] = {}           # when each small movement last began

    # Basic steps --------------------------------------------------------------------
    def secs(self, low: int, high: int) -> int:
        """A random even number of seconds from low to high."""
        if low % STEP or high % STEP:
            raise ValueError(f"Bounds {low}, {high} are not on the {STEP}-second grid")
        return self.rng.randrange(low, high + 1, STEP)

    def around(self, clock: str, spread: int) -> int:
        """A time near `clock`, at most `spread` seconds earlier or later."""
        return sec(clock) + self.secs(-spread, spread)

    def add(self, event: str, seconds: int, role: str = "background", case: str | None = None,
            place: str | None = None) -> None:
        if seconds <= 0 or seconds % STEP:
            raise ValueError(f"{event}: {seconds} s is not a positive multiple of {STEP} s")
        place = place or self.place
        lying = self.things.get(THINGS_AT.get(place, place), {})
        self.segments.append({"start": self.t, "end": self.t + seconds, "event": event,
                              "state": self.state, "role": role, "case": case, "place": place,
                              "things": tuple(label for name, label in lying.items()
                                              if name not in EVENTS[event]["uses"]),
                              "curtains": self.curtains, "tv": self.tv})
        self.t += seconds

    def pick(self, options: list[tuple[float, str, int, int]]) -> tuple[str, int]:
        """One weighted (event, seconds) from (weight, event, shortest, longest)."""
        point = self.rng.random() * sum(option[0] for option in options)
        for weight, event, low, high in options:
            point -= weight
            if point < 0:
                return event, self.secs(low, high)
        _, event, low, high = options[-1]
        return event, self.secs(low, high)

    def allowed(self, event: str) -> bool:
        """Nobody stretches or yawns again and again: a small movement waits for its gap."""
        if event not in RARE:
            return True
        if self.t - self.last.get(event, -DAY_END) < RARE[event]:
            return False
        self.last[event] = self.t
        return True

    def fill_until(self, moment: int, picker: Callable[[], tuple[str, int]]) -> None:
        """Everyday background until `moment`; the last piece is cut to end exactly there."""
        while self.t < moment:
            event, seconds = picker()
            last = self.segments[-1] if self.segments else None
            if last and last["event"] == event and last["role"] != "background":
                continue                      # a planted event is never followed by the same event
            if self.allowed(event):
                self.add(event, min(seconds, moment - self.t))   # background repeats are merged later

    # Background pickers ---------------------------------------------------------------
    def in_bed(self):
        return self.pick([(45, "lie_awake", 10, 40), (40, "look_at_phone", 10, 60), (5, "yawn", 2, 4),
                          (5, "rub_eyes", 2, 6), (5, "stretch", 6, 12)])

    def on_bed_edge(self):
        return self.pick([(70, "wake_slowly", 6, 16), (10, "yawn", 2, 4), (10, "rub_eyes", 2, 6),
                          (10, "stretch", 6, 12)])

    def by_bed(self):
        return self.pick([(70, "look_at_phone", 20, 90), (10, "look_around", 2, 6), (8, "yawn", 2, 4),
                          (6, "stretch", 6, 12), (6, "rub_eyes", 2, 6)])

    def after_meal(self):
        return self.pick([(80, "sit_idle_at_table", 10, 30), (10, "look_around", 2, 6), (10, "shift_position", 2, 6)])

    def on_sofa(self):
        return self.pick([(40, "watch_tv", 30, 150), (24, "look_at_phone", 6, 40), (8, "look_at_phone", 60, 150),
                          (6, "change_channel", 2, 4), (4, "check_time", 2, 4), (3, "adjust_cushion", 4, 6),
                          (5, "shift_position", 2, 6), (4, "look_around", 2, 6), (3, "yawn", 2, 4),
                          (3, "stretch", 6, 12)])

    # Eating ---------------------------------------------------------------------------
    def spoon_down(self, chance: float) -> None:
        if self.hand and self.rng.random() < chance:
            self.add("put_down_spoon", self.secs(2, 4))
            self.hand = None

    def spoon_up(self) -> None:
        if self.hand is None:
            self.add("pick_up_spoon", self.secs(2, 4))
            self.hand = "spoon"

    def eat_until(self, moment: int) -> None:
        """Eating with the odd sip of water, chewing and small movement; ends exactly at `moment`."""
        while self.t < moment:
            left, chance = moment - self.t, self.rng.random()
            if self.cup == "full" and chance < 0.07 and left >= 14:
                self.spoon_down(0.6)
                self.add("drink_water", min(self.secs(4, 8), moment - self.t))
            elif chance < 0.18 and left >= 8:
                event, seconds = self.pick([(60, "chew", 4, 10), (25, "look_around", 2, 6),
                                            (15, "shift_position", 2, 6)])
                if self.allowed(event):
                    self.add(event, min(seconds, left))
            elif self.hand is None and left < 8:
                self.add("chew", left)
            else:
                self.spoon_up()
                self.add("eat_cereal", min(self.secs(10, 40), moment - self.t))

    # Parts of the morning -----------------------------------------------------------
    def wake(self) -> None:
        self.state, self.place = "wake", "bed"
        self.add("sleep", self.secs(10, 50))
        self.add("turn_off_alarm", self.secs(4, 6))
        self.fill_until(self.t + self.secs(80, 170), self.in_bed)
        self.add("sit_up_in_bed", self.secs(4, 6))
        self.place = "bededge"
        self.fill_until(self.t + self.secs(10, 30), self.on_bed_edge)
        self.add("get_out_of_bed", 4, "candidate", "occasional_miss")
        got_up = self.t - 4
        self.place = "room"
        if self.rng.random() < 0.5 and self.allowed("stretch"):
            self.add("stretch", self.secs(6, 12))
        self.add("turn_on_room_light", 4)
        if self.day == LATE_CURTAIN_DAY:
            self.place = "bedside"
            self.add("make_bed", self.secs(40, 80))
            self.fill_until(got_up + self.secs(370, 430), self.by_bed)    # in view for over five minutes
            self.place = "room"
            self.bathroom()
            self.get_dressed()
            self.open_curtains()
        else:
            self.open_curtains()
            self.place = "room"
            self.bathroom()
            self.get_dressed()
            self.place = "bedside"
            self.add("make_bed", self.secs(30, 70))

    def open_curtains(self) -> None:
        self.place = "window"
        self.add("walk_to_curtains", self.secs(2, 4), "approach", "occasional_miss")
        self.add("open_curtains", self.secs(4, 6), "action", "occasional_miss")
        self.curtains = True
        self.add("look_out_window", self.secs(6, 20))

    def bathroom(self) -> None:
        self.add("leave_room", self.secs(2, 4))
        self.add("unseen", self.secs(7 * 60, 10 * 60), "unseen")
        self.add("enter_room", self.secs(2, 4))

    def get_dressed(self) -> None:
        self.place = "room"
        self.add("dry_hair", self.secs(30, 80))
        self.place = "bedside"
        self.add("get_dressed", self.secs(90, 170))

    def breakfast(self) -> None:
        self.state, self.place = "breakfast", "kitchen"
        self.add("walk_to_kitchen", self.secs(4, 6))
        self.add("take_bowl", self.secs(4, 6))
        self.add("pour_cereal", self.secs(6, 12))
        self.add("take_milk", self.secs(4, 6))
        self.add("pour_milk", self.secs(4, 8))
        self.add("put_milk_back", self.secs(4, 6))
        self.add("fill_cup_at_purifier", self.secs(6, 10))
        self.add("bring_breakfast", self.secs(6, 10), place="table")
        self.things["table"].update(bowl="a bowl of cereal", cup="a cup of water")
        self.cup = "full"
        self.place = "table"
        self.add("sit_at_table", 4)
        sat = self.t - 4
        last_bite = sat + self.secs(11 * 60, 15 * 60)
        last_drink = last_bite - self.secs(20, 70)
        cup_away = last_bite + 4 + self.secs(80, 150)   # the dishes go 1.5 to 4 minutes after the last drink
        # Phone checks while eating lie more than five minutes before the cup goes away.
        checks = sorted(self.rng.sample(range(sat + 60, last_drink - 330, 60), self.rng.randint(2, 3)))
        taken = [*checks, last_drink]

        def free_time(low: int, high: int) -> int:
            """A time between low and high at least 40 seconds from every planned moment."""
            while True:
                when = self.rng.randrange(low, high, 30)
                if all(abs(when - other) >= 40 for other in taken):
                    taken.append(when)
                    return when

        wipes = [free_time(sat + 150, last_bite - 60) for _ in range(self.rng.randint(1, 2))]
        sip = free_time(sat + 60, last_drink - 60)      # at least one sip before the water is finished
        plan = sorted([(when, "phone") for when in checks] + [(when, "wipe") for when in wipes]
                      + [(sip, "sip"), (last_drink, "finish")])
        for when, kind in plan:
            self.eat_until(when)
            if kind == "phone":
                self.spoon_down(0.8)
                self.add("look_at_phone", self.secs(6, 30), "candidate", "frequent_event")
            elif kind == "sip":
                self.spoon_down(0.6)
                self.add("drink_water", self.secs(4, 8))
            elif kind == "wipe":
                self.spoon_down(0.5)
                self.add("wipe_mouth", 4, "candidate", "repeated_candidate")
            else:
                self.spoon_down(0.6)
                self.add("finish_drinking", 4, "candidate", "daily_habit")
                self.cup = "empty"
                self.things["table"]["cup"] = "an empty cup"
        self.eat_until(last_bite)
        self.spoon_up()
        self.add("finish_meal", 4, "candidate", "one_signal_two_habits")
        self.things["table"]["bowl"] = "an empty bowl"
        self.spoon_down(1.0)
        self.add("sit_idle_at_table", self.secs(10, 30))
        self.add("wipe_mouth", 4, "candidate", "repeated_candidate")
        if self.day in NEAR_PHONE_DAYS:
            self.add("sit_idle_at_table", self.secs(6, 14))
            self.add("look_at_phone", self.secs(6, 16), "candidate", "frequent_event")
        self.fill_until(cup_away, self.after_meal)
        del self.things["table"]["bowl"], self.things["table"]["cup"]
        self.add("pick_up_dishes", self.secs(4, 6), "approach")
        self.place = "kitchen"
        self.add("carry_dishes_to_kitchen", self.secs(4, 6), "approach")
        self.add("put_bowl_in_dishwasher", self.secs(4, 6), "action", "one_signal_two_habits")
        self.add("put_cup_in_dishwasher", self.secs(4, 6), "action", "daily_habit")
        self.cup = None
        self.state = "rest"
        self.add("take_coffee_from_fridge", self.secs(6, 10), "approach", "coffee")
        self.place = "sofa"
        self.add("carry_coffee_to_sofa", self.secs(4, 8), "approach", "coffee")
        self.add("put_can_next_to_self", 4, "action", "coffee")
        self.things["sofa"]["can"] = "a can of coffee"
        self.add("go_to_sofa", 4)

    def leaving_steps(self) -> list[tuple[str, int, str, str | None, str]]:
        """Packing and going out, decided before the sofa so the can is put away in time."""
        steps = [("walk_to_desk", self.secs(4, 6), "background", None, "deskside"),
                 ("pack_bag", self.secs(40, 90), "background", None, "deskside"),
                 ("zip_bag", self.secs(2, 4), "background", None, "deskside"),
                 ("leave_room", self.secs(2, 4), "background", None, "room"),       # brushing teeth
                 ("unseen", self.secs(150, 240), "unseen", None, "room"),
                 ("enter_room", self.secs(2, 4), "background", None, "room"),
                 ("put_on_jacket", self.secs(8, 16), "background", None, "room"),
                 ("check_pockets", self.secs(4, 10), "background", None, "door"),
                 ("check_mirror", self.secs(6, 12), "background", None, "door"),
                 ("put_on_bag", 4, "candidate", "unseen", "door")]
        if self.day not in UNSEEN_LIGHT_DAYS:
            if self.rng.random() < 0.5:
                steps.append(("look_at_phone", self.secs(6, 16), "background", None, "door"))
            steps += [("walk_to_light_switch", 4, "approach", "unseen", "door"),
                      ("turn_off_room_light", self.secs(4, 6), "action", "unseen", "door")]
        return steps

    def rest(self) -> None:
        self.add("pick_up_remote", self.secs(2, 4))
        self.add("turn_on_tv", 4)
        self.tv = True
        self.add("open_coffee_can", 4)
        self.things["sofa"]["can"] = "an open can of coffee"
        self.add("drink_coffee", self.secs(4, 8))      # the first sip right after opening it
        sat = self.t
        leaving = self.leaving_steps()
        leave_at = self.around("07:57:00", 50)
        stored = leave_at - sum(step[1] for step in leaving)     # the can is in the bin by then
        watch, carry, drop = self.secs(30, 100), self.secs(4, 6), self.secs(4, 6)
        finish = stored - (4 + watch + 4 + 4 + carry + drop)
        ring, talk = self.secs(2, 4), self.secs(40, 80)
        if self.day in CALL_THEN_CAN_DAYS:
            call = finish - self.secs(20, 60) - talk - ring
        else:
            call = min(sat + self.secs(90, 240), stored - drop - self.secs(470, 530))
        if call < sat + 60:
            raise ValueError(f"Day {self.day}: no room for the phone call on the sofa")
        sips, when = [], sat + self.secs(90, 200)
        while when < finish - 60:
            if not call - 20 <= when <= call + ring + talk + 20:
                sips.append(when)
            when += self.secs(90, 240)
        for when, kind in sorted([(when, "sip") for when in sips] + [(call, "call")]):
            self.fill_until(when, self.on_sofa)
            if kind == "sip":
                self.add("drink_coffee", self.secs(4, 8))
            else:
                self.add("phone_rings", ring, "candidate", "early_coincidence")
                self.add("talk_on_phone", talk)
        self.fill_until(finish, self.on_sofa)
        self.add("finish_coffee", 4, "candidate", "empty_can")
        self.things["sofa"]["can"] = "an empty can"
        self.add("watch_tv", watch)
        self.add("turn_off_tv", 4)
        self.tv = False
        del self.things["sofa"]["can"]
        self.add("pick_up_empty_can", 4, "approach", "empty_can")
        self.place = "room"
        self.add("carry_can_to_bin", carry, "approach", "empty_can")
        self.add("put_can_in_storage", drop, "action", "empty_can")
        self.state = "leaving"
        for event, seconds, role, case, place in leaving:
            self.place = place
            self.add(event, seconds, role, case)
            if event == "pack_bag":
                self.things["desk"].clear()
        self.add("leave_home", self.secs(2, 4))
        self.state = "away"
        self.add("unseen", DAY_END - self.t, "unseen", "unseen" if self.day in UNSEEN_LIGHT_DAYS else None)


def story_problems(segments: list[dict]) -> list[str]:
    """Lines that contradict an earlier line of the same morning; empty when the morning is consistent."""
    problems: list[str] = []
    in_bed, curtains, tv, packed, gone = True, False, False, None, False
    light: bool | None = False
    cup = bowl = can = hand = None
    before = None
    for segment in segments:
        event, place = segment["event"], segment.get("place")

        def problem(text: str) -> None:
            problems.append(f"{hms(segment['start'])} {event}: {text}")

        if gone and event != "unseen":
            problem("the person has already left home")
        if event in ("sleep", "turn_off_alarm", "lie_awake", "sit_up_in_bed", "wake_slowly", "get_out_of_bed"):
            if not in_bed:
                problem("is not in bed any more")
            elif event == "get_out_of_bed":
                in_bed = False
        elif event == "unseen":
            light = None                      # it may be switched while the person is out of view
        elif event in ("turn_on_room_light", "turn_off_room_light"):
            wanted = event == "turn_on_room_light"
            if light is wanted:
                problem("the room light is already " + ("on" if wanted else "off"))
            light = wanted
        elif event == "open_curtains":
            if curtains:
                problem("the curtains are already open")
            curtains = True
        elif event == "look_out_window":
            if not curtains:
                problem("the curtains are closed")
        elif event == "bring_breakfast":
            cup, bowl = "full", "on"
        elif event in ("drink_water", "finish_drinking"):
            if cup != "full" or place != "table":
                problem("no cup with water in reach")
            elif event == "finish_drinking":
                cup = "empty"
        elif event in ("eat_cereal", "finish_meal", "chew"):
            if bowl != "on" or place != "table":
                problem("not having cereal")
            elif event != "chew" and hand != "spoon":
                problem("eats without the spoon in hand")
            elif event == "finish_meal":
                bowl = "over"
        elif event == "pick_up_spoon":
            if bowl != "on" or hand is not None:
                problem("cannot pick up the spoon now")
            hand = "spoon"
        elif event == "put_down_spoon":
            if hand != "spoon":
                problem("does not hold the spoon")
            hand = None
        elif event == "pick_up_dishes":
            if cup != "empty" or bowl != "over":
                problem("the meal is not over")
            cup = bowl = "carried"
        elif event in ("carry_dishes_to_kitchen", "put_bowl_in_dishwasher", "put_cup_in_dishwasher"):
            if (bowl if event == "put_bowl_in_dishwasher" else cup) != "carried":
                problem("is not carrying it")
            if event == "put_bowl_in_dishwasher":
                bowl = None
            elif event == "put_cup_in_dishwasher":
                cup = None
        elif event in ("take_coffee_from_fridge", "carry_coffee_to_sofa", "put_can_next_to_self", "open_coffee_can",
                       "drink_coffee", "finish_coffee", "pick_up_empty_can", "carry_can_to_bin", "put_can_in_storage"):
            wanted, after = {"take_coffee_from_fridge": (None, "hand"), "carry_coffee_to_sofa": ("hand", "hand"),
                             "put_can_next_to_self": ("hand", "closed"), "open_coffee_can": ("closed", "open"),
                             "drink_coffee": ("open", "open"), "finish_coffee": ("open", "empty"),
                             "pick_up_empty_can": ("empty", "empty in hand"),
                             "carry_can_to_bin": ("empty in hand", "empty in hand"),
                             "put_can_in_storage": ("empty in hand", "stored")}[event]
            if can != wanted:
                problem(f"the can is {can}, not {wanted}")
            can = after
        elif event in ("turn_on_tv", "turn_off_tv", "watch_tv", "change_channel"):
            if event == "turn_on_tv" and tv:
                problem("the TV is already on")
            elif event != "turn_on_tv" and not tv:
                problem("the TV is off")
            tv = event != "turn_off_tv"
        elif event == "talk_on_phone":
            if before not in ("phone_rings", "talk_on_phone"):
                problem("no call was answered")
        elif event == "pack_bag":
            packed = False
        elif event == "zip_bag":
            if packed is not False:
                problem("zips a bag that was not packed")
            packed = True
        elif event == "put_on_bag":
            if packed is not True:
                problem("the bag is not ready")
        elif event == "leave_home":
            gone = True
        before = event
    return problems


# Writing the record -----------------------------------------------------------------------
def _words(place: str) -> dict[str, str]:
    return WORDS.get(place, ELSEWHERE)


def _listing(things: tuple[str, ...], rng: random.Random) -> str:
    """At most two of the things lying around, as "a cup and a can"."""
    things = list(things)
    if len(things) > 2:
        first = rng.randrange(len(things) - 1)
        things = things[first:first + 2]
    return " and ".join(things)


def _sentence(segment: dict, rng: random.Random, subject: str, clause: str, posture: str,
              just_done: str | None, just_left: bool) -> str:
    """One line of the record, worded like the real predictor's observation sentence."""
    event, place = EVENTS[segment["event"]], segment["place"]
    words = _words(place)
    things = _listing(segment.get("things", ()), rng)
    if event["kind"] == "absent":         # "has left the room" stays for the first lines the person is away
        if just_left or rng.random() < 0.4:
            return rng.choice(LEFT) + (f", leaving {things} on the {words['surface']}" if things else "") + "."
        return clause + "."
    text = clause.format(**words)
    if event["kind"] == "step":
        return f"{subject} {text}."
    if just_done:                            # what was just done is still mentioned for a few seconds
        return f"{subject} {just_done}, and is now {text}."
    extra = ""
    if rng.random() < 0.75:
        if place in CURTAIN_PLACES:
            extra = rng.choice(CURTAINS_OPEN if segment.get("curtains") else CURTAINS_CLOSED)
        elif (place == "sofa" and segment.get("tv") and segment["event"] != "watch_tv"
              and (not things or rng.random() < 0.5)):
            extra = rng.choice(TV_ON)
        elif things:
            extra = rng.choice((", with {} on the {}", ", with {} resting on the {} nearby",
                                ", with {} sitting on the {}")).format(things, words["surface"])
    return f"{subject} {posture}{rng.choice((' ', ', '))}{text}{extra}."


def render_lines(segments: list[dict], seed_text: str) -> list[str]:
    """One line every STEP seconds. The wording drifts as in the real logs: the same clause
    stays for a few lines, a step goes from "is ...ing" to "has just ...", and the first
    lines of an activity may still say what was done right before it."""
    rng = random.Random(seed_text)
    lines: list[str] = []
    before = None
    subject = "The person"
    for segment in segments:
        event, place = EVENTS[segment["event"]], segment["place"]
        phrases = event["phrases"]
        perfect = [phrase for phrase in phrases if " has " in f" {phrase[:24]}"]
        ongoing = [phrase for phrase in phrases if phrase not in perfect] or list(phrases)
        count = (segment["end"] - segment["start"]) // STEP
        done = EVENTS[before["event"]]["done"] if before else ()
        linger = rng.choice((1, 2, 2, 3, 3, 4)) if done and event["kind"] == "activity" else 0
        just_done = rng.choice(done).format(**_words(before["place"])) if linger else None
        just_left = bool(before) and EVENTS[before["event"]]["kind"] != "absent"
        clause = posture = None
        for number in range(count):
            if rng.random() < 0.3:           # "A person" and "The person" come in runs, as in the real logs
                subject = "A person" if rng.random() < 0.1 else "The person"
            if event["kind"] == "step":
                if clause is None:
                    clause = rng.choice(ongoing if count > 1 else list(phrases))
                elif clause not in perfect:
                    chance = rng.random()
                    if perfect and chance < 0.4:
                        clause = rng.choice(perfect)
                    elif chance > 0.7:
                        clause = rng.choice(ongoing)
            elif clause is None or rng.random() < 0.35:
                clause = rng.choice(phrases)
            if posture is None or rng.random() < 0.25:
                posture = rng.choice(POSTURE.get(place, POSTURE["room"]))
            text = _sentence(segment, rng, subject, clause, posture, just_done if number < linger else None,
                             just_left and number < 2)
            lines.append(f"{hms(segment['start'] + number * STEP)} | {text}")
        before = segment
    return lines


def example_sentences(name: str, place: str) -> list[str]:
    """How an event reads in the record, for the answer key (and the scoring step that matches candidates)."""
    event, words = EVENTS[name], _words(place)
    examples = []
    for phrase in event["phrases"]:
        text = phrase.format(**words)
        if event["kind"] == "absent":
            examples.append(text + ".")
        elif event["kind"] == "step":
            examples.append(f"The person {text}.")
        else:
            examples.append(f"The person {POSTURE.get(place, POSTURE['room'])[0]} {text}.")
    return examples


def _merge_repeats(segments: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for segment in segments:
        last = merged[-1] if merged else None
        if (last and last["event"] == segment["event"] and last["state"] == segment["state"]
                and last["role"] == segment["role"] == "background"):
            last["end"] = segment["end"]
        else:
            merged.append(dict(segment))
    return merged


def build_day(day: int, seed: int = SEED) -> list[dict]:
    builder = _Day(day, random.Random(f"{seed}-day{day}"))
    builder.wake()
    builder.breakfast()
    builder.rest()
    if builder.t != DAY_END:
        raise ValueError(f"Day {day} ends at {hms(builder.t)}, not {hms(DAY_END)}")
    return _merge_repeats(builder.segments)


def build_week(seed: int = SEED) -> dict[int, list[dict]]:
    return {day: build_day(day, seed) for day in DAYS}


def make_answer_key(week: dict[int, list[dict]], seed: int) -> dict:
    seen: dict[str, Counter] = {}
    for segments in week.values():
        for s in segments:
            seen.setdefault(s["event"], Counter())[s["place"]] += s["end"] - s["start"]
    return {
        "about": "합성 기록 정답표 (혼자 사는 사람의 평일 아침 1시간, 5일). 모델 입력에 넣지 않는다. "
                 "시각은 HH:MM:SS이고 끝 시각은 포함하지 않는다.",
        "seed": seed,
        "line_seconds": STEP,
        "follow_seconds": FOLLOW,
        "day_start": hms(DAY_START),
        "day_end": hms(DAY_END),
        "tasks": list(TASKS),
        "states": dict(STATES),
        "events": {name: {"ko": event["ko"], "task": event["task"],
                          "phrases": example_sentences(name, seen[name].most_common(1)[0][0] if name in seen
                                                       else "room")}
                   for name, event in EVENTS.items()},
        "rules": list(RULES),
        "cases": list(CASES),
        "days": [{"day": day, "segments": [
            {"start": hms(s["start"]), "end": hms(s["end"]), "event": s["event"],
             "state": s["state"], "role": s["role"], "case": s["case"]} for s in week[day]]}
            for day in sorted(week)],
    }


def write_outputs(out_dir: Path, week: dict[int, list[dict]], seed: int) -> None:
    """Write dayN.txt records and answer_key.json; never overwrite earlier outputs."""
    out_dir = Path(out_dir)
    records = {out_dir / f"day{day}.txt": day for day in sorted(week)}
    key_path = out_dir / "answer_key.json"
    existing = [path for path in [*records, key_path] if path.exists()]
    if existing:
        raise FileExistsError(f"Output already exists: {existing[0]}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for path, day in records.items():
        lines = render_lines(week[day], f"{seed}-render-day{day}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    key_path.write_text(json.dumps(make_answer_key(week, seed), ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="아침 1시간 합성 기록 5일과 정답표를 만든다. 모델은 부르지 않는다.")
    parser.add_argument("--out", type=Path, required=True, help="기록과 정답표를 쓸 폴더 (이미 있으면 멈춘다)")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    write_outputs(args.out, build_week(args.seed), args.seed)


if __name__ == "__main__":
    main()
