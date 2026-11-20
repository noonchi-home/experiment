"""Event vocabulary for the synthetic week (합성 기록에 쓰는 사건 목록).

Records are written in English, like the real PAM predictor output. Each event has
several English phrases; a record line picks one at random, so consecutive lines
about the same event are worded differently. `ko` is the Korean label for people.
`task` is the index into ai/scenarios/routine/tasks.json when the person does that
robot task themselves. Approach steps (going to do a task) have no task.
"""

from __future__ import annotations

import json
from pathlib import Path

TASKS_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "routine" / "tasks.json"
TASKS: tuple[str, ...] = tuple(json.loads(TASKS_PATH.read_text(encoding="utf-8")))

STATES = {
    "morning": "아침 준비",
    "breakfast": "아침 식사",
    "study": "공부",
    "going_out": "외출 준비",
    "away": "외출 (안 보임)",
    "evening_rest": "저녁 휴식",
    "dinner": "저녁 식사",
    "bedtime": "잠자리 준비",
}


def _event(ko: str, phrases: tuple[str, ...], task: int | None = None) -> dict:
    return {"ko": ko, "phrases": phrases, "task": task}


EVENTS = {
    # The person does a robot task themselves (task = index in tasks.json).
    "put_cup_next_to_self": _event("컵을 가져와 자기 옆에 놓는다", (
        "The person sets a cup down right next to themselves.",
        "The person places a cup within reach beside them.",
        "The person puts a cup on the table next to where they sit.",
    ), task=0),
    "put_cup_in_dishwasher": _event("컵을 식기세척기에 넣는다", (
        "The person puts the cup in the dishwasher.",
        "The person places the cup into the dishwasher rack.",
        "The person loads the cup into the dishwasher.",
    ), task=1),
    "put_can_next_to_self": _event("캔을 가져와 소파 옆에 놓는다", (
        "The person sets a can down next to the sofa.",
        "The person places a can within reach beside the sofa.",
        "The person puts a can on the side table by the sofa.",
    ), task=2),
    "put_can_in_storage": _event("빈 캔을 보관 장소에 넣는다", (
        "The person puts the empty can in the storage area.",
        "The person places the empty can in the designated storage bin.",
        "The person drops the empty can into the storage box.",
    ), task=3),
    "put_book_in_storage": _event("책을 보관 장소에 넣는다", (
        "The person puts the book in the storage area.",
        "The person places the book on the storage shelf.",
        "The person files the book away on the storage shelf.",
    ), task=5),
    "put_bowl_in_dishwasher": _event("그릇을 식기세척기에 넣는다", (
        "The person puts the bowl in the dishwasher.",
        "The person places the bowl into the dishwasher rack.",
        "The person loads the bowl into the dishwasher.",
    ), task=6),
    "turn_off_room_light": _event("방 불을 끈다", (
        "The person turns off the room light.",
        "The person switches off the ceiling light.",
        "The person flips the wall switch and the room light goes off.",
    ), task=7),
    "turn_off_bedside_lamp": _event("침대 옆 스탠드를 끈다", (
        "The person turns off the bedside lamp.",
        "The person switches off the lamp next to the bed.",
        "The person clicks the bedside lamp off.",
    ), task=8),
    "put_lamp_in_storage": _event("스탠드를 보관 장소에 넣는다", (
        "The person puts the bedside lamp in the storage area.",
        "The person places the bedside lamp on the storage shelf.",
        "The person stores the bedside lamp away in the storage area.",
    ), task=9),

    # Approach steps: part of doing a task, never a trigger.
    "get_cup": _event("선반에서 컵을 집는다", (
        "The person takes a cup from the shelf.",
        "The person picks a cup up off the shelf.",
        "The person grabs a cup from the kitchen shelf.",
    )),
    "pick_up_empty_cup": _event("빈 컵을 집는다", (
        "The person picks up the empty cup.",
        "The person lifts the empty cup off the table.",
        "The person takes the empty cup in hand.",
    )),
    "carry_cup_to_kitchen": _event("컵을 들고 주방으로 간다", (
        "The person carries the cup to the kitchen.",
        "The person walks to the kitchen holding the cup.",
        "The person brings the cup over to the kitchen.",
    )),
    "get_can": _event("냉장고에서 캔을 꺼낸다", (
        "The person takes a can out of the fridge.",
        "The person grabs a can from the fridge.",
        "The person pulls a can out of the refrigerator.",
    )),
    "pick_up_empty_can": _event("빈 캔을 집는다", (
        "The person picks up the empty can.",
        "The person lifts the empty can off the table.",
        "The person takes the empty can in hand.",
    )),
    "pick_up_book": _event("책을 집는다", (
        "The person picks up the book.",
        "The person lifts the book off the desk.",
        "The person takes the book in hand.",
    )),
    "pick_up_bowl": _event("빈 그릇을 집는다", (
        "The person picks up the empty bowl.",
        "The person lifts the empty bowl off the table.",
        "The person takes the empty bowl in hand.",
    )),
    "walk_to_light_switch": _event("전등 스위치로 간다", (
        "The person walks to the light switch.",
        "The person goes over to the wall switch.",
        "The person heads to the light switch by the door.",
    )),
    "reach_for_lamp": _event("스탠드로 손을 뻗는다", (
        "The person reaches for the bedside lamp.",
        "The person stretches a hand toward the bedside lamp.",
        "The person extends an arm to the lamp switch.",
    )),
    "pick_up_lamp": _event("스탠드를 집어 든다", (
        "The person picks up the bedside lamp.",
        "The person lifts the bedside lamp.",
        "The person takes the bedside lamp in both hands.",
    )),

    # Planted trigger candidates.
    "finish_drinking": _event("물을 다 마신다", (
        "The person finishes the water and sets the empty cup down.",
        "The person drinks the last of the water and puts the cup down.",
        "The person empties the cup and places it on the table.",
    )),
    "look_at_phone": _event("휴대폰을 본다", (
        "The person looks at their phone.",
        "The person scrolls through their smartphone.",
        "The person checks the phone screen.",
    )),
    "close_book": _event("책을 덮는다", (
        "The person closes the book.",
        "The person shuts the book and sets it aside.",
        "The person finishes reading and closes the book.",
    )),
    "finish_meal": _event("밥을 다 먹는다", (
        "The person finishes eating the rice.",
        "The person eats the last bite of the meal.",
        "The person finishes the meal.",
    )),
    "put_down_spoon": _event("숟가락을 내려놓는다", (
        "The person puts down the spoon.",
        "The person sets the spoon on the table.",
        "The person lays the spoon down beside the bowl.",
    )),
    "put_down_chopsticks": _event("젓가락을 내려놓는다", (
        "The person puts down the chopsticks.",
        "The person sets the chopsticks on the table.",
        "The person lays the chopsticks down beside the plate.",
    )),
    "phone_rings": _event("전화가 와서 받는다", (
        "The person's phone rings and they answer it.",
        "The person takes an incoming phone call.",
        "The person answers a call on their phone.",
    )),
    "close_laptop": _event("노트북을 닫는다", (
        "The person closes the laptop.",
        "The person shuts the laptop lid.",
        "The person folds the laptop closed.",
    )),
    "guest_finishes_can": _event("손님이 캔 음료를 다 마신다", (
        "The guest finishes a can of soda.",
        "The guest drinks the last of the canned drink.",
        "The guest empties the soda can.",
    )),
    "finish_vacuuming": _event("청소기를 다 돌리고 끈다", (
        "The person finishes vacuuming and switches the vacuum off.",
        "The person turns off the vacuum cleaner.",
        "The person stops vacuuming and powers the cleaner down.",
    )),
    "sit_at_desk": _event("책상에 앉는다", (
        "The person sits down at the desk.",
        "The person takes a seat at the desk.",
        "The person settles into the desk chair.",
    )),
    "put_on_bag": _event("가방을 멘다", (
        "The person puts on a backpack.",
        "The person shoulders their bag.",
        "The person slings the bag over their shoulder.",
    )),

    # Everyday background.
    "wake_up": _event("일어나 기지개를 켠다", (
        "The person wakes up and stretches in bed.",
        "The person sits up in bed and stretches.",
        "The person gets out of bed slowly.",
    )),
    "wash_face": _event("세수를 한다", (
        "The person washes their face at the sink.",
        "The person splashes water on their face.",
        "The person rinses their face at the bathroom sink.",
    )),
    "get_dressed": _event("옷을 입는다", (
        "The person gets dressed.",
        "The person puts on a shirt and pants.",
        "The person changes into day clothes.",
    )),
    "eat_breakfast": _event("아침을 먹는다", (
        "The person eats toast at the dining table.",
        "The person is having breakfast at the table.",
        "The person eats cereal at the dining table.",
    )),
    "drink_water": _event("컵으로 물을 마신다", (
        "The person drinks water from a cup.",
        "The person sips water from the cup.",
        "The person is drinking a cup of water.",
    )),
    "type_on_laptop": _event("노트북으로 타자를 친다", (
        "The person types on the laptop.",
        "The person is working on the laptop.",
        "The person taps away at the laptop keyboard.",
    )),
    "read_book_at_desk": _event("책상에서 책을 읽는다", (
        "The person reads a book at the desk.",
        "The person is reading at the desk.",
        "The person turns a page of the book at the desk.",
    )),
    "write_notes": _event("공책에 필기한다", (
        "The person writes notes in a notebook.",
        "The person jots something down in a notebook.",
        "The person is writing in a notebook at the desk.",
    )),
    "check_pockets": _event("주머니를 확인한다", (
        "The person checks their pockets.",
        "The person pats their pockets for keys.",
        "The person looks through their pockets.",
    )),
    "watch_tv": _event("TV를 본다", (
        "The person watches TV from the sofa.",
        "The person is watching television.",
        "The person looks at the TV screen.",
    )),
    "sit_on_sofa": _event("소파에 앉아 쉰다", (
        "The person relaxes on the sofa.",
        "The person sits on the sofa resting.",
        "The person leans back on the sofa.",
    )),
    "chat_with_guest": _event("손님과 이야기한다", (
        "The person chats with a guest on the sofa.",
        "The person talks with the visiting guest.",
        "The person and a guest are having a conversation.",
    )),
    "eat_dinner": _event("저녁을 먹는다", (
        "The person eats rice and side dishes.",
        "The person is having dinner at the table.",
        "The person eats dinner with a spoon.",
    )),
    "pick_up_chopsticks": _event("젓가락을 다시 든다", (
        "The person picks the chopsticks up again.",
        "The person takes the chopsticks back in hand.",
        "The person lifts the chopsticks to keep eating.",
    )),
    "vacuum_floor": _event("청소기로 바닥을 민다", (
        "The person vacuums the living room floor.",
        "The person runs the vacuum cleaner over the floor.",
        "The person cleans the floor with the vacuum cleaner.",
    )),
    "read_in_bed": _event("침대에서 책을 읽는다", (
        "The person reads a book in bed.",
        "The person is reading in bed under the lamp.",
        "The person turns a page while lying in bed.",
    )),
    "lie_back": _event("베개에 기대 눕는다", (
        "The person lies back against the pillow.",
        "The person leans back on the pillow.",
        "The person settles down on the pillow.",
    )),
    "lie_in_dark_bed": _event("불 끈 방 침대에 누워 있다", (
        "The person lies in bed with the lights off.",
        "The person is lying in the dark bedroom.",
        "The person rests in bed in the dark.",
    )),
    "unseen": _event("사람이 보이지 않는다", (
        "The person is not visible in the camera view.",
        "No one is in view.",
        "The room appears empty; the person is out of sight.",
    )),
}
