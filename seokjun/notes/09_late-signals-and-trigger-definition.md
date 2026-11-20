# 9. Late signals and the definition of a trigger (November 16–17)

## What was the problem

When I ran the 5 days of one-morning-hour synthetic logs with a real AI on November 16, motions in which the person had already started moving to do the task passed the adoption test as triggers (signals that start the robot's help).

| Robot task | Answer-key signal I planted | Signal that passed | Follow-through |
|---|---|---|---|
| Open the curtains | Gets out of bed | Heads to the curtains | 5 of 5 on the night of day 5 |
| Open the curtains | (same) | Walks up to the window | 4 of 4 on the night of day 5 |
| Turn off the room light | Slings the bag over the shoulder | Heads toward the switch by the door | 100% every night, days 2–4 |

- These motions led to the task 2–4 seconds later every time, so their follow-through rate is 100%. The adoption test (Note 8) only asks "does the task follow the signal?" So in the test's eyes they look like the most reliable signals of all. They are not chance but the beginning of the task itself, so the chance probability (p-value) does not filter them out either.
- For the robot they are late signals. If the robot sets off when the person is already heading to the curtains, it cannot help first.
- Only late signals remained in the curtain rule. After seeing day 2, when the curtains were opened late, the AI moved the rule to a different stage and dropped the answer-key signal "gets out of bed," which never came back.
- On the night of day 4, the AI's reasoning text (the text it writes to think things through before answering) said it would keep "heads to the curtains" because it passed the check, and drop the candidates that failed. Passing the check was used as the reason to keep a late signal.

## How I thought about it

### The definition of a trigger

A trigger must appear before the person starts moving to do the task. This is not a new principle; it already existed.

- PAM paper, main text: the signal must appear before the person starts the task. The paper tries to enforce this through the prompt for self-reflection (the step where, after the day ends, the AI revises the rule table from that day's log): "use only signals the person would show even if the robot helps," and "it cannot be a signal that the person is going to get something."
- November 9 design (Note 5): "If the robot does this task instead, does this event still happen?" If not, it is part of the task. The person has already started moving, so the robot is late, and if the robot does the task instead, the person never makes that motion and the trigger itself disappears.

"Walking to the window" is not a trigger, because the person is already moving toward the curtains. "Gets out of bed" is a moment when where the person will go has not been decided yet, so it can be a trigger. In fact, on day 2 the person got up and went to wash first.

The problem was that the principle was in the prompt yet was not followed, and the check cannot see this.

### Approaches considered

| Approach | Outcome | Problem |
|---|---|---|
| State the principle more clearly in the self-reflection prompt | Listed as a next step; not in the current prompt | The paper's prompt already has sentences with the same meaning, yet late signals still appeared |
| Add a condition to the check code: "the signal must come at least N seconds (e.g., 10 seconds) before the action" | Not chosen | There is no basis for the number of seconds. The November 9 design already said "do not define this relationship as a fixed number of seconds." The approach below filtered out late signals, so this became unnecessary |
| Reject a candidate if it is a preparatory motion physically required for the task | Not chosen | Opening the curtains requires getting out of bed, so even the answer-key "gets out of bed" would be rejected. The question to ask is not "is it required?" but "is the person already moving to do the task?" |
| Redefine the action time as "the moment the person starts walking to do the task" | Chosen | The check formula stays the same; only the reference point for counting changes |

### The redefined action time

The curtain scene from the day 1 log (quoted from the original English log):

```
07:02:44 | The person is getting out of bed.                                          ← planted answer-key signal
07:02:48 | The person is pressing the wall switch to turn on the room light.
07:02:50 | The person has just turned on the room light at the wall switch.
07:02:52 | The person has walked up to the window.                                    ← late signal
07:02:54 | The person is drawing the curtains open to let the light in.
07:02:58 | The person has opened the curtains, and is now glancing out at the weather.
```

- **Before.** The time-marking AI (the step that finds at what time in the log the candidates and actions occurred) recorded the moment the person accomplished the task as the action time. Then "has walked up to the window" at 07:02:52 is counted as a signal that precedes the action.
- **After.** The AI first finds the moment the task was accomplished, then goes back up the log one line at a time and records as the action time the first line where the person started walking toward that object or place. That line does not have to name the object (walking toward the flowerpot before watering it). In this scene, 07:02:52 becomes the action time.
- Reaching and grasping are not included; only starting to walk counts as the start (decided November 17).
- This way, a motion of going to do the task falls at the same moment as the action and cannot satisfy "the action follows the signal." The check code was not changed.

## How far it got

I reran the same 5-day log (pass threshold 80%, $0.288; the results were appended to the experiment README on November 18).

| Robot task | Answer-key signal | First run (night of day 5) | Rerun (night of day 5) |
|---|---|---|---|
| Open the curtains | Gets out of bed | ✗ Heads to the curtains, walks up to the window | △ Switches on the main room light (4 of 5). Before heading to the window, but only 4 seconds earlier |
| Bowl into the dishwasher | Finishes the cereal | ✓ | ✓ Rests briefly after eating (5 of 5) |
| Cup into the dishwasher | Finishes the water | ✓ | ✓ Sets the empty cup down on the table; rests briefly after eating (5 of 5) |
| Can of coffee next to the person | Finishes the cereal | ✗ No rule | ✓ Rests briefly after eating; gathers the bowl and cup (4 of 5) |
| Empty can to the storage spot | Finishes the coffee | ✓ | ✓ Sets the empty can down; turns off the TV with the remote (5 of 5) |
| Turn off the room light | Slings the bag over the shoulder | ✗ The AI deleted the rule on the night of day 5 | ✗ Same reason |

- The result went from 3 of 6 to 4, plus 1 half-correct.
- In the rerun, the going-to motions that appeared as candidates (walks up to the window, heads toward the switch by the door, gets up from the sofa) were all counted as never followed and failed. "Heads to the curtains" did not appear as a candidate this time.
- On the night of day 4, the answer-key signal "is getting up from the bed" stood at 3 of 4 (75%), but the AI discarded it. This led me to lower the pass threshold to 75% (Note 8).

## Open questions

- **The light-off rule was deleted on the night of day 5.** After seeing day 5, when the person left without turning off the light, the AI deleted a rule that had passed on the nights of days 2–4. Two lines of the paper's prompt ("the rule's action must be something the person did today" and "do not delete a rule just because it did not appear today") conflicted, and the AI followed the first. This has the same root as dropping the answer-key signal from the curtain rule. The check looks at all days so far, but the AI that revises the rules judges from that single day.
- **How many seconds ahead is enough?** "Switches on the main room light" is a signal that comes before heading to the window, but only 4 seconds before the action. How many seconds the robot needs to get moving has to be measured with a real robot and real video.
- **Time marking counted one occurrence as several.** On day 3 of the first run, a single rest after eating was counted again each time the rest was interrupted by wiping the mouth or looking at the phone (07:27:46, 07:28:38, 07:29:00). So the good signal "rests briefly after eating" dropped to 3 of 5 (60%) on the night of day 3. This problem led to activity chunks (Note 10).
- These results come from a single synthetic log, with each setting run once (Note 11).

## Related

- Experiment folder: `2026-11-16_synthetic-logs-morning-1-hour/` (first run in `runs/model`, rerun in `runs/model_start`)
- Note 5 (Appliance signals and trigger finding): the "does this event happen even if the robot does it instead?" criterion
- Note 8 (Adoption criteria): what the check sees and what it cannot see; the 75% adjustment
- Note 10 (Activity chunks): the problem of counting the same moment many times

## Sources

- `seokjun/2026-11-16_synthetic-logs-morning-1-hour/README.md` ("Remaining problems and causes," "2026-11-18 addendum")
- `seokjun/2026-11-16_synthetic-logs-morning-1-hour/runs/model/night-1`–`night-5/check_results.json` (check numbers for the first run)
- `seokjun/2026-11-16_synthetic-logs-morning-1-hour/runs/model_start/night-1`–`night-5/check_results.json`, `night-5/predictor_fsm.json` (the rerun)
- `seokjun/prompts/text/marking.txt` (time-marking prompt), `seokjun/prompts/text/README.md` ("Finding tasks" item)
- `seokjun/prompts/text/reflector_text_update.txt` (self-reflection prompt, from day 2 on)
- `seokjun/notes/sources/설계문서/2026-11-09_가전_관찰에서_도움_규칙_만들기.md` line 45 (making help rules from appliance observations: do not define it as a fixed number of seconds)
- `seokjun/notes/sources/설계문서/2026-11-14_트리거_채택기준_80퍼센트와_p-value.md` section 2 (trigger adoption criteria, 80% and p-value: part of an action cannot be a trigger)
