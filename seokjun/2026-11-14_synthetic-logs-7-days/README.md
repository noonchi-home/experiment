# Synthetic Logs, 7 Days — Checking the Adoption Test Calculation Code (2026-11-14)

## Summary

Without running the AI, I put the answer key in the AI's place and checked that the counting, 80%, and p-value code runs as designed. All 84 cells checked over 7 nights matched the answer key's expectations. However, the logs did not resemble real life, so I stopped using them and rebuilt the logs as 5 weekdays.

## Why I ran this experiment

- PAM turns something it has seen on just one day straight into a rule. So I decided to filter the signal candidates produced by nightly self-reflection (the AI step that reviews the day's log and creates or updates rules) with an adoption test (a test that accepts a candidate as a rule only if the action follows the signal often enough and is unlikely to be chance).
- Before running it with a real AI, I wanted to check separately that the calculation code is correct. If the AI and the code are both wrong, I cannot tell which one is to blame.
- So in place of the nightly AI steps (creating rules and signal candidates, and finding the times when candidates and actions occurred), I plugged in the answers from the answer key. If a result differs from what is expected, the code is at fault.

## What I did

**Logs**

- 7 days of fake text logs. Each day runs 07:00–23:00 with one line every 2 seconds, so 28,800 lines per day.
- Each line is just "time | English sentence." Example: `07:00:00 | The person gets dressed.`
- The same event is written with varied wording: for each event, one of 3 English sentences is picked.
- I split the day into 8 stages: morning prep, breakfast, study, getting ready to go out, out (not visible), evening rest, dinner, getting ready for bed. Stage names are not written in the log.
- The answer key (`data/answer_key.json`) records which ones are real habits, when events actually happened, and on which night each should pass. It is not part of the AI's input.

**The 13 planted cases**

| Case | What was planted in the log | Real habit? |
|---|---|---|
| Daily habit | [Breakfast] Every day at 07:50, finishes the water and 3 minutes later puts the cup in the dishwasher | Yes |
| Same event, different state | In [Study] too, finishes the water every day at 10:15 but leaves the cup where it is | Yes (only in [Breakfast]) |
| Habit with an occasional miss | [Getting ready for bed] Closes the book and turns off the desk lamp. Only on day 2, turns it off 30 minutes later | Yes |
| Two candidates pass together | [Dinner] Finishes eating, puts the spoon down 1 minute later, and puts the bowl in the dishwasher 2 minutes after that | Yes (both) |
| Frequent event | Checks the phone more than 15 times a day. In [Breakfast], checks it 3 times every day, and only the last one is within 5 minutes of putting the cup away | No |
| Coincidence in the first few days | A phone call comes every day at 17:40. Only on days 1 and 2, the person happens to fetch a can 2 minutes later | No (a weakness of the criteria) |
| Done about half the time | Only on days 1, 3, 5, and 7, closes the laptop and 2 minutes later puts the book in its storage place | No |
| Concentrated on one day | Only on day 4, a guest finishes a can 3 times, and each time the can is put in its storage place 2 minutes later | No (a weakness of the criteria) |
| Action seen for the first time | Only on day 6, 2 minutes after turning off the vacuum, puts the desk lamp in its storage place | Unknown |
| Action that is already frequent | Brings a cup over to themselves in about 21% of 5-minute slots anyway. After sitting down at the desk, brings it 3 minutes later on every day except day 3 | Yes |
| Not observed | [Getting ready to go out] Puts on the bag and turns off the room light. On days 3 and 5, turning it off is not visible | Yes |
| Candidate repeated without action | Every evening, puts the chopsticks down and picks them up again three times. All three are within 5 minutes of putting the bowl away | No |
| Part of the action | Every action is preceded by a line of the person going to do it (e.g., picks up the empty cup) | No |

**How counting works and the pass criteria**

- Each night, everything is recounted over the whole log from day 1 to that day.
- If the action comes within 5 minutes after the signal, it counts as "followed." If the same signal appears again before the action, the earlier one is not counted; only the last signal right before the action counts.
- If the person was not visible during the 5 minutes after the signal, that occurrence is not counted.
- Pass: the follow-through rate must be at least 80%, and the chance probability (p-value: the probability of the action following this often if it happened at its usual rate regardless of the signal) must be below 0.001. If the usual rate is below 1%, it is raised to 1%. As a result, a candidate must be seen at least twice to pass.
- Only signals that pass go into the rules given to the robot for the next day.

## Results

7 nights × 12 candidates = 84 cells, all matching the answer key's expectations.

| Case | Signal → robot task | Times followed as of night 7 | Nights passed |
|---|---|---|---|
| Daily habit | Finished the water → cup into the dishwasher | 7 of 7 | Nights 2–7 |
| Habit with an occasional miss | Closed the book → turn off the desk lamp | 6 of 7 | Nights 5–7 |
| Two candidates pass together | Finished eating / put the spoon down → bowl into the dishwasher | 7 of 7 each | Nights 2–7 |
| Frequent event | Checked the phone → cup into the dishwasher | 7 of 21 | None |
| Coincidence in the first few days | Phone call came → can next to the person | 2 of 7 | Night 2 only |
| Done about half the time | Closed the laptop → book to its storage place | 4 of 7 | None |
| Concentrated on one day | Guest finished a can → can to its storage place | 3 of 3 | Nights 4–7 |
| Action seen for the first time | Finished vacuuming → desk lamp to its storage place | 1 of 1 | None |
| Action that is already frequent | Sat down at the desk → cup next to the person | 6 of 7 | Night 7 only |
| Not observed | Put on the bag → turn off the room light | 5 of 5 (2 unobserved left out) | Nights 2–7 |
| Candidate repeated without action | Put the chopsticks down → bowl into the dishwasher | 7 of 21 | None |

- "Same event, different state" and "Part of the action" are judgments the AI makes, so they cannot be checked this way. These two will be checked in the real-AI experiment.

## What I found digging into the results

1. **The p-value filtered out the "action that is already frequent."** Bringing a cup after sitting down at the desk was 2 of 2 (100%) on night 2, but because the person brings a cup in about 21% of 5-minute slots anyway, the chance probability was 0.042, above the threshold. On night 6, 5 of 6 (83%) still failed at 0.0018, and on night 7, 6 of 7 passed at 0.00044.
2. **Counting only the last signal filtered out a repeated motion.** The chopsticks were put down three times every day, all within 5 minutes of putting the bowl away, but only the last one counted, so the candidate stayed at 7 of 21 (33%) on night 7 and failed throughout. If all three had counted, it would have passed on the very first night.
3. **Leaving out unobserved occurrences kept the habit.** On days 3 and 5, turning off the light after putting on the bag was not visible. Because those two were not counted, the candidate stayed at 5 of 5 and kept passing.
4. **The two weaknesses of the criteria showed up exactly as expected.** Fetching a can after a phone call passed on night 2 at 2 of 2, then dropped out on night 3 at 2 of 3. Clearing the guest's cans passed on the strength of 3 occurrences on day 4 alone and stayed until the end. The calculation follows the design, but these are not real habits.

## Limitations and next steps

| Limitation | Next |
|---|---|
| I did not run the AI. I only confirmed that the calculation code is correct | Run with a real AI, one day at a time |
| The logs did not match real life. The spoon was put down exactly once each evening (18:59), "eats dinner" appeared even after the meal was finished, and "drinks water" appeared even after the cup had been cleared | Rebuild the day in time order so that it is consistent |

The calculation check had no problems, but if a real AI read these logs and got something wrong, I could not tell whether the log or the AI was to blame. So I rebuilt the logs as 5 weekdays of a person living alone (`2026-11-15_synthetic-logs-5-weekdays/`).

## Files

| Folder | Contents |
|---|---|
| `data/` | The 7 daily logs (`day1.txt`–`day7.txt`) and the answer key (`answer_key.json`) |
| `code/` | Building the logs and answer key (`make_records.py`; event sentence list `vocabulary.py`), running the nightly calculation with the answer key (`free_run.py`, `free_steps.py`), code that matches AI-written candidates to answer-key events (`night_scoring.py`, not run in this folder), tests (`test_*.py`) |
| `runs/free/` | Results of the 7 nights run with the answer key: per-night test numbers for each candidate (`check_results.json`), the rules to give the robot the next day (`predictor_fsm.json`), and more |
