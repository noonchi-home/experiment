"""Event vocabulary for the weekday synthetic record (합성 기록에 쓰는 사건 목록).

The record imitates what the real PAM predictor writes when it watches a video: one
English sentence per frame that describes the whole scene (posture, what the person is
doing, objects lying around), not a bare action label. The style follows the real
observation logs in ai/artifacts/routine_vllm_fsm_2026-11-04/*/predictions.jsonl, e.g.
    A person is sitting at a desk actively typing on a laptop, with a can and a jar
    sitting on the desk nearby.
    The person has finished drinking from the cup, placed it on the desk, and is now
    actively reading an open book.
    The person has left the room, leaving an open book and a can on the desk.

Two kinds of event:
- activity: something that goes on. `phrases` are "-ing" clauses that follow a posture
  ("is sitting at the desk" + "actively typing on a laptop"). A clause that starts with
  "is" stands alone (moving about, e.g. vacuuming).
- step: something done once. `phrases` are whole predicates ("is closing the laptop",
  "has just shut the laptop lid"), or whole sentences when someone else acts ("The guest
  is opening a can of soda.").
`done` is how the next lines still mention what was just done ("has closed the laptop,
and is now ..."), as the real predictor does for a few seconds. `uses` names the things
in the person's hands, which are then not listed as lying around. `ko` is the Korean
label for people. `task` is the index into ai/scenarios/routine/tasks.json when the
person does that robot task themselves.

How to write phrases (2026-11-16, after two wrong tries):
- What the person does belongs in the timeline (make_records.py). The phrases of one
  event only word the same visible thing in different ways, so any order of them over
  time must be possible. Never put another object, place or appliance, or a step that
  happens once, among the phrases of an activity.
- An event used in several places uses {surface}, {from} and {to} instead of naming a
  place, and no phrase says "again": the same event is also used for the first time.
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

# Where the person is, and how the predictor words the posture there.
POSTURE = {
    "bed": ("is lying in bed", "is in bed"),
    "bedside": ("is standing by the bed", "is standing next to the bed"),
    "room": ("is standing in the room", "is standing near the door"),
    "door": ("is standing by the front door", "is standing at the front door"),
    "stove": ("is standing at the stove", "is standing in the kitchen at the stove"),
    "table": ("is sitting at the dining table", "is seated at the dining table", "is sitting at the table"),
    "desk": ("is sitting at the desk", "is seated at the desk", "is sitting at a desk"),
    "deskside": ("is standing by the desk", "is standing next to the desk"),
    "sofa": ("is sitting on the sofa", "is seated on the sofa", "is sitting back on the sofa"),
}
WORDS = {
    "table": {"surface": "table", "from": "from the dining table", "to": "to the dining table"},
    "desk": {"surface": "desk", "from": "from the desk", "to": "to the desk"},
    "deskside": {"surface": "desk", "from": "from the desk", "to": "to the desk"},
    "sofa": {"surface": "side table", "from": "from the sofa", "to": "to the sofa"},
}
ELSEWHERE = {"surface": "counter", "from": "from their seat", "to": "to their seat"}
LAMP_ON = (", with the bedside lamp on", ", while the bedside lamp remains on", ", with the bedside lamp turned on")
LEFT = ("The person has left the room", "The person has walked out of the room",
        "The person has stepped out of the room")


def _event(kind: str, ko: str, phrases: tuple[str, ...], task: int | None, done: tuple[str, ...],
           uses: tuple[str, ...]) -> dict:
    return {"ko": ko, "kind": kind, "phrases": phrases, "task": task, "done": done, "uses": uses}


def _activity(ko: str, phrases: tuple[str, ...], task: int | None = None, done: tuple[str, ...] = (),
              uses: tuple[str, ...] = ()) -> dict:
    return _event("activity", ko, phrases, task, done, uses)


def _step(ko: str, phrases: tuple[str, ...], task: int | None = None, done: tuple[str, ...] = (),
          uses: tuple[str, ...] = ()) -> dict:
    return _event("step", ko, phrases, task, done, uses)


EVENTS = {
    # The person does a robot task themselves (task = index in tasks.json).
    "put_cup_next_to_self": _step("컵을 가져와 자기 옆에 놓는다", (
        "is setting a cup of water down on the {surface} within reach",
        "has just placed a cup of water on the {surface} beside their seat",
        "is putting a cup of water down on the {surface} next to where they sit",
    ), task=0, done=("has placed a cup of water on the {surface}",)),
    "put_cup_in_dishwasher": _step("컵을 식기세척기에 넣는다", (
        "is putting the empty cup into the dishwasher",
        "is loading the cup into the dishwasher rack",
        "has opened the dishwasher and is placing the cup inside",
    ), task=1, done=("has put the cup in the dishwasher",)),
    "put_can_next_to_self": _step("캔을 가져와 소파 옆에 놓는다", (
        "is setting a can down on the side table next to the sofa",
        "has just placed a can on the side table within reach",
        "is putting a can down on the side table beside them",
    ), task=2, done=("has placed a can on the side table",)),
    "put_can_in_storage": _step("빈 캔을 보관 장소에 넣는다", (
        "is dropping the empty can into the storage bin",
        "has carried the empty can to the storage area and is putting it in the bin",
        "is placing the empty can in the designated storage bin",
    ), task=3, done=("has put the empty can away in the storage bin",)),
    "put_book_next_to_self": _step("책을 가져와 자기 옆에 놓는다", (
        "is setting a book down on the sofa next to them",
        "has just placed a book within reach on the sofa",
        "is putting a book down beside them on the sofa",
    ), task=4, done=("has placed a book next to them on the sofa",)),
    "put_book_in_storage": _step("책을 보관 장소에 넣는다", (
        "is putting the book away on the storage shelf",
        "has carried the book to the storage shelf and is placing it there",
        "is filing the book away on the storage shelf",
    ), task=5, done=("has put the book away on the storage shelf",)),
    "put_bowl_in_dishwasher": _step("그릇을 식기세척기에 넣는다", (
        "is putting the empty bowl into the dishwasher",
        "is loading the bowl into the dishwasher rack",
        "has carried the bowl to the kitchen and is placing it in the dishwasher",
    ), task=6, done=("has put the bowl in the dishwasher",)),
    "turn_off_room_light": _step("방 불을 끈다", (
        "is pressing the wall switch to turn off the room light",
        "has just turned off the room light at the wall switch",
        "is switching off the main room light",
    ), task=7, done=("has turned off the room light",)),
    "turn_off_bedside_lamp": _step("침대 옆 스탠드를 끈다", (
        "is switching off the bedside lamp",
        "has just turned off the bedside lamp",
        "is clicking the bedside lamp off",
    ), task=8, done=("has turned off the bedside lamp",)),

    # Approach steps: part of doing a task, never a trigger.
    "get_cup": _step("선반에서 컵을 꺼내 물을 따른다", (
        "is taking a cup from the kitchen shelf and filling it with water",
        "has taken a cup from the shelf and is pouring water into it",
        "is standing in the kitchen filling a cup from the shelf with water",
    )),
    "fill_cup_at_purifier": _step("정수기에서 컵에 물을 받는다", (
        "is filling a cup with water at the water purifier",
        "is standing at the water purifier filling a cup",
        "is holding a cup under the water purifier",
    )),
    "carry_cup_back": _step("물컵을 들고 자리로 돌아온다", (
        "is walking back {to} holding a cup of water",
        "is carrying a cup of water back {to}",
        "is returning {to} with a cup of water in hand",
    )),
    "pick_up_empty_cup": _step("빈 컵을 집는다", (
        "is picking up the empty cup from the table",
        "has picked up the empty cup and is standing up from the table",
        "is lifting the empty cup off the table",
    )),
    "carry_cup_to_kitchen": _step("컵을 들고 주방으로 간다", (
        "is carrying the empty cup to the kitchen",
        "is walking to the kitchen holding the empty cup",
        "is taking the empty cup over to the kitchen",
    )),
    "get_can": _step("냉장고에서 캔을 꺼낸다", (
        "is taking a can out of the fridge",
        "has opened the fridge and is taking out a can",
        "is pulling a can from the refrigerator",
    )),
    "carry_can_back": _step("캔을 들고 소파로 돌아온다", (
        "is walking back to the sofa holding a can",
        "is carrying a can back to the sofa",
        "is returning to the sofa with a can in hand",
    )),
    "pick_up_empty_can": _step("빈 캔을 집는다", (
        "is picking up the empty can from the side table",
        "has picked up the guest's empty can and is standing up from the sofa",
        "is lifting the empty can off the side table",
    )),
    "get_book_from_shelf": _step("책장에서 책을 꺼낸다", (
        "has walked to the bookshelf and is taking out a book",
        "is pulling a book off the bookshelf",
        "is picking a book out of the bookcase",
    )),
    "pick_up_book": _step("책을 집는다", (
        "is picking up the book from the desk",
        "has picked up the book and is standing up from the desk",
        "is lifting the book off the desk",
    )),
    "pick_up_bowl": _step("빈 그릇을 집는다", (
        "is picking up the empty bowl from the table",
        "has picked up the empty bowl and is standing up from the table",
        "is lifting the empty bowl off the table",
    )),
    "walk_to_light_switch": _step("전등 스위치로 간다", (
        "is walking to the light switch on the wall",
        "is heading toward the wall switch by the door",
        "has walked over to the light switch",
    )),
    "reach_for_lamp": _step("스탠드로 손을 뻗는다", (
        "is reaching toward the bedside lamp",
        "is stretching a hand out to the bedside lamp switch",
        "is reaching for the switch of the bedside lamp",
    )),

    # Moving about. The real logs are full of these lines.
    "stand_up": _step("자리에서 일어난다", (
        "has stood up {from}",
        "is getting up {from}",
        "is standing up {from} and stepping away",
    )),
    "walk_to_kitchen": _step("주방으로 간다", (
        "is walking to the kitchen",
        "is heading into the kitchen",
        "has walked over to the kitchen",
    )),
    "leave_room": _step("방에서 나간다", (
        "is walking out of the room",
        "is leaving the room",
        "is heading out of the room through the door",
    )),
    "enter_room": _step("방으로 돌아온다", (
        "has come back into the room",
        "is walking back into the room",
        "has returned to the room",
    )),
    "go_to_sofa": _step("소파로 가서 앉는다", (
        "is walking over to the sofa and sitting down",
        "has just sat down on the sofa",
        "is settling onto the sofa",
    )),
    "return_to_desk": _step("책상으로 돌아온다", (
        "has come back to the desk",
        "is back at the desk and settling in",
        "has returned to the desk",
    )),
    "leave_home": _step("현관으로 나간다", (
        "is walking out through the front door",
        "is leaving the home through the front door",
        "has opened the front door and is stepping out",
    )),

    # Planted trigger candidates.
    "finish_drinking": _step("물을 다 마신다", (
        "is drinking the last of the water and setting the empty cup down on the {surface}",
        "has just emptied the cup and is putting it back down on the {surface}",
        "is tipping the cup all the way back to finish the water, then setting it down empty",
    ), done=("has emptied the cup and set it down on the {surface}",), uses=("cup",)),
    "look_at_phone": _activity("휴대폰을 본다", (
        "looking at their phone",
        "holding a smartphone and looking at it",
        "using a smartphone",
        "scrolling on their phone",
    )),
    "close_book": _step("책을 덮는다", (
        "is closing the book",
        "has just closed the book and set it aside",
        "has finished reading and is closing the book",
    ), done=("has closed the book",)),
    "finish_meal": _step("밥을 다 먹는다", (
        "is eating the last bite of the meal",
        "has just finished the last of the rice",
        "is finishing the meal with a final bite",
    ), done=("has finished the meal",)),
    "wipe_mouth": _step("냅킨으로 입을 닦는다", (
        "is wiping their mouth with a napkin",
        "is dabbing their lips with a napkin",
        "has picked up a napkin and is wiping their mouth",
    ), done=("has wiped their mouth with a napkin",)),
    "put_down_spoon": _step("숟가락을 내려놓는다", (
        "is putting the spoon down on the table",
        "has just set the spoon down beside the bowl",
        "is laying the spoon down next to the bowl",
    )),
    "put_down_chopsticks": _step("젓가락을 내려놓는다", (
        "is putting the chopsticks down on the table",
        "has just set the chopsticks down beside the bowl",
        "is laying the chopsticks down next to the side dishes",
    )),
    "phone_rings": _step("전화가 와서 받는다", (
        "is answering a ringing phone",
        "has picked up an incoming call",
        "is picking up the phone as it rings",
    )),
    "close_laptop": _step("노트북을 닫는다", (
        "is closing the laptop",
        "has just shut the laptop lid",
        "is folding the laptop closed",
    ), done=("has closed the laptop",), uses=("laptop",)),
    "guest_finishes_can": _step("손님이 캔 음료를 다 마신다", (
        "The guest is drinking the last of the soda and setting the empty can down on the side table.",
        "The guest has just finished the can of soda and put the empty can down.",
        "The guest is tipping the can all the way back to finish the soda, then setting it down empty.",
    )),
    "finish_vacuuming": _step("청소기를 다 돌리고 끈다", (
        "is switching off the vacuum cleaner",
        "has just finished vacuuming and turned the vacuum cleaner off",
        "is turning off the vacuum cleaner after finishing the floor",
    ), done=("has finished vacuuming and turned the vacuum cleaner off",)),
    "sit_at_desk": _step("책상에 앉는다", (
        "is sitting down at the desk",
        "has just sat down at the desk",
        "is taking a seat at the desk",
    ), done=("has sat down at the desk",)),
    "put_on_bag": _step("가방을 멘다", (
        "is putting on a backpack",
        "is slinging the bag over their shoulder",
        "has just shouldered their bag",
    ), done=("has put on their bag",)),

    # Everyday background.
    "wake_up": _activity("잠에서 깨 침대에 누워 있다", (
        "awake after just waking up",
        "awake under the covers",
        "awake and stretching a little under the covers",
    )),
    "sit_up_in_bed": _step("침대에서 일어나 앉아 기지개를 켠다", (
        "is sitting up in bed and stretching their arms",
        "is pushing the covers back and sitting up in bed",
        "has sat up in bed and is stretching",
    )),
    "get_out_of_bed": _step("침대에서 나온다", (
        "is getting out of bed",
        "has just gotten out of bed",
        "is standing up from the bed",
    )),
    "turn_on_room_light": _step("방 불을 켠다", (
        "is pressing the wall switch to turn on the room light",
        "has just turned on the room light at the wall switch",
        "is switching on the main room light",
    ), done=("has turned on the room light",)),
    "make_bed": _activity("침대를 정리한다", (
        "making the bed",
        "straightening the blanket and the pillow",
        "tidying the bed and smoothing out the blanket",
    )),
    "get_dressed": _activity("옷을 입는다", (
        "getting dressed",
        "putting on clothes for the day",
        "changing into day clothes",
    )),
    "bring_toast": _step("토스트 접시를 식탁에 가져온다", (
        "is carrying a plate of toast to the dining table",
        "is bringing a plate of toast over to the table",
        "is walking to the table with a plate of toast",
    ), done=("has set a plate of toast on the table",)),
    "sit_at_table": _step("식탁에 앉는다", (
        "is sitting down at the dining table",
        "has just sat down at the table",
        "is pulling out a chair and sitting down at the table",
    ), done=("has sat down at the table",)),
    "eat_breakfast": _activity("아침을 먹는다", (
        "eating toast",
        "eating a piece of toast",
        "having toast for breakfast",
        "taking a bite of toast",
    ), uses=("plate",)),
    "finish_breakfast": _step("아침을 다 먹는다", (
        "is eating the last piece of toast",
        "has just finished the toast",
        "is finishing breakfast with the last bite of toast",
    ), done=("has finished eating breakfast",)),
    "sit_idle_at_table": _activity("식탁에 앉아 쉰다", (
        "doing nothing in particular",
        "resting for a moment after eating",
        "leaning back in the chair",
        "looking ahead idly",
    )),
    "put_plate_in_sink": _step("접시를 싱크대로 가져가 넣는다", (
        "is carrying the empty plate to the kitchen sink",
        "is taking the plate over to the sink",
        "has just put the plate in the kitchen sink",
    ), done=("has put the plate in the sink",)),
    "drink_water": _activity("컵으로 물을 마신다", (
        "drinking water from a cup",
        "holding a cup to their mouth and drinking",
        "taking a sip of water from the cup",
    ), done=("has taken a sip of water and put the cup back down on the {surface}",), uses=("cup",)),
    "open_laptop": _step("노트북을 연다", (
        "is opening the laptop",
        "has just opened the laptop on the desk",
        "is lifting the laptop lid",
    ), done=("has opened the laptop",), uses=("laptop",)),
    "type_on_laptop": _activity("노트북으로 타자를 친다", (
        "actively typing on a laptop",
        "working on a laptop",
        "typing on the laptop keyboard",
        "focused on typing on a laptop",
    ), uses=("laptop",)),
    "read_book_at_desk": _activity("책상에서 책을 읽는다", (
        "reading an open book",
        "actively reading a book",
        "reading and turning the pages of an open book",
        "reading a book that lies open in front of them",
    ), uses=("book",)),
    "write_notes": _activity("공책에 필기한다", (
        "writing notes in a notebook",
        "writing in a notebook",
        "jotting notes down in a notebook",
    )),
    "stretch": _activity("앉은 채로 기지개를 켠다", (
        "stretching their arms overhead",
        "stretching their arms and rolling their shoulders",
        "leaning back and stretching",
    )),
    "look_around": _activity("주변을 둘러본다", (
        "looking around the room",
        "glancing around the room",
        "looking away toward the window",
    )),
    "rub_face": _activity("얼굴을 문지른다", (
        "rubbing their face",
        "rubbing their eyes",
        "looking tired and rubbing their face",
    )),
    "lean_back": _activity("등을 기대고 잠깐 쉰다", (
        "leaning back for a moment",
        "leaning back and pausing",
        "leaning back with their hands in their lap",
    )),
    "shift_position": _activity("자세를 고쳐 앉는다", (
        "shifting their position",
        "adjusting how they sit",
        "shifting their weight on the seat",
    )),
    "yawn": _activity("하품한다", (
        "yawning",
        "yawning widely",
        "covering a yawn with one hand",
    )),
    "pack_bag": _activity("가방을 싼다", (
        "packing things into a bag",
        "putting the laptop and a notebook into a bag",
        "packing a bag on the desk",
    ), uses=("laptop",)),
    "zip_bag": _step("가방 지퍼를 닫는다", (
        "is zipping the bag closed",
        "has just zipped up the bag",
        "is pulling the zipper of the bag shut",
    )),
    "put_on_jacket": _step("겉옷을 입는다", (
        "is putting on a jacket",
        "is pulling on a jacket and adjusting it",
        "is slipping their arms into a jacket",
    )),
    "check_pockets": _step("주머니를 확인한다", (
        "is checking their pockets",
        "is patting their pockets",
        "is feeling through their pockets with both hands",
    )),
    "come_home": _step("현관으로 들어온다", (
        "has just come in through the front door",
        "is coming in through the front door",
        "is stepping inside and closing the front door behind them",
    )),
    "take_off_bag": _step("가방을 내려놓는다", (
        "is taking off their bag and setting it down by the door",
        "has just slipped the bag off their shoulder and put it down",
        "is putting their bag down by the door",
    )),
    "sit_on_sofa": _activity("소파에 앉아 쉰다", (
        "resting",
        "resting with their head back",
        "relaxing without doing anything",
    )),
    "watch_tv": _activity("TV를 본다", (
        "watching TV",
        "watching television",
        "looking at the TV screen",
        "watching something on the TV",
    )),
    "talk_on_phone": _activity("통화한다", (
        "talking on the phone",
        "holding a phone to their ear and talking",
        "having a phone call",
    )),
    "drink_from_can": _activity("캔 음료를 마신다", (
        "drinking from a can",
        "holding a can to their mouth and drinking",
        "taking a sip from the can",
    ), done=("has taken a sip from the can and put it back on the side table",), uses=("can",)),
    "guest_arrives": _step("손님이 온다", (
        "A guest is coming in through the front door, greeted by the person.",
        "The person is welcoming a guest at the front door.",
        "A guest has arrived and is being let in by the person.",
    )),
    "guest_opens_can": _step("손님이 캔 음료를 딴다", (
        "The guest is opening a can of soda.",
        "The guest has just cracked open a can of soda.",
        "The guest is pulling the tab on a can of soda.",
    )),
    "chat_with_guest": _activity("손님과 이야기한다", (
        "chatting with a guest",
        "talking with the guest sitting next to them",
        "having a conversation with a guest",
    )),
    "guest_drinks_can": _step("손님이 캔 음료를 마신다", (
        "The guest is drinking from a can of soda.",
        "The guest is taking a sip from a soda can.",
        "The guest is holding a soda can to their mouth and drinking.",
    )),
    "guest_leaves": _step("손님이 간다", (
        "The guest is saying goodbye and leaving through the front door.",
        "The person is seeing the guest off at the front door.",
        "The guest is leaving, and the person is walking them to the door.",
    )),
    "take_food_from_fridge": _step("냉장고에서 음식을 꺼낸다", (
        "is taking food out of the fridge",
        "has opened the fridge and is taking out containers of food",
        "is getting ingredients from the refrigerator",
    )),
    "cook_dinner": _activity("가스레인지에서 저녁을 만든다", (
        "stirring a pot",
        "cooking dinner in a pot",
        "stirring food in a pot on the stove",
        "watching over a pot on the stove",
    )),
    "put_food_in_microwave": _step("음식을 전자레인지에 넣는다", (
        "is putting a bowl of food into the microwave",
        "has just put a bowl in the microwave and started it",
        "is closing the microwave door on a bowl of food",
    )),
    "take_food_from_microwave": _step("전자레인지에서 음식을 꺼낸다", (
        "is taking the heated bowl out of the microwave",
        "has just taken the bowl of food out of the microwave",
        "is opening the microwave and lifting out the bowl",
    )),
    "bring_dinner": _step("밥그릇과 반찬을 식탁에 가져온다", (
        "is carrying a bowl of rice and side dishes to the dining table",
        "is bringing dinner over to the table",
        "is walking to the table with the rice bowl and side dishes",
    ), done=("has set dinner on the table",)),
    "pick_up_spoon": _step("숟가락을 든다", (
        "is picking up the spoon",
        "has picked up the spoon",
        "is taking the spoon in hand",
    )),
    "pick_up_chopsticks": _step("젓가락을 든다", (
        "is picking up the chopsticks",
        "has picked up the chopsticks",
        "is taking the chopsticks in hand",
    )),
    "eat_dinner": _activity("저녁을 먹는다", (
        "eating rice and side dishes",
        "eating dinner",
        "having dinner",
        "taking a bite of rice",
    ), uses=("dinner",)),
    "wipe_table": _step("식탁을 닦는다", (
        "is wiping the dining table with a cloth",
        "is wiping down the table",
        "is cleaning the table surface with a cloth",
    )),
    "vacuum_floor": _activity("청소기로 바닥을 민다", (
        "is vacuuming the living room floor",
        "is running the vacuum cleaner over the floor",
        "is pushing the vacuum cleaner across the floor",
    )),
    "turn_on_bedside_lamp": _step("침대 옆 스탠드를 켠다", (
        "is switching on the bedside lamp",
        "has just turned on the bedside lamp",
        "is clicking the bedside lamp on",
    ), done=("has turned on the bedside lamp",)),
    "get_into_bed": _step("침대에 눕는다", (
        "is getting into bed",
        "is climbing into bed and pulling up the covers",
        "is pulling the blanket up while getting into bed",
    ), done=("has gotten into bed",)),
    "read_in_bed": _activity("침대에서 책을 읽는다", (
        "reading a book",
        "holding a book and reading",
        "reading and turning the pages of a book",
        "reading with the book propped up in their hands",
    )),
    "lie_back": _activity("베개에 기대 눕는다", (
        "leaning back on the pillow",
        "resting against the pillow with the book closed",
        "settled back on the pillow",
    )),
    "lie_in_dark_bed": _activity("불 끈 방 침대에 누워 있다", (
        "under the covers with their eyes closed",
        "under the covers, appearing to be asleep",
        "under the covers in the dark room",
        "motionless under the covers with the lights off",
    )),
    "unseen": _event("absent", "사람이 보이지 않는다", (
        "No person is visible in the room",
        "The person is not visible in the frame",
        "The room is empty and no person is in view",
    ), None, (), ()),
}
