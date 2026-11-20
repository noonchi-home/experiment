"""Make the weekday synthetic record and its answer key (합성 기록 평일 5일과 정답표 만들기).

One person living alone, on five weekdays. Each day is simulated in time order and the
simulation keeps track of what a line depends on, so no line contradicts an earlier one:
where the person is, which cup in reach has water (table, desk, sofa), the can on the
side table, what lies on the table, desk and side table, the spoon or chopsticks in hand
and whether a meal is over, the room light, the bedside lamp, the laptop, and whether a
guest is in. `story_problems` checks a finished day again.

The record is written the way the real PAM predictor writes when it watches a video
(ai/artifacts/routine_vllm_fsm_2026-11-04/*/predictions.jsonl): every line describes the
scene (posture, what the person is doing, things lying around), the wording drifts from
line to line, what was just done is still mentioned for a few seconds, and the person is
seen standing up, walking out, coming back and looking around. See vocabulary.py.

Realism anchors (구현계획서 4.2): continuous home recordings label fine-grained actions
that repeat and are full of walking, sitting down and standing up (Toyota Smarthome
Untrimmed); much of a person's day has no special activity (CASAS Aruba); about five
bites a minute, so the spoon and chopsticks go down and up many times during a meal;
phone use about 76 times a day, here 35 to 55 times while at home and awake; a drink is
brought 7 to 9 times a day (estimate). Start times move by a few minutes from day to day.

Read the finished day as a person's day, not only for contradictions (2026-11-16): the
filler between planned events must be human too. Small movements (a stretch, a yawn,
looking around) come now and then, never again and again; a drink brought to the desk or
sofa is drunk right away; a can is opened at once and finished within the hour; pockets
are checked once before the bag goes on; a guest opens a can before drinking and
finishing it; one-time steps (getting out of bed, the microwave, zipping the bag) happen
once and in order.

No model is called. A record holds only `HH:MM:SS | sentence`, one line every 2 seconds
from 07:00:00 to 23:00:00. The answer key goes to a separate file and must never be given
to a model.

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

from vocabulary import ELSEWHERE, EVENTS, LAMP_ON, LEFT, POSTURE, STATES, TASKS, WORDS

SEED = 20261115
STEP = 2                     # seconds between record lines
FOLLOW = 300                 # "within 5 minutes"
DAY_START, DAY_END = 7 * 3600, 23 * 3600
DAYS = range(1, 6)
PLACE = {"breakfast": "table", "dinner": "table", "study": "desk", "evening_rest": "sofa"}
NEAR_PHONE_DAYS = (1, 3, 4)  # breakfast days with one phone check right before the cup goes away
THINGS_AT = {"deskside": "desk"}                 # standing by the desk, the desk is still in view
# Small movements, and the shortest time before the same one comes again.
RARE = {"stretch": 30 * 60, "yawn": 20 * 60, "rub_face": 20 * 60, "look_around": 6 * 60,
        "lean_back": 8 * 60, "shift_position": 8 * 60}


def sec(text: str) -> int:
    hours, minutes, seconds = map(int, text.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def hms(value: int) -> str:
    return f"{value // 3600:02d}:{value // 60 % 60:02d}:{value % 60:02d}"


NIGHTS_2_TO_5 = (2, 3, 4, 5)
RULES = (
    {"id": "R1", "state": "breakfast", "task": 1,
     "candidates": [{"event": "finish_drinking", "expected_nights": NIGHTS_2_TO_5},
                    {"event": "look_at_phone", "expected_nights": ()}],
     "forbidden": ["pick_up_empty_cup", "carry_cup_to_kitchen"]},
    {"id": "R2", "state": "bedtime", "task": 8,
     "candidates": [{"event": "close_book", "expected_nights": (5,)}],
     "forbidden": ["reach_for_lamp"]},
    {"id": "R3", "state": "dinner", "task": 6,
     "candidates": [{"event": "finish_meal", "expected_nights": NIGHTS_2_TO_5},
                    {"event": "wipe_mouth", "expected_nights": NIGHTS_2_TO_5},
                    {"event": "put_down_spoon", "expected_nights": ()}],
     "forbidden": ["pick_up_bowl"]},
    {"id": "R4", "state": "evening_rest", "task": 2,
     "candidates": [{"event": "phone_rings", "expected_nights": (2,)}],
     "forbidden": ["get_can", "carry_can_back"]},
    {"id": "R5", "state": "study", "task": 5,
     "candidates": [{"event": "close_laptop", "expected_nights": ()}],
     "forbidden": ["pick_up_book"]},
    {"id": "R6", "state": "evening_rest", "task": 3,
     "candidates": [{"event": "guest_finishes_can", "expected_nights": (4, 5)}],
     "forbidden": ["pick_up_empty_can"]},
    {"id": "R7", "state": "evening_rest", "task": 4,
     "candidates": [{"event": "finish_vacuuming", "expected_nights": ()}],
     "forbidden": ["get_book_from_shelf"]},
    {"id": "R8", "state": "study", "task": 0,
     "candidates": [{"event": "sit_at_desk", "expected_nights": (5,)}],
     "forbidden": ["get_cup", "fill_cup_at_purifier", "carry_cup_back"]},
    {"id": "R9", "state": "going_out", "task": 7,
     "candidates": [{"event": "put_on_bag", "expected_nights": NIGHTS_2_TO_5}],
     "forbidden": ["walk_to_light_switch"]},
)

CASES = (
    {"id": "daily_habit", "ko": "매일 하는 습관", "rule": "R1", "candidate": "finish_drinking",
     "true_habit": "예", "note": "아침 식사 끝 무렵 물을 다 마시고, 1.5~4분 뒤 컵을 식기세척기에 넣는다. 5일 모두."},
    {"id": "same_event_other_state", "ko": "같은 사건, 다른 상태", "rule": "R1", "candidate": "finish_drinking",
     "true_habit": "예 ([아침 식사]에서만)",
     "note": "[공부]에서도 매일 물을 다 마시지만 컵은 그대로 두고, 10분 넘게 지나서 다시 채운다. 상태별로 세야 "
             "[아침 식사] 규칙만 채택된다."},
    {"id": "occasional_miss", "ko": "가끔 빠지는 습관", "rule": "R2", "candidate": "close_book",
     "true_habit": "예", "note": "2일째만 책을 덮고 휴대폰을 25~30분 보다가 스탠드를 끈다. 그래서 5일째 밤(5번 중 4번)에야 통과한다."},
    {"id": "two_candidates", "ko": "후보 둘이 같이 통과", "rule": "R3", "candidate": "finish_meal",
     "true_habit": "예 (둘 다 맞음)",
     "note": "밥을 다 먹고 20~60초 뒤 냅킨으로 입을 닦고, 1~3분 뒤 그릇을 식기세척기에 넣는다. 두 후보 모두 통과해 'or'로 묶인다."},
    {"id": "frequent_event", "ko": "자주 있는 사건", "rule": "R1", "candidate": "look_at_phone",
     "true_habit": "아니요",
     "note": "휴대폰은 하루 35~55번 본다. [아침 식사]에서는 2~4번 보고, 1·3·4일째에만 그중 1번이 컵 넣기 5분 안이다."},
    {"id": "early_coincidence", "ko": "처음 며칠에 겹친 우연", "rule": "R4", "candidate": "phone_rings",
     "true_habit": "아니요 (기준의 약점)",
     "note": "전화는 매일 17:40 무렵 온다. 1·2일째에만 우연히 통화 뒤 캔을 소파 옆에 가져온다(전화 받고 2~4분 뒤)."},
    {"id": "half", "ko": "반쯤 하는 일", "rule": "R5", "candidate": "close_laptop",
     "true_habit": "아니요", "note": "1·3·5일째만 노트북을 닫고 1.5~3분 뒤 책을 보관 장소에 넣는다. 5일째 밤 5번 중 3번(60%)."},
    {"id": "one_day_burst", "ko": "하루에 몰림", "rule": "R6", "candidate": "guest_finishes_can",
     "true_habit": "아니요 (기준의 약점)",
     "note": "4일째에만 손님이 와서 캔을 3번 다 마시고, 매번 1.5~2.5분 뒤 빈 캔을 보관 장소에 넣는다."},
    {"id": "first_seen", "ko": "처음 본 행동", "rule": "R7", "candidate": "finish_vacuuming",
     "true_habit": "모름", "note": "5일째에만 청소기를 다 돌리고, 1.5~3분 뒤 책장에서 책을 꺼내 옆에 둔다."},
    {"id": "frequent_action", "ko": "원래 자주 하는 행동", "rule": "R8", "candidate": "sit_at_desk",
     "true_habit": "예",
     "note": "마실 것을 자기 옆에 가져오는 일을 하루 7~9번 한다(다른 때 비율 약 4~8%). 책상에 앉은 뒤에는 3일째만 "
             "빼고 2~4분 뒤 가져온다. 2일째 밤(2번 중 2번)은 p-value에서 떨어지고, 5일째 밤(5번 중 4번)에 통과한다."},
    {"id": "unseen", "ko": "못 봄", "rule": "R9", "candidate": "put_on_bag", "true_habit": "예",
     "note": "3·5일째엔 가방을 멘 뒤 바로 나가서 불은 안 보이는 곳에서 끈다(기록에 없음). 못 본 회차를 빼야 계속 통과한다."},
    {"id": "repeated_candidate", "ko": "행동 없이 반복된 후보", "rule": "R3", "candidate": "put_down_spoon",
     "true_habit": "아니요",
     "note": "저녁을 먹는 동안 숟가락을 여러 번(하루 8번 넘게) 내려놓았다가 다시 든다. 그릇 넣기 바로 앞의 마지막 한 번만 "
             "인정되므로 떨어진다."},
    {"id": "part_of_action", "ko": "행동의 일부", "rule": None, "candidate": None, "true_habit": "아니요",
     "note": "모든 행동 앞에 그 행동을 하러 가는 줄이 있다. 각 규칙의 forbidden 사건이 예측 모델용 FSM에 들어가면 실패다."},
)


class _Day:
    """Builds one day in time order and keeps track of what each line depends on."""

    def __init__(self, day: int, rng: random.Random):
        self.day, self.rng = day, rng
        self.t = DAY_START
        self.state = "morning"
        self.place = "bed"                   # where the person is (a key of vocabulary.POSTURE, or "kitchen")
        self.segments: list[dict] = []
        self.cups: dict[str, str | None] = {place: None for place in ("table", "desk", "sofa")}
        # What lies on the table, the desk and the side table by the sofa: name -> how the record words it.
        self.things: dict[str, dict[str, str]] = {"table": {}, "desk": {"laptop": "a closed laptop", "book": "a book"},
                                                  "sofa": {}}
        self.hand: str | None = None
        self.guest = False
        self.guest_can = False               # the guest has an open can
        self.lamp = False                    # the bedside lamp is on
        self.last: dict[str, int] = {}       # when each small movement last began

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
                              "lamp": self.lamp})
        self.t += seconds

    def pick(self, options: list[tuple[float, str, int, int]]) -> tuple[str, int]:
        """One weighted (event, seconds) from (weight, event, shortest, longest)."""
        options = [option for option in options if option[0] > 0]
        point = self.rng.random() * sum(option[0] for option in options)
        for weight, event, low, high in options:
            point -= weight
            if point < 0:
                return event, self.secs(low, high)
        _, event, low, high = options[-1]
        return event, self.secs(low, high)

    def fill_until(self, moment: int, picker: Callable[[], tuple[str, int]]) -> None:
        """Everyday background until `moment`; the last piece is cut to end exactly there."""
        while self.t < moment:
            event, seconds = picker()
            last = self.segments[-1] if self.segments else None
            if last and last["event"] == event and last["role"] != "background":
                continue                      # a planted event is never followed by the same event
            if event in RARE:
                if self.t - self.last.get(event, -DAY_END) < RARE[event]:
                    continue                  # nobody stretches or yawns again and again
                self.last[event] = self.t
            self.add(event, min(seconds, moment - self.t))   # background repeats are merged later

    # Moving about ---------------------------------------------------------------------
    def to_sofa(self) -> None:
        self.add("go_to_sofa", self.secs(4, 6), place="sofa")
        self.place = "sofa"

    def out_of_view(self, seconds: int) -> None:
        """Walks out of the room (bathroom, shower) and comes back in."""
        self.add("leave_room", self.secs(2, 4))
        self.add("unseen", seconds, "unseen")
        self.add("enter_room", self.secs(2, 4))

    def fetch_drink(self, how: str, case: str | None = None) -> None:
        """how: "meal" (already in the kitchen, the cup goes on the table), "shelf" (a new cup,
        from the desk or sofa and back) or "refill" (the same trip to the water purifier)."""
        seat = "table" if how == "meal" else self.place
        if how != "meal":
            self.things[seat].pop("cup", None)                 # a refill takes the cup along
            self.add("stand_up", 2, "approach", case)
            self.add("walk_to_kitchen", self.secs(4, 6), "approach", case, place="kitchen")
        self.add("fill_cup_at_purifier" if how == "refill" else "get_cup", self.secs(6, 10), "approach", case,
                 place="kitchen")
        if how != "meal":
            self.add("carry_cup_back", self.secs(4, 6), "approach", case, place=seat)
        self.add("put_cup_next_to_self", 4, "action", case, place=seat)
        self.cups[PLACE[self.state]] = "full"
        self.things[seat]["cup"] = "a cup"
        if how != "meal":                     # a drink brought to the desk or sofa is drunk right away
            self.add("drink_water", self.secs(4, 8))

    def put_down(self) -> None:
        if self.hand == "spoon":
            self.add("put_down_spoon", self.secs(2, 4), "candidate", "repeated_candidate")
        else:
            self.add("put_down_chopsticks", self.secs(2, 4))
        self.hand = None

    def take(self, utensil: str) -> None:
        self.add("pick_up_spoon" if utensil == "spoon" else "pick_up_chopsticks", self.secs(2, 4))
        self.hand = utensil

    # Background pickers ---------------------------------------------------------------
    def _sip(self, weight: float) -> tuple[float, str, int, int]:
        return (weight if self.cups.get(PLACE.get(self.state)) == "full" else 0, "drink_water", 4, 8)

    def morning_idle(self):
        return self.pick([(35, "look_at_phone", 6, 40), (35, "look_at_phone", 60, 240),
                          (22, "sit_on_sofa", 20, 90), (3, "stretch", 6, 14), (3, "yawn", 2, 4),
                          (2, "look_around", 2, 6)])

    def eating_breakfast(self):
        return self.pick([(80, "eat_breakfast", 10, 40), self._sip(15)])

    def idle_at_table(self):
        return self.pick([(85, "sit_idle_at_table", 10, 40), (10, "stretch", 6, 14), (5, "look_around", 2, 6)])

    def at_desk(self):
        return self.pick([(33, "type_on_laptop", 120, 600), (14, "read_book_at_desk", 90, 420),
                          (9, "write_notes", 40, 200), (16, "look_at_phone", 6, 40), (4, "look_at_phone", 120, 300),
                          self._sip(10), (2, "stretch", 6, 14), (3, "look_around", 2, 6), (2, "rub_face", 2, 6),
                          (3, "lean_back", 4, 10), (1, "yawn", 2, 4)])

    def after_laptop(self):
        return self.pick([(55, "write_notes", 30, 120), (36, "look_at_phone", 6, 40), (5, "stretch", 6, 14),
                          (4, "look_around", 2, 6)])

    def on_sofa(self):
        if self.guest:
            return self.pick([(45, "chat_with_guest", 60, 300), (18, "watch_tv", 60, 300),
                              (15 if self.guest_can else 0, "guest_drinks_can", 4, 10),
                              (12, "look_at_phone", 6, 30), self._sip(6)])
        return self.pick([(38, "watch_tv", 180, 900), (24, "look_at_phone", 6, 40), (10, "look_at_phone", 120, 480),
                          (10, "sit_on_sofa", 30, 120), self._sip(8), (4, "shift_position", 2, 6),
                          (2, "look_around", 2, 6), (2, "yawn", 2, 4)])

    def after_meal(self):
        return self.pick([(50, "sit_idle_at_table", 10, 30), self._sip(25), (25, "look_at_phone", 6, 20)])

    def chatting(self):
        return self.pick([(60, "chat_with_guest", 20, 120), (40, "look_at_phone", 6, 20)])

    def open_guest_can(self, chat_seconds: int) -> None:
        """The guest opens a can after a little talk; it is finished before the next one is opened."""
        self.add("chat_with_guest", chat_seconds)
        self.add("guest_opens_can", 4)
        self.add("guest_drinks_can", self.secs(4, 8))      # the first drink right after opening it
        self.guest_can = True

    # Parts of the day -------------------------------------------------------------------
    def morning(self) -> None:
        self.state, self.place = "morning", "bed"
        self.add("wake_up", self.secs(40, 120))
        self.add("sit_up_in_bed", self.secs(4, 8))
        self.add("get_out_of_bed", 4)
        self.place = "room"
        self.add("turn_on_room_light", 4)
        self.out_of_view(self.secs(10 * 60, 14 * 60))                  # bathroom
        washed = self.t
        self.place = "bedside"
        self.add("get_dressed", self.secs(3 * 60, 5 * 60))
        self.add("make_bed", self.secs(40, 90))
        self.to_sofa()
        # The cup comes more than five minutes after the bathroom, as in every drink below.
        self.fill_until(max(self.around("07:26:00", 240), washed + 330), self.morning_idle)

    def breakfast(self) -> None:
        self.state = "breakfast"
        self.add("stand_up", 2)
        self.place = "kitchen"
        self.add("walk_to_kitchen", self.secs(2, 4))
        self.fetch_drink("meal")
        self.add("bring_toast", self.secs(6, 12))
        self.things["table"]["plate"] = "a plate of toast"
        self.place = "table"
        self.add("sit_at_table", 4)
        sat = self.t - 4
        last_bite = sat + self.secs(12 * 60, 18 * 60)
        last_drink = last_bite - self.secs(30, 90)
        cup_away = last_bite + 4 + self.secs(40, 150)    # the dishwasher 1.5 to 4 minutes after the last drink
        # Phone checks while eating lie more than five minutes before the cup goes away.
        checks = sorted(self.rng.sample(range(sat + 60, last_drink - 330, 60), self.rng.randint(2, 3)))
        for check in checks:
            self.fill_until(check, self.eating_breakfast)
            self.add("look_at_phone", self.secs(6, 30), "candidate", "frequent_event")
        self.fill_until(last_drink, self.eating_breakfast)
        self.add("finish_drinking", 4, "candidate", "daily_habit")
        self.cups["table"] = "empty"
        self.fill_until(last_bite, self.eating_breakfast)
        self.add("finish_breakfast", 4)
        self.things["table"]["plate"] = "an empty plate"
        if self.day in NEAR_PHONE_DAYS:
            self.add("sit_idle_at_table", self.secs(6, 14))
            self.add("look_at_phone", self.secs(6, 16), "candidate", "frequent_event")
        self.fill_until(cup_away, self.idle_at_table)
        self.things["table"].pop("cup")
        self.add("pick_up_empty_cup", 4, "approach", "daily_habit")
        self.place = "kitchen"
        self.add("carry_cup_to_kitchen", 4, "approach", "daily_habit")
        self.add("put_cup_in_dishwasher", 6, "action", "daily_habit")
        self.cups["table"] = None
        self.things["table"].pop("plate")
        self.add("put_plate_in_sink", self.secs(6, 12))
        self.place = "room"
        self.out_of_view(self.secs(4 * 60, 8 * 60))                    # brushing teeth

    def study(self) -> None:
        self.state = "morning"                # getting ready between breakfast and the desk
        self.to_sofa()
        self.fill_until(self.around("08:08:00", 300), self.morning_idle)
        self.state = "study"
        self.add("stand_up", 2)
        self.place = "desk"
        self.add("sit_at_desk", 4, "candidate", "frequent_action")
        sat = self.t - 4
        self.add("open_laptop", self.secs(4, 8))
        self.things["desk"]["laptop"] = "an open laptop"
        close = self.around("11:58:00", 360)
        fetch = sat + (self.secs(25 * 60, 40 * 60) if self.day == 3 else self.secs(110, 230))
        finish = sat + self.secs(95 * 60, 140 * 60)
        refill = finish + 4 + self.secs(10 * 60, 22 * 60)
        plan = [(fetch, "fetch"), (finish, "finish"), (refill, "refill")]
        if self.rng.random() < 0.5 and refill + 30 * 60 < close - 15 * 60:
            plan.append((refill + self.secs(30 * 60, 45 * 60), "coffee"))
        drinks = [when for when, kind in plan if kind != "finish"]
        breaks = []
        while len(breaks) < self.rng.randint(1, 2):
            when = self.rng.randrange(sat + 15 * 60, close - 15 * 60, STEP)
            if all(abs(when - other) > 12 * 60 for other in [*drinks, finish, *breaks]):
                breaks.append(when)
        plan += [(when, "bathroom") for when in breaks]
        for when, kind in sorted(plan):
            self.fill_until(when, self.at_desk)
            if kind in ("fetch", "refill", "coffee"):
                self.fetch_drink("shelf" if kind == "fetch" else "refill",
                                 "frequent_action" if kind == "fetch" else None)
            elif kind == "finish":
                self.add("finish_drinking", 4, "candidate", "same_event_other_state")
                self.cups["desk"] = "empty"
            else:
                self.add("stand_up", 2)
                self.out_of_view(self.secs(3 * 60, 6 * 60))
                self.add("return_to_desk", self.secs(2, 4))
        self.fill_until(close, self.at_desk)
        self.add("close_laptop", 4, "candidate", "half")
        self.things["desk"]["laptop"] = "a closed laptop"
        closed = self.t - 4
        if self.day % 2 == 1:
            self.fill_until(self.t + self.secs(80, 170), self.after_laptop)
            self.things["desk"].pop("book")
            self.add("pick_up_book", 4, "approach", "half")
            self.add("put_book_in_storage", 6, "action", "half", place="room")
            self.add("return_to_desk", self.secs(2, 4))
        # Going out starts more than five minutes after the laptop is closed.
        pack, zipper, jacket, pockets = self.secs(60, 120), self.secs(2, 4), self.secs(8, 16), self.secs(6, 12)
        ready = 2 + pack + zipper + jacket + pockets
        bag = max(closed + self.secs(7 * 60, 10 * 60), self.t + 60 + ready)
        self.fill_until(bag - ready, self.after_laptop)
        self.state = "going_out"
        self.add("stand_up", 2)
        self.place = "deskside"
        self.add("pack_bag", pack)
        self.things["desk"].pop("laptop")
        self.add("zip_bag", zipper)
        self.place = "room"
        self.add("put_on_jacket", jacket)
        self.add("check_pockets", pockets)
        self.add("put_on_bag", 4, "candidate", "unseen")
        home = self.around("16:54:00", 120) if self.day == 4 else self.around("17:00:00", 720)
        if self.day in (3, 5):
            self.state = "away"
            self.add("unseen", home - self.t, "unseen", "unseen")
        else:
            self.add("look_at_phone", self.secs(10, 40))               # a last look at the phone, bag on
            self.add("walk_to_light_switch", 4, "approach", "unseen")
            self.add("turn_off_room_light", 6, "action", "unseen")
            self.add("leave_home", self.secs(2, 4), place="door")
            self.state = "away"
            self.add("unseen", home - self.t, "unseen")

    def evening(self) -> None:
        self.state, self.place = "evening_rest", "door"
        self.add("come_home", self.secs(6, 10))
        self.add("take_off_bag", self.secs(4, 8))
        self.place = "room"
        self.add("turn_on_room_light", 4)
        self.out_of_view(self.secs(120, 240))                          # washing hands
        washed = self.t
        self.to_sofa()
        self.add("sit_on_sofa", self.secs(20, 60))
        plan = [(washed + self.secs(330, 480), "water")]
        if self.day == 4:
            arrive = self.around("17:14:00", 120)
            cans = [self.around("17:29:00", 120), self.around("17:58:00", 120), self.around("18:16:00", 120)]
            plan += [(arrive, "guest_arrives"), (self.around("17:42:00", 180), "call"),
                     *[(when, "guest_can") for when in cans],
                     (cans[-1] + self.secs(6 * 60, 10 * 60), "guest_leaves")]
            dinner = plan[-1][0] + self.secs(4 * 60, 8 * 60)
        else:
            plan.append((self.around("17:42:00", 480), "call"))
            dinner = self.around("18:34:00", 480)
        can_sips: list[int] = []
        for when, kind in sorted(plan):
            self.fill_until(when, self.on_sofa)
            if kind == "water":
                self.fetch_drink("refill")
            elif kind == "guest_arrives":
                self.add("stand_up", 2)
                self.add("guest_arrives", self.secs(10, 20), place="door")
                self.guest = True
                self.to_sofa()
                self.open_guest_can(self.secs(40, 120))
            elif kind == "guest_leaves":
                self.add("stand_up", 2)
                self.add("guest_leaves", self.secs(10, 20), place="door")
                self.guest = False
                self.to_sofa()
            elif kind == "guest_can":
                self.add("guest_finishes_can", 4, "candidate", "one_day_burst")
                self.guest_can = False
                self.fill_until(self.t + self.secs(80, 140), self.chatting)
                self.add("pick_up_empty_can", 4, "approach", "one_day_burst")
                self.add("put_can_in_storage", 6, "action", "one_day_burst", place="room")
                self.to_sofa()
                if when < cans[-1]:
                    self.open_guest_can(self.secs(30, 90))
            else:
                self.add("phone_rings", self.secs(2, 4), "candidate", "early_coincidence")
                self.add("talk_on_phone", self.secs(40, 90))
                if self.day in (1, 2):
                    self.fill_until(self.t + self.secs(50, 120), self.on_sofa)
                    self.add("stand_up", 2, "approach", "early_coincidence")
                    self.add("walk_to_kitchen", self.secs(4, 6), "approach", "early_coincidence", place="kitchen")
                    self.add("get_can", 4, "approach", "early_coincidence", place="kitchen")
                    self.add("carry_can_back", self.secs(4, 6), "approach", "early_coincidence")
                    self.add("put_can_next_to_self", 4, "action", "early_coincidence")
                    self.things["sofa"]["can"] = "a can"
                    # A can is opened and drunk right away, then a sip every few minutes until it is empty.
                    self.add("drink_from_can", self.secs(4, 8))
                    sip = self.t
                    for _ in range(self.rng.randint(4, 6)):
                        sip += self.secs(2 * 60, 6 * 60)
                        can_sips.append(sip)
        for when in can_sips:
            if when < dinner - 60:
                self.fill_until(when, self.on_sofa)
                self.add("drink_from_can", self.secs(4, 8))
        self.fill_until(dinner, self.on_sofa)

    def dinner(self) -> None:
        self.state = "dinner"
        self.add("stand_up", 2)
        self.place = "kitchen"
        self.add("walk_to_kitchen", self.secs(4, 6))
        self.add("take_food_from_fridge", self.secs(4, 6))
        # Cooking: a pot on the stove, with one bowl heated in the microwave along the way.
        self.place = "stove"
        cooking, first, heating = self.secs(5 * 60, 10 * 60), self.secs(60, 150), self.secs(60, 120)
        self.add("cook_dinner", first)
        self.add("put_food_in_microwave", 4, place="kitchen")
        self.add("cook_dinner", heating)
        self.add("take_food_from_microwave", 4, place="kitchen")
        self.add("cook_dinner", cooking - first - heating - 8)
        self.place = "kitchen"
        self.add("bring_dinner", self.secs(8, 14))
        self.things["table"]["dinner"] = "a bowl of rice and side dishes"
        self.fetch_drink("meal")
        self.place = "table"
        self.add("sit_at_table", 4)
        last_bite = self.t - 4 + self.secs(18 * 60, 28 * 60)
        while self.t < last_bite:
            chance = self.rng.random()
            if chance < 0.10 and self.cups["table"] == "full":
                if self.hand and self.rng.random() < 0.6:
                    self.put_down()
                self.add("drink_water", self.secs(4, 8))
            elif chance < 0.16:
                if self.hand:
                    self.put_down()
                self.add("look_at_phone", self.secs(6, 30))
            else:
                utensil = "spoon" if self.rng.random() < 0.55 else "chopsticks"
                if self.hand != utensil:
                    if self.hand:
                        self.put_down()
                    self.take(utensil)
                self.add("eat_dinner", self.secs(8, 30))
        if self.hand is None:
            self.take(self.rng.choice(["spoon", "chopsticks"]))
        self.add("finish_meal", 4, "candidate", "two_candidates")
        self.things["table"]["dinner"] = "an empty bowl"
        self.put_down()
        self.add("sit_idle_at_table", self.secs(14, 50))
        self.add("wipe_mouth", 4, "candidate", "two_candidates")
        self.fill_until(self.t + self.secs(50, 160), self.after_meal)
        self.things["table"].pop("dinner")
        self.add("pick_up_bowl", 4, "approach", "two_candidates")
        self.add("put_bowl_in_dishwasher", 6, "action", "two_candidates", place="kitchen")
        self.add("wipe_table", self.secs(8, 14))

    def night(self) -> None:
        self.state = "evening_rest"
        self.to_sofa()
        self.add("sit_on_sofa", self.secs(10, 30))
        plan = [(self.around("20:30:00", 600), "tea"), (self.around("21:05:00", 480), "shower")]
        if self.day == 5:
            plan.append((self.around("19:50:00", 480), "vacuum"))
        for when, kind in sorted(plan):
            self.fill_until(when, self.on_sofa)
            if kind == "tea":
                self.fetch_drink("refill")
            elif kind == "vacuum":
                self.add("stand_up", 2)
                self.add("vacuum_floor", self.secs(8 * 60, 12 * 60), place="room")
                self.add("finish_vacuuming", 4, "candidate", "first_seen", place="room")
                self.to_sofa()
                self.fill_until(self.t + self.secs(70, 160), self.on_sofa)
                self.add("get_book_from_shelf", 4, "approach", "first_seen", place="room")
                self.add("put_book_next_to_self", 4, "action", "first_seen")
                self.things["sofa"]["book"] = "a book"
            else:
                self.add("stand_up", 2)
                self.out_of_view(self.secs(15 * 60, 25 * 60))
                self.to_sofa()
                showered = self.t
        late_water = showered + self.secs(6 * 60, 8 * 60)
        self.fill_until(late_water, self.on_sofa)
        self.fetch_drink("refill")
        self.fill_until(max(self.around("21:58:00", 240), late_water + 6 * 60), self.on_sofa)

        self.state = "bedtime"
        self.add("stand_up", 2)
        self.out_of_view(self.secs(3 * 60, 5 * 60))                    # brushing teeth
        self.place = "bedside"
        self.add("turn_on_bedside_lamp", 4)
        self.lamp = True
        self.place = "room"
        self.add("walk_to_light_switch", 4, "approach")
        self.add("turn_off_room_light", 6, "action")
        self.place = "bed"
        self.add("get_into_bed", self.secs(6, 12))
        phone = self.secs(25 * 60, 30 * 60)
        reading = self.secs(15 * 60, 25 * 60)
        if self.day == 2:                    # the lamp must still go off before 23:00
            reading = min(reading, (DAY_END - 2 * 60 - phone - 12 - self.t) // STEP * STEP)
        self.add("read_in_bed", reading)
        self.add("close_book", 4, "candidate", "occasional_miss")
        if self.day == 2:
            self.add("look_at_phone", phone, "background", "occasional_miss")
        else:
            self.add("lie_back", self.secs(14, 90))
        self.add("reach_for_lamp", 4, "approach", "occasional_miss")
        self.add("turn_off_bedside_lamp", 6, "action", "occasional_miss")
        self.lamp = False
        self.add("lie_in_dark_bed", DAY_END - self.t)


def story_problems(segments: list[dict]) -> list[str]:
    """Lines that contradict an earlier line of the same day; empty when the day is consistent."""
    problems: list[str] = []
    cups: dict[str, str | None] = {place: None for place in ("table", "desk", "sofa")}
    meal: dict[str, str] = {}
    hand = None
    can = guest = guest_can = laptop = lamp = packing = False
    light: bool | None = False
    in_bed, microwave = True, False
    for segment in segments:
        event, place = segment["event"], PLACE.get(segment["state"])

        def problem(text: str) -> None:
            problems.append(f"{hms(segment['start'])} {event}: {text}")

        if event == "unseen":
            light = None                      # it may be switched while the person is out of view
        elif event == "put_cup_next_to_self":
            if place is None:
                problem("no table, desk or sofa to put a cup at")
            else:
                cups[place] = "full"
        elif event == "drink_water":
            if cups.get(place) != "full":
                problem("no cup with water in reach")
        elif event == "finish_drinking":
            if cups.get(place) != "full":
                problem("no cup with water to finish")
            else:
                cups[place] = "empty"
        elif event in ("pick_up_empty_cup", "carry_cup_to_kitchen"):
            if cups.get(place) != "empty":
                problem("there is no empty cup")
        elif event == "put_cup_in_dishwasher":
            if cups.get(place) is None:
                problem("there is no cup to put away")
            else:
                cups[place] = None
        elif event == "sit_at_table":
            meal[segment["state"]] = "on"
        elif event in ("eat_breakfast", "finish_breakfast"):
            if meal.get("breakfast") != "on":
                problem("not having breakfast")
            elif event == "finish_breakfast":
                meal["breakfast"] = "over"
        elif event in ("eat_dinner", "finish_meal"):
            if meal.get("dinner") != "on":
                problem("not having dinner")
            elif hand is None:
                problem("eats without a spoon or chopsticks in hand")
            elif event == "finish_meal":
                meal["dinner"] = "over"
        elif event in ("pick_up_spoon", "pick_up_chopsticks"):
            if meal.get("dinner") != "on":
                problem("picks up a utensil outside the meal")
            elif hand is not None:
                problem("already holds a utensil")
            else:
                hand = "spoon" if event == "pick_up_spoon" else "chopsticks"
        elif event in ("put_down_spoon", "put_down_chopsticks"):
            wanted = "spoon" if event == "put_down_spoon" else "chopsticks"
            if hand != wanted:
                problem(f"does not hold the {wanted}")
            else:
                hand = None
        elif event == "put_can_next_to_self":
            can = True
        elif event == "drink_from_can":
            if not can:
                problem("no can in reach")
        elif event == "guest_arrives":
            guest = True
        elif event in ("chat_with_guest", "guest_opens_can", "guest_drinks_can", "guest_finishes_can",
                       "guest_leaves"):
            if not guest:
                problem("no guest is here")
            elif event == "guest_leaves":
                guest = guest_can = False
            elif event == "guest_opens_can":
                if guest_can:
                    problem("the guest already has an open can")
                guest_can = True
            elif event in ("guest_drinks_can", "guest_finishes_can"):
                if not guest_can:
                    problem("the guest has no open can")
                elif event == "guest_finishes_can":
                    guest_can = False
        elif event == "open_laptop":
            laptop = True
        elif event in ("type_on_laptop", "close_laptop"):
            if not laptop:
                problem("the laptop is closed")
            elif event == "close_laptop":
                laptop = False
        elif event in ("turn_on_room_light", "turn_off_room_light"):
            wanted = event == "turn_on_room_light"
            if light is wanted:
                problem("the room light is already " + ("on" if wanted else "off"))
            light = wanted
        elif event == "turn_on_bedside_lamp":
            if lamp:
                problem("the lamp is already on")
            lamp = True
        elif event in ("read_in_bed", "close_book", "turn_off_bedside_lamp"):
            if not lamp:
                problem("the bedside lamp is off")
            elif event == "turn_off_bedside_lamp":
                lamp = False
        # Steps that happen once and in order.
        elif event in ("wake_up", "sit_up_in_bed", "get_out_of_bed"):
            if not in_bed:
                problem("is not in bed any more")
            elif event == "get_out_of_bed":
                in_bed = False
        elif event == "get_into_bed":
            in_bed = True
        elif event == "put_food_in_microwave":
            if microwave:
                problem("the microwave is already running")
            microwave = True
        elif event == "take_food_from_microwave":
            if not microwave:
                problem("nothing was put in the microwave")
            microwave = False
        elif event == "pack_bag":
            packing = True
        elif event == "zip_bag":
            if not packing:
                problem("zips a bag that was not packed")
            packing = False
    return problems


# Writing the record -----------------------------------------------------------------------
def _place(segment: dict) -> str:
    return segment.get("place") or PLACE.get(segment["state"], "room")


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
    event, place = EVENTS[segment["event"]], _place(segment)
    words = _words(place)
    things = _listing(segment.get("things", ()), rng)
    if event["kind"] == "absent":         # "has left the room, leaving ..." stays for as long as the person is away
        if just_left or rng.random() < 0.4:
            return rng.choice(LEFT) + (f", leaving {things} on the {words['surface']}" if things else "") + "."
        return clause + (f", with {things} on the {words['surface']}" if things and rng.random() < 0.5 else "") + "."
    text = clause.format(**words)
    if text[0].isupper():                    # someone else acts: the phrase is a whole sentence
        return text
    if event["kind"] == "step":
        return f"{subject} {text}."
    alone = text.startswith("is ")           # moving about: no sitting or standing posture in front
    if just_done:                            # what was just done is still mentioned for a few seconds
        return f"{subject} {just_done}, and is now {text[3:] if alone else text}."
    extra = ""
    if rng.random() < 0.75:
        if place == "bed":
            extra = rng.choice(LAMP_ON) if segment.get("lamp") else ""
        elif things:
            extra = rng.choice((", with {} on the {}", ", with {} resting on the {} nearby",
                                ", with {} sitting on the {}")).format(things, words["surface"])
    if alone:
        return f"{subject} {text}{extra}."
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
        event, place = EVENTS[segment["event"]], _place(segment)
        phrases = event["phrases"]
        perfect = [phrase for phrase in phrases if " has " in f" {phrase[:24]}"]
        ongoing = [phrase for phrase in phrases if phrase not in perfect] or list(phrases)
        count = (segment["end"] - segment["start"]) // STEP
        done = EVENTS[before["event"]]["done"] if before else ()
        linger = rng.choice((1, 2, 2, 3, 3, 4)) if done and event["kind"] == "activity" else 0
        just_done = rng.choice(done).format(**_words(_place(before))) if linger else None
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
        elif text[0].isupper():
            examples.append(text)
        elif event["kind"] == "step" or text.startswith("is "):
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
            last["case"] = last["case"] or segment["case"]
        else:
            merged.append(dict(segment))
    return merged


def build_day(day: int, seed: int = SEED) -> list[dict]:
    builder = _Day(day, random.Random(f"{seed}-day{day}"))
    builder.morning()
    builder.breakfast()
    builder.study()
    builder.evening()
    builder.dinner()
    builder.night()
    if builder.t != DAY_END:
        raise ValueError(f"Day {day} ends at {hms(builder.t)}, not {hms(DAY_END)}")
    return _merge_repeats(builder.segments)


def build_week(seed: int = SEED) -> dict[int, list[dict]]:
    return {day: build_day(day, seed) for day in DAYS}


def make_answer_key(week: dict[int, list[dict]], seed: int) -> dict:
    seen: dict[str, Counter] = {}
    for segments in week.values():
        for s in segments:
            seen.setdefault(s["event"], Counter())[_place(s)] += s["end"] - s["start"]
    return {
        "about": "합성 기록 정답표 (혼자 사는 사람의 평일 5일). 모델 입력에 넣지 않는다. 시각은 HH:MM:SS이고 끝 시각은 포함하지 않는다.",
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
    parser = argparse.ArgumentParser(description="합성 기록 평일 5일과 정답표를 만든다. 모델은 부르지 않는다.")
    parser.add_argument("--out", type=Path, required=True, help="기록과 정답표를 쓸 폴더 (이미 있으면 멈춘다)")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    write_outputs(args.out, build_week(args.seed), args.seed)


if __name__ == "__main__":
    main()
