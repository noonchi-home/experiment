"""Make the 7-day synthetic record and its answer key (합성 기록 7일과 정답표 만들기).

No model is called. A record holds only `HH:MM:SS | sentence`, one line every 2 seconds
from 07:00:00 to 23:00:00. The answer key (states, roles, planted cases, expected
nights) goes to a separate file and must never be given to a model.

The planted cases follow 설계문서/2026-11-14_PAM_80퍼센트_p-value_구현계획서.md, chapter 7.
Every planted action starts 2 to 4.5 minutes after its candidate starts, and within
5 minutes after it ends, so "within 5 minutes" holds whichever end is measured from.

Usage (writes files; run only for the experiment):
    python make_records.py --out ../data
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from vocabulary import EVENTS, STATES, TASKS

SEED = 20261114
STEP = 2                     # seconds between record lines
FOLLOW = 300                 # "within 5 minutes"
SLOT = 300                   # 5-minute slots used for the base rate
DAY_START, DAY_END = 7 * 3600, 23 * 3600
DAYS = range(1, 8)


def sec(text: str) -> int:
    hours, minutes, seconds = map(int, text.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def hms(value: int) -> str:
    return f"{value // 3600:02d}:{value // 60 % 60:02d}:{value % 60:02d}"


BLOCKS = (  # (start, end, state), the same every day
    (sec("07:00:00"), sec("07:30:00"), "morning"),
    (sec("07:30:00"), sec("08:00:00"), "breakfast"),
    (sec("08:00:00"), sec("12:30:00"), "study"),
    (sec("12:30:00"), sec("12:35:00"), "going_out"),
    (sec("12:35:00"), sec("17:00:00"), "away"),
    (sec("17:00:00"), sec("18:30:00"), "evening_rest"),
    (sec("18:30:00"), sec("19:30:00"), "dinner"),
    (sec("19:30:00"), sec("22:00:00"), "evening_rest"),
    (sec("22:00:00"), sec("23:00:00"), "bedtime"),
)

BACKGROUND = {  # repeated names are picked more often
    "morning": ("wake_up", "wash_face", "get_dressed", "look_at_phone"),
    "breakfast": ("eat_breakfast", "drink_water"),
    "study": ("type_on_laptop", "read_book_at_desk", "write_notes", "drink_water",
              "look_at_phone", "look_at_phone"),
    "going_out": ("check_pockets",),
    "evening_rest": ("watch_tv", "sit_on_sofa", "look_at_phone", "look_at_phone"),
    "dinner": ("eat_dinner", "drink_water"),
}
GUEST_BACKGROUND = ("watch_tv", "chat_with_guest", "chat_with_guest", "look_at_phone")

# Case "frequent_action": the person brings a cup next to themselves in about a fifth
# of the visible 5-minute slots, away from the other planted cases.
FETCH_STATES = {"morning", "breakfast", "study", "evening_rest", "dinner"}
FETCHES_PER_DAY = 28
QUIET = 60                   # seconds kept free around every planted event

EVERY_NIGHT_FROM_2 = (2, 3, 4, 5, 6, 7)
RULES = (
    {"id": "R1", "state": "breakfast", "task": 1,
     "candidates": [{"event": "finish_drinking", "expected_nights": EVERY_NIGHT_FROM_2},
                    {"event": "look_at_phone", "expected_nights": ()}],
     "forbidden": ["pick_up_empty_cup", "carry_cup_to_kitchen"]},
    {"id": "R2", "state": "bedtime", "task": 8,
     "candidates": [{"event": "close_book", "expected_nights": (5, 6, 7)}],
     "forbidden": ["reach_for_lamp"]},
    {"id": "R3", "state": "dinner", "task": 6,
     "candidates": [{"event": "finish_meal", "expected_nights": EVERY_NIGHT_FROM_2},
                    {"event": "put_down_spoon", "expected_nights": EVERY_NIGHT_FROM_2},
                    {"event": "put_down_chopsticks", "expected_nights": ()}],
     "forbidden": ["pick_up_bowl"]},
    {"id": "R4", "state": "evening_rest", "task": 2,
     "candidates": [{"event": "phone_rings", "expected_nights": (2,)}],
     "forbidden": ["get_can"]},
    {"id": "R5", "state": "study", "task": 5,
     "candidates": [{"event": "close_laptop", "expected_nights": ()}],
     "forbidden": ["pick_up_book"]},
    {"id": "R6", "state": "evening_rest", "task": 3,
     "candidates": [{"event": "guest_finishes_can", "expected_nights": (4, 5, 6, 7)}],
     "forbidden": ["pick_up_empty_can"]},
    {"id": "R7", "state": "evening_rest", "task": 9,
     "candidates": [{"event": "finish_vacuuming", "expected_nights": ()}],
     "forbidden": ["pick_up_lamp"]},
    {"id": "R8", "state": "study", "task": 0,
     "candidates": [{"event": "sit_at_desk", "expected_nights": (7,)}],
     "forbidden": ["get_cup"]},
    {"id": "R9", "state": "going_out", "task": 7,
     "candidates": [{"event": "put_on_bag", "expected_nights": EVERY_NIGHT_FROM_2}],
     "forbidden": ["walk_to_light_switch"]},
)

CASES = (
    {"id": "daily_habit", "ko": "매일 하는 습관", "rule": "R1", "candidate": "finish_drinking",
     "true_habit": "예", "note": "매일 07:50 물을 다 마시고 3분 뒤 컵을 식기세척기에 넣는다."},
    {"id": "same_event_other_state", "ko": "같은 사건, 다른 상태", "rule": "R1", "candidate": "finish_drinking",
     "true_habit": "예 ([아침 식사]에서만)",
     "note": "[공부]에서도 매일 10:15에 물을 다 마시지만 컵은 그대로 둔다. 하루 전체로 세면 14번 중 7번(50%)이라 "
             "떨어진다. 상태별로 세야 [아침 식사] 규칙만 채택된다."},
    {"id": "occasional_miss", "ko": "가끔 빠지는 습관", "rule": "R2", "candidate": "close_book",
     "true_habit": "예", "note": "2일째만 책을 덮고 30분 뒤에 스탠드를 끈다. 그래서 5일째 밤(5번 중 4번)에야 통과한다."},
    {"id": "two_candidates", "ko": "후보 둘이 같이 통과", "rule": "R3", "candidate": "finish_meal",
     "true_habit": "예 (둘 다 맞음)",
     "note": "밥을 다 먹고 1분 뒤 숟가락을 내려놓고, 그 2분 뒤 그릇을 넣는다. 두 후보 모두 통과해 'or'로 묶인다."},
    {"id": "frequent_event", "ko": "자주 있는 사건", "rule": "R1", "candidate": "look_at_phone",
     "true_habit": "아니요",
     "note": "휴대폰은 하루 15번 넘게 본다. [아침 식사]에서는 매일 3번 보고, 그중 마지막 1번만 컵 넣기 5분 안이다."},
    {"id": "early_coincidence", "ko": "처음 며칠에 겹친 우연", "rule": "R4", "candidate": "phone_rings",
     "true_habit": "아니요 (기준의 약점)",
     "note": "전화는 매일 17:40에 온다. 1·2일째에만 우연히 2분 뒤 캔을 소파 옆에 가져온다."},
    {"id": "half", "ko": "반쯤 하는 일", "rule": "R5", "candidate": "close_laptop",
     "true_habit": "아니요", "note": "1·3·5·7일째만 노트북을 닫고 2분 뒤 책을 보관 장소에 넣는다."},
    {"id": "one_day_burst", "ko": "하루에 몰림", "rule": "R6", "candidate": "guest_finishes_can",
     "true_habit": "아니요 (기준의 약점)",
     "note": "4일째에만 손님이 캔을 3번 다 마시고, 매번 2분 뒤 캔을 보관 장소에 넣는다."},
    {"id": "first_seen", "ko": "처음 본 행동", "rule": "R7", "candidate": "finish_vacuuming",
     "true_habit": "모름", "note": "6일째에만 청소기를 다 돌리고 끈 뒤, 2분 뒤 스탠드를 보관 장소에 넣는다."},
    {"id": "frequent_action", "ko": "원래 자주 하는 행동", "rule": "R8", "candidate": "sit_at_desk",
     "true_habit": "예",
     "note": "컵을 자기 옆에 가져오는 일을 보이는 5분 칸의 약 20%에서 한다. 책상에 앉은 뒤에는 3일째만 빼고 "
             "3분 뒤 가져온다. 다른 때 비율이 0.185~0.235면 7일째 밤에만 통과한다."},
    {"id": "unseen", "ko": "못 봄", "rule": "R9", "candidate": "put_on_bag", "true_habit": "예",
     "note": "3·5일째엔 가방을 멘 뒤 사람이 보이지 않는다. 불은 안 보이는 곳에서 껐다(기록에 없음). "
             "못 본 회차를 빼야 계속 통과한다."},
    {"id": "repeated_candidate", "ko": "행동 없이 반복된 후보", "rule": "R3", "candidate": "put_down_chopsticks",
     "true_habit": "아니요",
     "note": "매일 저녁 젓가락을 18:56, 18:57, 18:57:40에 내려놓았다가 다시 든다. 셋 다 그릇 넣기(19:01) 5분 안이지만, "
             "행동 바로 앞의 마지막 한 번만 인정해 3번 중 1번(33%)이라 떨어진다. 셋을 다 인정하면 첫날 밤에 바로 통과해 버린다."},
    {"id": "part_of_action", "ko": "행동의 일부", "rule": None, "candidate": None, "true_habit": "아니요",
     "note": "모든 행동 앞에 그 행동을 하러 가는 줄이 있다. 각 규칙의 forbidden 사건이 예측 모델용 FSM에 들어가면 실패다."},
)


def state_at(moment: int) -> str:
    for start, end, state in BLOCKS:
        if start <= moment < end:
            return state
    raise ValueError(f"No state block covers {hms(moment)}")


def render_lines(segments: list[dict], seed_text: str) -> list[str]:
    """One line every STEP seconds; each line picks a phrase of the event active then."""
    rng = random.Random(seed_text)
    return [f"{hms(moment)} | {rng.choice(EVENTS[segment['event']]['phrases'])}"
            for segment in segments for moment in range(segment["start"], segment["end"], STEP)]


def _planted(day: int) -> list[dict]:
    planted = []

    def add(start: int | str, event: str, seconds: int, role: str, case: str | None) -> None:
        begin = sec(start) if isinstance(start, str) else start
        planted.append({"start": begin, "end": begin + seconds, "event": event, "role": role, "case": case})

    # Breakfast: phone three times (only the last within 5 minutes of the cup), then the cup habit.
    for start in ("07:35:00", "07:42:00", "07:48:30"):
        add(start, "look_at_phone", 60, "candidate", "frequent_event")
    add("07:49:30", "drink_water", 30, "background", "daily_habit")
    add("07:50:00", "finish_drinking", 4, "candidate", "daily_habit")
    add("07:52:52", "pick_up_empty_cup", 4, "approach", "daily_habit")
    add("07:52:56", "carry_cup_to_kitchen", 4, "approach", "daily_habit")
    add("07:53:00", "put_cup_in_dishwasher", 6, "action", "daily_habit")

    # Study.
    add("08:00:00", "sit_at_desk", 4, "candidate", "frequent_action")
    if day != 3:
        add("08:02:56", "get_cup", 4, "approach", "frequent_action")
        add("08:03:00", "put_cup_next_to_self", 4, "action", "frequent_action")
    add("10:14:30", "drink_water", 30, "background", "same_event_other_state")
    add("10:15:00", "finish_drinking", 4, "candidate", "same_event_other_state")
    add("12:00:00", "close_laptop", 4, "candidate", "half")
    if day % 2 == 1:
        add("12:01:56", "pick_up_book", 4, "approach", "half")
        add("12:02:00", "put_book_in_storage", 6, "action", "half")

    # Going out; on days 3 and 5 the person walks out of view before the light goes off.
    add("12:30:00", "put_on_bag", 4, "candidate", "unseen")
    if day in (3, 5):
        add("12:30:04", "unseen", sec("17:00:00") - sec("12:30:04"), "unseen", "unseen")
    else:
        add("12:31:56", "walk_to_light_switch", 4, "approach", "unseen")
        add("12:32:00", "turn_off_room_light", 6, "action", "unseen")
        add("12:32:06", "unseen", sec("17:00:00") - sec("12:32:06"), "unseen", None)

    # Evening rest.
    add("17:40:00", "phone_rings", 60, "candidate", "early_coincidence")
    if day in (1, 2):
        add("17:41:56", "get_can", 4, "approach", "early_coincidence")
        add("17:42:00", "put_can_next_to_self", 4, "action", "early_coincidence")
    if day == 4:
        for start in ("17:20:00", "17:50:00", "18:15:00"):
            add(start, "guest_finishes_can", 4, "candidate", "one_day_burst")
            add(sec(start) + 116, "pick_up_empty_can", 4, "approach", "one_day_burst")
            add(sec(start) + 120, "put_can_in_storage", 6, "action", "one_day_burst")

    # Dinner: chopsticks go down three times (picked up again in between), all within
    # five minutes of the bowl; only the last one comes right before it.
    for start, gap_event, gap, eat in (("18:56:00", "drink_water", 46, 6), ("18:57:00", "drink_water", 20, 12)):
        begin = sec(start)
        add(begin, "put_down_chopsticks", 4, "candidate", "repeated_candidate")
        add(begin + 4, gap_event, gap, "background", "repeated_candidate")
        add(begin + 4 + gap, "pick_up_chopsticks", 4, "background", "repeated_candidate")
        add(begin + 8 + gap, "eat_dinner", eat, "background", "repeated_candidate")
    add("18:57:40", "put_down_chopsticks", 4, "candidate", "repeated_candidate")
    add("18:57:44", "eat_dinner", 16, "background", "repeated_candidate")
    add("18:58:00", "finish_meal", 4, "candidate", "two_candidates")
    add("18:59:00", "put_down_spoon", 4, "candidate", "two_candidates")
    add("19:00:56", "pick_up_bowl", 4, "approach", "two_candidates")
    add("19:01:00", "put_bowl_in_dishwasher", 6, "action", "two_candidates")

    if day == 6:
        add("20:30:00", "vacuum_floor", 600, "background", "first_seen")
        add("20:40:00", "finish_vacuuming", 4, "candidate", "first_seen")
        add("20:41:56", "pick_up_lamp", 4, "approach", "first_seen")
        add("20:42:00", "put_lamp_in_storage", 6, "action", "first_seen")

    # Bedtime; on day 2 the lamp goes off 30 minutes after the book is closed.
    lamp = sec("22:50:00") if day == 2 else sec("22:22:00")
    add("22:00:00", "read_in_bed", 1200, "background", "occasional_miss")
    add("22:20:00", "close_book", 4, "candidate", "occasional_miss")
    add("22:20:04", "look_at_phone" if day == 2 else "lie_back", lamp - 4 - sec("22:20:04"),
        "background", "occasional_miss")
    add(lamp - 4, "reach_for_lamp", 4, "approach", "occasional_miss")
    add(lamp, "turn_off_bedside_lamp", 6, "action", "occasional_miss")
    add(lamp + 6, "lie_in_dark_bed", DAY_END - lamp - 6, "background", None)
    return planted


def _frequent_cup_fetches(planted: list[dict], rng: random.Random) -> list[dict]:
    blocked = [(s["start"] - QUIET, s["end"] + QUIET) for s in planted]
    blocked.append((sec("08:00:00"), sec("08:10:00")))  # after sitting down only the planted fetch
    choices = {}
    for slot in range(DAY_START, DAY_END, SLOT):
        if state_at(slot) not in FETCH_STATES or state_at(slot + SLOT - 1) != state_at(slot):
            continue
        offsets = [offset for offset in range(0, SLOT - 8 + 1, STEP)
                   if all(slot + offset + 8 <= low or slot + offset >= high for low, high in blocked)]
        if offsets:
            choices[slot] = offsets
    fetches = []
    for slot in sorted(rng.sample(sorted(choices), FETCHES_PER_DAY)):
        start = slot + rng.choice(choices[slot])
        fetches.append({"start": start, "end": start + 4, "event": "get_cup",
                        "role": "approach", "case": "frequent_action"})
        fetches.append({"start": start + 4, "end": start + 8, "event": "put_cup_next_to_self",
                        "role": "action", "case": "frequent_action"})
    return fetches


def _background(segments: list[dict], low: int, high: int, state: str, day: int,
                previous: str | None, rng: random.Random) -> str | None:
    guest = day == 4 and state == "evening_rest" and low < sec("18:30:00")
    pool = GUEST_BACKGROUND if guest else BACKGROUND[state]
    while low < high:
        length = min(high - low, rng.randrange(30, 602, STEP))
        if 0 < high - low - length < 30:
            length = high - low
        event = rng.choice([name for name in pool if name != previous] or pool)
        segments.append({"start": low, "end": low + length, "event": event, "state": state,
                         "role": "background", "case": None})
        low, previous = low + length, event
    return previous


def _fill(planted: list[dict], day: int, rng: random.Random) -> list[dict]:
    segments, cursor, previous = [], DAY_START, None
    for item in [*sorted(planted, key=lambda s: s["start"]), None]:
        stop = DAY_END if item is None else item["start"]
        if stop < cursor:
            raise ValueError(f"Planted events overlap at {hms(stop)} on day {day}")
        for start, end, state in BLOCKS:
            low, high = max(cursor, start), min(stop, end)
            if low < high:
                previous = _background(segments, low, high, state, day, previous, rng)
        if item is None:
            return segments
        state = "away" if item["event"] == "unseen" else state_at(item["start"])
        segments.append({**item, "state": state})
        cursor, previous = item["end"], item["event"]
    return segments


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
    rng = random.Random(f"{seed}-day{day}")
    planted = _planted(day)
    planted += _frequent_cup_fetches(planted, rng)
    return _merge_repeats(_fill(planted, day, rng))


def build_week(seed: int = SEED) -> dict[int, list[dict]]:
    return {day: build_day(day, seed) for day in DAYS}


def make_answer_key(week: dict[int, list[dict]], seed: int) -> dict:
    return {
        "about": "합성 기록 정답표. 모델 입력에 넣지 않는다. 시각은 HH:MM:SS이고 끝 시각은 포함하지 않는다.",
        "seed": seed,
        "line_seconds": STEP,
        "follow_seconds": FOLLOW,
        "day_start": hms(DAY_START),
        "day_end": hms(DAY_END),
        "tasks": list(TASKS),
        "states": dict(STATES),
        "events": {name: {"ko": event["ko"], "task": event["task"], "phrases": list(event["phrases"])}
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
    parser = argparse.ArgumentParser(description="합성 기록 7일과 정답표를 만든다. 모델은 부르지 않는다.")
    parser.add_argument("--out", type=Path, required=True, help="기록과 정답표를 쓸 폴더 (이미 있으면 멈춘다)")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    write_outputs(args.out, build_week(args.seed), args.seed)


if __name__ == "__main__":
    main()
