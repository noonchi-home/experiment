"""Event vocabulary for the one-hour morning record (아침 1시간 합성 기록에 쓰는 사건 목록).

The record imitates what the real PAM predictor writes when it watches a video: one
English sentence per line that describes the whole scene (posture, what the person is
doing, things lying around), not a bare action label. The style follows the real
observation logs in ai/artifacts/routine_vllm_fsm_2026-11-04/*/predictions.jsonl.

Two kinds of event:
- activity: something that goes on. `phrases` are "-ing" clauses that follow a posture
  ("is sitting at the dining table" + "eating cereal with a spoon"). A clause that starts
  with "is" stands alone (moving about).
- step: something done once. `phrases` are whole predicates ("is opening the curtains",
  "has just pulled the curtains open"), or whole sentences when someone else acts.
`done` is how the next lines still mention what was just done. `uses` names the things in
the person's hands, which are then not listed as lying around. `ko` is the Korean label for
people. `task` is the index into ai/scenarios/routine/tasks.json when the person does that
robot task themselves.

How to write phrases (2026-11-16): the phrases of one event only word the same visible
thing in different ways, so any order of them over time must be possible. What the person
does belongs in the timeline (make_records.py), never in the wording. An event used in
several places uses {surface}, {from} and {to} instead of naming a place, and no phrase
says "again". The room light is only called "room light" or "main room light", as in the
real logs.
"""

from __future__ import annotations

import json
from pathlib import Path

TASKS_PATH = Path(__file__).resolve().parents[3] / "scenarios" / "routine" / "tasks.json"
TASKS: tuple[str, ...] = tuple(json.loads(TASKS_PATH.read_text(encoding="utf-8")))

STATES = {
    "wake": "잠에서 깨서 씻고 옷 입기",
    "breakfast": "아침 식사",
    "rest": "소파에서 커피 마시며 TV 보기",
    "leaving": "외출 준비",
    "away": "외출 (안 보임)",
}

# Where the person is, and how the predictor words the posture there.
POSTURE = {
    "bed": ("is lying in bed", "is in bed"),
    "bededge": ("is sitting on the edge of the bed", "is sitting on the side of the bed"),
    "bedside": ("is standing by the bed", "is standing next to the bed"),
    "window": ("is standing at the window", "is standing by the window"),
    "room": ("is standing in the room", "is standing in the middle of the room"),
    "door": ("is standing by the front door", "is standing at the front door"),
    "kitchen": ("is standing in the kitchen", "is standing at the kitchen counter"),
    "table": ("is sitting at the dining table", "is seated at the dining table", "is sitting at the table"),
    "sofa": ("is sitting on the sofa", "is seated on the sofa", "is sitting back on the sofa"),
    "deskside": ("is standing by the desk", "is standing next to the desk"),
}
WORDS = {
    "table": {"surface": "table", "from": "from the dining table", "to": "to the dining table"},
    "sofa": {"surface": "side table", "from": "from the sofa", "to": "to the sofa"},
    "deskside": {"surface": "desk", "from": "from the desk", "to": "to the desk"},
    "bed": {"surface": "bedside table", "from": "from the bed", "to": "to the bed"},
}
ELSEWHERE = {"surface": "counter", "from": "from where they were", "to": "to where they were"}
LEFT = ("The person has left the room", "The person has walked out of the room",
        "The person has stepped out of the room")
# How the surroundings are described near the bed and the window, and on the sofa while the TV is on.
CURTAIN_PLACES = ("bed", "bededge", "bedside", "window")
CURTAINS_CLOSED = (", with the curtains still closed", ", with the curtains still drawn")
CURTAINS_OPEN = (", with daylight coming in through the open curtains", ", with morning light coming in")
TV_ON = (", with the TV on in front of them", ", while the TV is on")


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
    "open_curtains": _step("커튼을 연다", (
        "is opening the curtains",
        "is drawing the curtains open to let the light in",
        "has just pulled the curtains open",
    ), task=10, done=("has opened the curtains",)),
    "put_bowl_in_dishwasher": _step("그릇을 식기세척기에 넣는다", (
        "is putting the empty bowl into the dishwasher",
        "is loading the bowl into the dishwasher rack",
        "has just placed the bowl in the dishwasher",
    ), task=6, done=("has put the bowl in the dishwasher",)),
    "put_cup_in_dishwasher": _step("컵을 식기세척기에 넣는다", (
        "is putting the empty cup into the dishwasher",
        "is loading the cup into the dishwasher rack",
        "has just placed the cup in the dishwasher",
    ), task=1, done=("has put the cup in the dishwasher",)),
    "put_can_next_to_self": _step("캔 커피를 소파 옆 탁자에 놓는다", (
        "is setting a can of coffee down on the side table next to the sofa",
        "is putting a can of coffee down on the side table beside them",
        "has just placed a can of coffee on the side table within reach",
    ), task=2, done=("has placed a can of coffee on the side table",)),
    "put_can_in_storage": _step("빈 캔을 보관함에 넣는다", (
        "is dropping the empty can into the storage bin",
        "is placing the empty coffee can in the designated storage bin",
        "has just put the empty can in the storage bin",
    ), task=3, done=("has put the empty can in the storage bin",)),
    "turn_off_room_light": _step("방 불을 끈다", (
        "is pressing the wall switch to turn off the room light",
        "is switching off the main room light",
        "has just turned off the room light at the wall switch",
    ), task=7, done=("has turned off the room light",)),

    # Approach steps: part of doing a task, never a trigger.
    "walk_to_curtains": _step("창가로 간다", (
        "is walking over to the window",
        "is heading to the curtains",
        "has walked up to the window",
    )),
    "pick_up_dishes": _step("빈 그릇과 컵을 집는다", (
        "is picking up the empty bowl and the cup from the table",
        "is gathering the bowl and the cup from the table",
        "has picked up the bowl and the cup and is standing up from the table",
    )),
    "carry_dishes_to_kitchen": _step("그릇과 컵을 들고 주방으로 간다", (
        "is carrying the bowl and the cup to the kitchen",
        "is walking over to the kitchen holding the bowl and the cup",
        "is taking the dishes over to the kitchen",
    )),
    "take_coffee_from_fridge": _step("냉장고에서 캔 커피를 꺼낸다", (
        "is taking a can of coffee out of the fridge",
        "is pulling a can of coffee from the refrigerator",
        "has opened the fridge and is taking out a can of coffee",
    )),
    "carry_coffee_to_sofa": _step("캔 커피를 들고 소파로 간다", (
        "is walking to the sofa holding a can of coffee",
        "is carrying a can of coffee over to the sofa",
        "is bringing a can of coffee to the sofa",
    )),
    "pick_up_empty_can": _step("빈 캔을 집는다", (
        "is picking up the empty can from the side table",
        "is lifting the empty can off the side table",
        "has picked up the empty can and is standing up from the sofa",
    )),
    "carry_can_to_bin": _step("빈 캔을 들고 보관함으로 간다", (
        "is walking to the storage bin with the empty can",
        "is carrying the empty can over to the storage bin",
        "is taking the empty can to the storage bin",
    )),
    "walk_to_light_switch": _step("전등 스위치로 간다", (
        "is walking to the light switch on the wall",
        "is heading toward the wall switch by the door",
        "has walked over to the light switch",
    )),

    # Planted trigger candidates.
    "get_out_of_bed": _step("침대에서 일어난다", (
        "is getting out of bed",
        "is standing up from the bed",
        "has just gotten out of bed",
    ), done=("has gotten out of bed",)),
    "finish_drinking": _step("물을 다 마신다", (
        "is drinking the last of the water and setting the empty cup down on the {surface}",
        "is tipping the cup all the way back to finish the water, then setting it down empty",
        "has just emptied the cup and is putting it back down on the {surface}",
    ), done=("has emptied the cup and set it down on the {surface}",), uses=("cup",)),
    "look_at_phone": _activity("휴대폰을 본다", (
        "looking at their phone",
        "holding a smartphone and looking at it",
        "using a smartphone",
        "scrolling on their phone",
    )),
    "finish_meal": _step("시리얼을 다 먹는다", (
        "is eating the last spoonful of cereal",
        "is scraping up the last of the cereal from the bowl",
        "has just finished the bowl of cereal",
    ), done=("has finished the cereal",), uses=("bowl",)),
    "wipe_mouth": _step("냅킨으로 입을 닦는다", (
        "is wiping their mouth with a napkin",
        "is dabbing their lips with a napkin",
        "has picked up a napkin and is wiping their mouth",
    ), done=("has wiped their mouth with a napkin",)),
    "finish_coffee": _step("커피를 다 마신다", (
        "is drinking the last of the coffee and setting the empty can down on the side table",
        "is tipping the can all the way back to finish the coffee",
        "has just finished the can of coffee and put it down",
    ), done=("has finished the coffee and set the empty can down",), uses=("can",)),
    "phone_rings": _step("전화가 와서 받는다", (
        "is answering a ringing phone",
        "is picking up the phone as it rings",
        "has picked up an incoming call",
    )),
    "put_on_bag": _step("가방을 멘다", (
        "is putting on a backpack",
        "is slinging the bag over their shoulder",
        "has just shouldered their bag",
    ), done=("has put on their bag",)),

    # Everyday background: waking up.
    "sleep": _activity("자고 있다", (
        "asleep under the covers",
        "sleeping",
        "asleep, curled up under the blanket",
    )),
    "wake_slowly": _activity("침대 가장자리에 앉아 잠을 깬다", (
        "slowly waking up",
        "pausing for a moment, still sleepy",
        "looking half asleep",
    )),
    "make_bed": _activity("이불을 갠다", (
        "making the bed",
        "straightening the blanket on the bed",
        "folding the blanket and fixing the pillow",
    )),
    "lie_awake": _activity("잠에서 깨 누워 있다", (
        "awake under the covers",
        "awake with their eyes open",
        "awake and not yet getting up",
    )),
    "turn_off_alarm": _step("휴대폰 알람을 끈다", (
        "is turning off the alarm on their phone",
        "is reaching for the phone to stop the alarm",
        "has just switched off the phone alarm",
    )),
    "sit_up_in_bed": _step("침대에서 몸을 일으켜 앉는다", (
        "is sitting up in bed",
        "is pushing the covers back and sitting up in bed",
        "has just sat up in bed",
    )),
    "turn_on_room_light": _step("방 불을 켠다", (
        "is pressing the wall switch to turn on the room light",
        "is switching on the main room light",
        "has just turned on the room light at the wall switch",
    ), done=("has turned on the room light",)),
    "look_out_window": _activity("창밖을 본다", (
        "looking outside",
        "looking out at the street",
        "glancing out at the weather",
    )),
    "dry_hair": _activity("수건으로 머리를 말린다", (
        "drying their hair with a towel",
        "rubbing their wet hair with a towel",
        "drying their wet hair with a towel",
    )),
    "get_dressed": _activity("옷을 입는다", (
        "getting dressed",
        "putting on clothes for the day",
        "changing into day clothes",
    )),

    # Making breakfast.
    "walk_to_kitchen": _step("주방으로 간다", (
        "is walking to the kitchen",
        "is heading into the kitchen",
        "has walked over to the kitchen",
    )),
    "take_bowl": _step("찬장에서 그릇을 꺼낸다", (
        "is taking a bowl out of the cupboard",
        "is getting a bowl down from the cupboard",
        "has taken a bowl from the cupboard",
    )),
    "pour_cereal": _activity("그릇에 시리얼을 붓는다", (
        "pouring cereal into a bowl",
        "shaking cereal out of the box into a bowl",
        "filling a bowl with cereal",
    )),
    "take_milk": _step("냉장고에서 우유를 꺼낸다", (
        "is taking the milk out of the fridge",
        "has opened the fridge and is taking out the milk",
        "is getting the milk carton from the fridge",
    )),
    "pour_milk": _activity("시리얼에 우유를 붓는다", (
        "pouring milk over the cereal",
        "pouring milk into the bowl of cereal",
        "adding milk to the cereal",
    )),
    "put_milk_back": _step("우유를 냉장고에 다시 넣는다", (
        "is putting the milk carton into the fridge",
        "is returning the milk to the fridge",
        "has put the milk in the fridge and closed the door",
    )),
    "fill_cup_at_purifier": _step("정수기에서 컵에 물을 받는다", (
        "is filling a cup with water at the water purifier",
        "is standing at the water purifier filling a cup",
        "is holding a cup under the water purifier",
    )),
    "bring_breakfast": _step("시리얼과 물컵을 식탁으로 가져간다", (
        "is carrying the bowl of cereal and a cup of water to the dining table",
        "is bringing breakfast over to the dining table",
        "is walking to the table with the cereal and a cup of water",
    ), done=("has set the cereal and a cup of water on the table",)),
    "sit_at_table": _step("식탁에 앉는다", (
        "is sitting down at the dining table",
        "is pulling out a chair and sitting down at the table",
        "has just sat down at the table",
    ), done=("has sat down at the table",)),

    # Eating.
    "eat_cereal": _activity("시리얼을 먹는다", (
        "eating cereal with a spoon",
        "eating a spoonful of cereal",
        "having cereal for breakfast",
        "eating from the bowl of cereal",
    ), uses=("bowl",)),
    "drink_water": _activity("컵으로 물을 마신다", (
        "drinking water from a cup",
        "holding a cup to their mouth and drinking",
        "taking a sip of water from the cup",
    ), done=("has taken a sip of water and put the cup back down on the {surface}",), uses=("cup",)),
    "put_down_spoon": _step("숟가락을 내려놓는다", (
        "is putting the spoon down in the bowl",
        "is resting the spoon on the edge of the bowl",
        "has just set the spoon down",
    )),
    "pick_up_spoon": _step("숟가락을 든다", (
        "is picking up the spoon",
        "is taking the spoon in hand",
        "has picked up the spoon",
    )),
    "chew": _activity("씹는다", (
        "chewing a mouthful of cereal",
        "chewing slowly",
        "chewing and looking down at the bowl",
    )),
    "sit_idle_at_table": _activity("식탁에 앉아 잠깐 쉰다", (
        "doing nothing in particular",
        "resting for a moment after eating",
        "leaning back in the chair",
        "looking ahead idly",
    )),

    # Coffee and TV on the sofa.
    "go_to_sofa": _step("소파에 앉는다", (
        "is sitting down on the sofa",
        "is settling onto the sofa",
        "has just sat down on the sofa",
    )),
    "open_coffee_can": _step("캔 커피를 딴다", (
        "is opening the can of coffee",
        "is pulling the tab on the can of coffee",
        "has just cracked open the can of coffee",
    ), uses=("can",)),
    "drink_coffee": _activity("커피를 마신다", (
        "drinking coffee from the can",
        "taking a sip of coffee from the can",
        "holding the coffee can to their mouth and drinking",
    ), done=("has taken a sip of coffee and put the can back on the side table",), uses=("can",)),
    "pick_up_remote": _step("리모컨을 집는다", (
        "is picking up the TV remote",
        "is reaching for the remote control",
        "has picked up the remote",
    ), uses=("remote",)),
    "turn_on_tv": _step("TV를 켠다", (
        "is turning on the TV with the remote",
        "is switching the TV on",
        "has just turned on the TV",
    ), done=("has turned on the TV",), uses=("remote",)),
    "watch_tv": _activity("TV를 본다", (
        "watching TV",
        "watching the morning news on TV",
        "looking at the TV screen",
        "watching something on the TV",
    )),
    "change_channel": _step("채널을 바꾼다", (
        "is changing the TV channel with the remote",
        "is flipping through channels with the remote",
        "has just switched to another channel",
    ), uses=("remote",)),
    "adjust_cushion": _step("쿠션을 고쳐 놓는다", (
        "is adjusting a cushion behind their back",
        "is moving a sofa cushion to get comfortable",
        "has just straightened the cushion behind them",
    )),
    "check_time": _step("벽시계를 본다", (
        "is glancing at the clock on the wall",
        "is checking the time on the wall clock",
        "has just looked up at the clock",
    )),
    "talk_on_phone": _activity("통화한다", (
        "talking on the phone",
        "holding a phone to their ear and talking",
        "having a phone call",
    )),
    "turn_off_tv": _step("TV를 끈다", (
        "is turning off the TV with the remote",
        "is switching the TV off",
        "has just turned off the TV",
    ), done=("has turned off the TV",), uses=("remote",)),

    # Getting ready to leave.
    "walk_to_desk": _step("책상으로 간다", (
        "is walking over to the desk",
        "is heading to the desk",
        "has walked over to the desk",
    )),
    "pack_bag": _activity("노트북과 충전기를 가방에 넣는다", (
        "putting the laptop and its charger into a backpack",
        "packing a laptop into a backpack",
        "packing things into a backpack on the desk",
    ), uses=("laptop", "charger")),
    "zip_bag": _step("가방 지퍼를 닫는다", (
        "is zipping the backpack closed",
        "is pulling the zipper of the backpack shut",
        "has just zipped up the backpack",
    )),
    "put_on_jacket": _step("겉옷을 입는다", (
        "is putting on a jacket",
        "is pulling on a jacket and adjusting it",
        "is slipping their arms into a jacket",
    )),
    "check_pockets": _step("주머니를 확인한다", (
        "is checking their pockets",
        "is patting their pockets",
        "is feeling through their pockets for keys",
    )),
    "check_mirror": _step("거울을 보며 머리를 정리한다", (
        "is checking their hair in the mirror by the door",
        "is fixing their hair in the mirror",
        "is glancing at the mirror by the door",
    )),
    "leave_home": _step("현관으로 나간다", (
        "is walking out through the front door",
        "is leaving the home through the front door",
        "has opened the front door and is stepping out",
    )),

    # Moving about and small movements.
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
    "stretch": _activity("기지개를 켠다", (
        "stretching their arms overhead",
        "stretching their arms and rolling their shoulders",
        "leaning back and stretching",
    )),
    "yawn": _activity("하품한다", (
        "yawning",
        "yawning widely",
        "covering a yawn with one hand",
    )),
    "rub_eyes": _activity("눈을 비빈다", (
        "rubbing their eyes",
        "rubbing their face",
        "looking sleepy and rubbing their eyes",
    )),
    "look_around": _activity("주변을 둘러본다", (
        "looking around the room",
        "glancing around the room",
        "looking away toward the window",
    )),
    "shift_position": _activity("자세를 고쳐 앉는다", (
        "shifting their position",
        "adjusting how they sit",
        "shifting their weight on the seat",
    )),
    "unseen": _event("absent", "사람이 보이지 않는다", (
        "No person is visible in the room",
        "The person is not visible in the frame",
        "The room is empty and no person is in view",
    ), None, (), ()),
}
