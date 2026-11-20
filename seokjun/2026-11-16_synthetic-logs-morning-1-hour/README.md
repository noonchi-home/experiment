# Synthetic Logs, 1-Hour Mornings — Real AI with the Adoption Test (2026-11-16)

## Summary

I added the adoption test to PAM and ran a real AI on 1-hour mornings × 5 days. The test filtered out 10 weakly supported signals, and 3 of 6 robot tasks came out right. Late signals, where the person is already on the way to do the task, were passing; I blocked them by redefining the action time, which raised the result to 4 of 6 plus 1 half right.

## Why I ran this experiment

- PAM turns something it has seen on just one day straight into a rule. So I decided to filter the signal candidates the AI produces each night with an adoption test (a test that accepts a candidate as a rule only if the action follows the signal often enough and is unlikely to be chance).
- In the previous two experiments I put the answer key in the AI's place and checked only the calculation code. This time I wanted to run it with a real AI and see whether the test actually filters out weakly supported signals.
- The 16-hour daily logs needed a step not in the paper. I shortened each day to a 1-hour morning to match the paper's method, in which the AI reads the raw log directly.

## What I did

**Logs**

- 5 weekday mornings, 1 hour each (07:00–08:00), of a person living alone. One line every 2 seconds, so 1,800 lines per day. The style follows what the actual camera AI writes.
- Daily flow: wake up, wash, and get dressed → breakfast → coffee and TV on the sofa → getting ready to go out → out (not visible).
- For example, on day 1 from 07:02:40 to 07:02:58, the person sits on the edge of the bed → gets up (planted signal) → turns on the light → goes to the window → opens the curtains (the task the robot would take over). One motion spans several lines, and what was just done keeps being mentioned for a few more lines.

**The 6 planted habits**

| Robot task | Planted signal | What was planted in the log |
|---|---|---|
| Open the curtains | Got out of bed | Opens them within 1 minute of getting up. Only on day 2, opens them after washing up (habit with an occasional miss) |
| Cup into the dishwasher | Finished the water | 2–4 minutes later. All 5 days |
| Bowl into the dishwasher | Finished the cereal | 1.5–3 minutes later. All 5 days |
| Canned coffee next to the person | Finished the cereal | After putting the bowl and cup in, takes it out of the fridge and puts it on the side table by the sofa. 2–3.5 minutes after finishing |
| Empty can to its storage place | Finished the coffee | 1–2 minutes later, turns off the TV and puts it away. All 5 days |
| Turn off the room light | Put on the bag | Turns it off within 30 seconds and leaves. On days 3 and 5, turning it off is not visible |

**The 4 planted traps**

- A motion also done mid-meal: wiping the mouth. Done 1–2 times during the meal and once after finishing. Only the last one is followed by the bowl.
- Frequent event: checks the phone 2–3 times during breakfast.
- Coincidence in the first few days: a phone call. Only on days 1 and 2 does the person finish the coffee right after the call, so clearing the can happens to follow within 5 minutes.
- Part of the action: every action is preceded by a line of the person going to do it (e.g., walks toward the curtains).

**Nightly steps**

1. Self-reflection: the AI reads that day's raw log and outputs a rule table (FSM: a table that divides the day into stages and lists "signal → robot task" for each stage) and signal candidates.
2. Timestamp finding: the AI finds in the log the times when the candidates and actions occurred. Only times of lines that actually exist in the log are accepted.
3. Adoption test (code): recounts every day from day 1 to that day, and passes to the next day's robot only the signals that are followed by the action within 5 minutes at least 80% of the time with a chance probability (p-value) below 0.001.

I ran Experiment 1 (answer key in place of the AI) and Experiment 2 (real AI), which ran the 5 days with Qwen3.5-27B ($0.31).

## Results

Experiment 1: all 45 cells over 5 nights (9 candidates × 5 nights) came out as expected.

Experiment 2: rules the robot ended up using after night 5

| Robot task | Planted signal | Signals passing on night 5 | Verdict |
|---|---|---|---|
| Open the curtains | Got out of bed | Goes toward the curtains; walks over to the window | Wrong (only late signals remain) |
| Bowl into the dishwasher | Finished the cereal | Has finished the cereal (5 of 5) | Right |
| Cup into the dishwasher | Finished the water | Has finished the cereal (5 of 5) | Right (not the planted signal, but usable) |
| Canned coffee next to the person | Finished the cereal | None | Wrong (no rule made in all 5 days) |
| Empty can to its storage place | Finished the coffee | Finished the coffee and put the empty can down; watching TV on the sofa with the empty can nearby (5 of 5 each) | Right |
| Turn off the room light | Put on the bag | None | Wrong (passed on nights 2–4; the AI deleted it on night 5) |

- 3 of 6 were right (Experiment 1: all 6).
- Of the traps, the AI never picked checking the phone while eating or answering the phone as a candidate in all 5 days.

**Signals the test filtered out**

Of the signals that appeared from night 2 on, 10 never passed.

- Wiping the mouth → clearing the bowl and cup: 2 of 6 (33%) on night 2, and when picked again on night 5, 5 of 13 (38%), so it was blocked at the 80% bar. Without the test, the robot would come to clear the bowl every time the person wiped their mouth mid-meal.
- Sitting idly in front of the empty bowl: lines of sitting idly after finishing kept repeating, so it was 4 of 25 (16%) on night 4.
- Watching the news on the sofa with the empty can nearby: 1 of 1 (100%) on night 2, but its chance probability was 0.01, so it did not meet the threshold (0.001).
- Others: leaning back in the chair (3 of 4), checking the phone in front of the empty bowl (3 of 5), turning off the TV (4 of 6), putting on the backpack (2 of 3), coming back to the room and changing clothes (1 of 2 each), turning on the room's main light (2 of 3).

In Experiment 1, "answered the phone → clear the empty can" coincided by chance on days 1 and 2, so it passed on night 2 at 2 of 2, then dropped out on night 3 at 2 of 3.

## What I found digging into the results

The self-reflection AI writes out its own reasoning (thinking text) before giving its answer. I confirmed the causes of items 1 and 2 below from this text.

1. **Late signals passed.** "Goes toward the curtains" and "goes toward the switch" were followed by the action 2–4 seconds later every time, so they passed at 100%. But by then the person is already moving to do the task, so for the robot these are late signals. A statistical test cannot filter them out. On night 4, the thinking text even used passing the test as a reason to keep that signal.
2. **The AI moved or deleted rules based on a single day.** Seeing day 2, when the curtains were opened late, it moved the curtain rule to a different stage and dropped the real signal "got out of bed," which never came back. On day 5, when turning off the light was not visible, it deleted the light rule that had passed on nights 2–4. Two lines of the paper's prompt clashed: "the rule's action must be something the person did today" and "do not delete a rule just because it did not appear today."
3. **Timestamp finding counted one occurrence as several.** On day 3, the person rested once after finishing eating, but timestamp finding counted it again each time the rest was interrupted by wiping the mouth or checking the phone. As a result, the good signal "rests briefly after finishing" fell to 3 of 5 (60%) on night 3.
4. **The AI never made a rule for bringing the canned coffee in all 5 days.** It used the scene of taking the canned coffee out of the fridge and carrying it to the sofa only as a marker for moving to the next stage.

## After redefining the action time (2026-11-18)

- In the timestamp-finding prompt, I changed the action time from "the moment the task is done" to "the moment the person starts walking over to do it." The AI first finds the moment the task is done, then works backward from there to find the first line where the person starts walking over. That way, a motion that is already heading to do the task, like "goes toward the curtains," falls at the same moment as the action and cannot pass the test.
- I reran on the same 5-day logs (pass threshold 80%, $0.288).

| Robot task | Planted signal | Signals passing on night 5 | Verdict |
|---|---|---|---|
| Open the curtains | Got out of bed | Turned on the room's main light (4 of 5) | Half right (a signal before going to the window, but only 4 seconds before) |
| Bowl into the dishwasher | Finished the cereal | Rests briefly after finishing (5 of 5) | Right |
| Cup into the dishwasher | Finished the water | Put the empty cup down on the table; rests briefly after finishing (5 of 5 each) | Right |
| Canned coffee next to the person | Finished the cereal | Rests briefly after finishing; gathers the bowl and cup (4 of 5 each) | Right |
| Empty can to its storage place | Finished the coffee | Finished the coffee and put the empty can down; turned off the TV with the remote (5 of 5 each) | Right |
| Turn off the room light | Put on the bag | None | Wrong (the AI deleted the rule on night 5, for the same reason as item 2 above) |

- 4 of 6 were right and 1 was half right (the first run had 3).
- Signals of heading to do the task (walks over to the window, goes toward the switch, gets up from the sofa) failed every time they appeared.
- On night 4, the correct signal "is getting up from the bed" was at 3 of 4 (75%), but the AI dropped it because the prompt said "you may change it if it is below 80%." So I lowered both the pass threshold and this sentence to 75% (2026-11-18).

## Limitations and next steps

| Limitation | Next |
|---|---|
| The AI moved or deleted rules based on a single day (deleting the light rule on night 5) | Add an AI notebook where the reasoning is written down each night so the AI can pick it up the next night, and compare on the same 5 days |
| Timestamp finding counted the same moment several times | First group the log into activity chunks ("what the person is doing") (`2026-11-18_real-video-cup-clearing/`) |
| The log sentences were generated by code | Transcribe real videos into text and insert them (`2026-11-18_real-video-cup-clearing/`) |
| Each condition was run only once | Run several times to see how much results vary |

## Files

| Folder | Contents |
|---|---|
| `data/` | The 5 daily logs (`day1.txt`–`day5.txt`) and the answer key (`answer_key.json`: planted habits and traps, and expected results) |
| `code/` | Building the logs (`make_records.py`; event sentence list `vocabulary.py`), running the nightly calculation with the answer key (`free_run.py`, `free_steps.py`), tests (`test_*.py`) |
| `runs/free/` | Experiment 1 results |
| `runs/model/` | Experiment 2 results. For each night: the AI's rules (`reflector_fsm.json`), times found by the AI (`marks/`), test numbers (`check_results.json`), the rules that passed for the robot to use (`predictor_fsm.json`), and the text sent to the AI and its replies (`work/`) |
| `runs/model_start/` | Results after redefining the action time (same file layout) |

The log notes kept for each AI request (`input_reference.json`) contain folder paths on this computer, so they are not uploaded.
