# Appliance Signals Over Four Weeks — Can Rules Learned Overnight Help the Next Day? (2026-11-10)

## Summary

To test an approach where help rules are saved overnight from appliance signals and then used the next day to decide whether to execute, wait, or cancel, I built a simulated 28-day log for one person (861 appliance signals, 86,995 observation lines at 4-second intervals) and an expected answer key for the evaluator only (980 nightly-rule rows, 646 daytime decisions). I did not run any AI model on it.

## Why I did this

- I designed a flow in which, during the day, the person's actual actions are recorded; at night, the tasks among them that the robot could take on, and their start conditions, are saved as rules; and the next day, those rules are used to decide whether to **execute, wait, or cancel**. I needed material to test this flow from start to finish.
- I decided to use appliance signals as triggers (the signals at which the robot starts helping). For signals the machine reports (wash finished, etc.), I look at what follows. For signals from a person operating an appliance (opening the fridge door, etc.), I look at what comes before and after.
- The question for deciding whether something is a trigger was: "If the robot did this task instead, would this event still happen?" Even if the robot moves the laundry, the wash-finished chime still sounds, so it can be a trigger. A fridge door that a person opened while going to get a drink is part of fetching the drink, so it cannot be a trigger.
- I set the first criteria for adopting a rule.
  - Rules without conditions: they match on 4 or more different days, and the rate of acting in that situation is 80% or higher.
  - Rules with a condition such as day of the week or weather: in addition to the two above, the rate is at least 20 percentage points higher than without the condition, and the p-value of a one-sided binomial test (the chance probability of this result) is below 0.001.

## What I built

### Simulated 28-day log (input for the model)

| Item | Value |
|---|---|
| Period | 2026-10-12 (Mon) to 11-08 (Sun), 28 days |
| Appliance signals | 861 (714 operated by a person, 147 reported by a machine) |
| Observations | 86,995 lines, 4-second intervals |
| Other | Hourly weather, indoor temperature reported by the air conditioner every 30 minutes |

- The observations are what a CLOiD robot (LG's home robot) following the person saw, written one line each as "time / location / what was seen." The weather and sensor values were all synthesized too.
- Observations exist only around appliance signals: for machine signals, from that moment to 10 minutes after (151 time points); for signals from a person operating an appliance, from 10 minutes before to 10 minutes after (301 time points). There is no camera record outside those windows.
- Each date folder holds one day. Rules built by the first night are applied from the next day on.
- I also included rare events, such as guest visits and a one-time plant repotting.

### Expected answer key (evaluator only)

Only the evaluator sees the answer key. The model is given only the per-date input folders, one day at a time.

I defined 35 rule and observation candidates and recalculated them every night using the records up to that day. 35 × 28 days = 980 rows.

| Candidate type | Count | Meaning |
|---|---:|---|
| Habit | 24 | Becomes a rule only if it passes the adoption criteria |
| Observation only | 7 | Robot help is not scored; only whether the person does it is tracked (making the bed, drying hair, etc.) |
| Device-required | 1 | One step must come before the other because of how the device works, so it is adopted after being seen once (taking out the laundry after the wash finishes) |
| Fixed safety | 3 | Rules applied from the start (closing the fridge door on a door-open alert, etc.). Excluded from the count of learned habits |

I linked the 646 decisions that the nightly rules should produce the next day to their original timestamps and observation line numbers.

| Decision | Meaning | Count |
|---|---|---:|
| Execute | The required checks are done; start the command | 65 |
| Wait | Something about safety, stock, or the target's state still needs checking | 129 |
| Cancel | The person already started, or the task is no longer needed | 129 |
| Don't step in | No grounds to start a new rule at that time | 323 |

- Occurrences of the same start event are grouped into one opportunity covering 60 minutes from the first one. I checked whether the action started within 30 minutes, and excluded "already done" and "not observable" from the rate.
- The conditions that can be used are: day of the week, type of day, one-hour time slot, the robot's observation location, whether it is raining, TV channel, a visitor in the last 30 minutes, and indoor temperature in 2-degree bands.
- I also built a tool that compares actual results with the answer key once they are fed in.

## Results

I did not run any AI model. There are no real-robot results either. This folder holds only the logs and the answer key.

I checked two things about the answer key itself.

- With no future date folders present, I added one day at a time and recalculated 28 times, and the results matched the answer key. This confirms that the answer key does not use records from after each day.
- When I fed deliberately wrong decisions into the comparison tool, it caught them.

Nights on which a rule was newly adopted or changed in the answer key

| Night | Rules newly adopted or changed |
|---|---|
| 10-14 | Take out the laundry after the wash finishes |
| 10-16 | 7 rules, including preparing a cup of water after the pill box is put on the dining table, and putting the laptop in the bag when going out in the morning |
| 10-17 | Start the wash after the dinner dishes are loaded |
| 10-20 | Pack the charger after the laptop goes in |
| 10-21 | Turn on the reading lamp when sitting down with a paper book, and turn it off when the book is closed |
| 10-25 | Prepare water after the workout timer ends |
| 11-04 | Beer after a channel is selected |
| 11-07 | Start the dryer once laundry is in it |
| 11-08 | Beer after the TV turns on |

The other nights have no changes.

## What I found while building the answer key

1. **The same fridge alert can lead to different decisions.** In the earlier two-scene fridge test (11-08), the model built the rule "close the door when the alert sounds." The answer key contains scenes where the decision differs for the same alert.

   | Time | Expected decision | Reason |
   |---|---|---|
   | 10-18 12:31:56 | Wait | A person's hand is inside, on a fridge shelf. At 12:32:20 the person closes it themselves, so cancel |
   | 10-23 12:29:28 | Wait | A paper bag blocks the view in front of the door, so there is no evidence that no one is there. At 12:30:00 the door closes, so cancel |
   | 10-25 12:29:36 | Execute | At the moment of the alert, the space in front of the open door is empty and the user is over by the dining table |

2. **The chance check was strict.** Of the 8 times the laundry was taken out, on all 4 rainy occasions it was moved to the dryer, but the p-value was 0.0625, so the condition "use the dryer when it rains" was not adopted.
3. **Sports channel and beer first passed on the night of November 4.** Under the channel 37 condition, beer was brought 4 times out of 4, while the overall base rate was 5 out of 29. The p-value was about 0.000884.
4. **Conditions can also match by chance.** On the last night, the condition "turns on the TV in the 21:00 hour on a weekday" also passed the criteria for the beer rule. Whether it explains this person's preference has to be checked separately on new dates.
5. **Matching the answer key does not prove the robot actually helped.** There are 3 points where the rule says execute but, in the actual log, the person did not do the task. All are starting the dishwasher (10-19 19:47:44, 10-31 18:50:08, 11-06 19:12:40).
6. **Looking only 10 minutes past a signal is too short to conclude "not done."** On October 28, the person opened the washer door 12 min 16 s after the wash finished. This action is observed again around the door-opening signal from the person that followed.

## Limitations and next steps

- I did not run an AI model. None of the steps (interpreting observations, saving rules, next-day decisions) was actually tested.
- Both the logs and the answer key are synthetic. The answer key was assigned only within the 35 predefined candidates and the condition list.
- Only things the person did themselves are included. Users accepting or undoing the robot's help would have to be simulated separately.
- The last night's (11-08) rules have no next-day decisions assigned, because there is no day-29 log.

After this I narrowed the research scope to habit judgment (the adoption test). The November 14 implementation plan replaced the November 9 implementation plan, which centered on appliance signals, and no model was run on this data.

## Files

**Logs (input).** In `seokjun/2026-11-10_appliance-signals-4-weeks/input/`.

| Folder / file | Contents |
|---|---|
| `일별입력/<날짜>/` (daily input/<date>) | 28 daily inputs. Each folder has the four files below |
| `가전신호.jsonl` (appliance signals) | Time, who operated it (person / machine), device, and the changed item and value. One event per line |
| `관찰.txt` (observations) | Time / robot location / what was seen. One line every 4 seconds |
| `weather.json` | Synthetic weather and outdoor temperature on the hour |
| `실내온도.jsonl` (indoor temperature) | Indoor temperature reported by the air conditioner every 30 minutes |
| `시작안내.md` (getting started) | How to feed in one day at a time, and a scene table by date. The table also lists events after each day, so it is not used as model input |
| `하루읽기.py` (read one day) | A tool that reads one day in time order and prints it. Does not call the learner |
| `검토용/` (for review) | Observation windows for each signal and settings for each date. Also lists events after each day, so it is not used as model input |
| `생성도구/` (generation tools) | Code that generated the logs, and code that re-reads all 28 days to check them (`verify.py`) |

**Expected answer key (evaluator only).** In `seokjun/2026-11-10_appliance-signals-4-weeks/answer-key/`. Never mixed into model input.

| Folder / file | Contents |
|---|---|
| `예상정답_읽는법.md` (how to read the expected answer key) | The criteria used for the answer key, and a summary by date |
| `규칙목록.md` (rule list) | Name, start event, robot action, and type for each of the 35 candidates |
| `날짜별/` (by date) | For each date, the rules learned up to that night and the next day's decisions (28) |
| `채점자료/밤별규칙.jsonl` (scoring data / rules per night) | Rule status and condition checks for each night (980 rows) |
| `채점자료/시각별판단.jsonl` (scoring data / decisions by time) | Daytime decisions matched against actual actions (646 rows) |
| `채점자료/원본근거와기회.jsonl` (scoring data / source evidence and opportunities) | The source text and observation line numbers for the 522 cases before grouping into opportunities |
| `채점자료/전체신호색인.jsonl` (scoring data / full signal index) | The full list of all 861 appliance signals |
| `채점자료/원본지문.jsonl` (scoring data / source fingerprints) | Values for checking that the original input files have not changed |
| `결과대조.py` (result comparison) | Tool that compares actual nightly rules and daytime decisions with the answer key |
| `도구/` (tools) | Code that built and checked the answer key |
