# Synthetic Logs, 5 Weekdays — Rebuilding the Day So It Hangs Together (2026-11-15)

## Summary

I rebuilt 5 weekdays of a person living alone as consistent 16-hour logs. The calculation check run with the answer key matched expectations in all 60 cells. I ran the real AI only through the first night; because problems kept recurring with the 16-hour logs, I decided to shorten each day to a 1-hour morning.

## Why I ran this experiment

- The 7-day logs had lines that did not fit real life. The spoon was put down exactly once each evening, "eats" appeared after the meal was finished, and there were lines of drinking water from a cup that had already been cleared.
- The next step is an experiment where a real AI reads the logs. If the logs are unnatural and the AI gets something wrong, I cannot tell whether the log or the AI is to blame.
- So I rebuilt the day to be consistent, like real life, and rechecked the calculation and scoring code before running the real AI.

## What I did

**How the logs were built**

- 5 weekdays of a person living alone. Each day runs 07:00–23:00 with one line every 2 seconds, so 28,800 lines per day.
- I wrote each day in time order starting at 07:00, having the generator keep track of whether the cup has water in it, whether the person is holding the spoon or the chopsticks, whether the meal is finished, whether the light, desk lamp, and laptop are on, and whether a guest is over. So there are no lines of drinking from a cleared cup or eating again after finishing. I also added a separate check that looks for inconsistent lines once the logs are built.
- The sentences follow the style of the actual PAM prediction model (the AI that watches the video and describes the scene one sentence at a time). Each sentence covers posture, current activity, and nearby objects, and what was just done keeps being mentioned for a few more lines. Example: `07:00:00 | The person is lying in bed awake and stretching a little under the covers.`
- The day's flow: morning prep → breakfast → study → getting ready to go out → out (not visible) → evening rest → dinner → getting ready for bed. The overall order is the same every day; only the times shift by a few minutes.

**Real-world data I referred to**

- Toyota Smarthome (18 people aged 60–80 recorded continuously for 8 hours each in real homes): fine-grained actions such as drinking and eating overlap.
- CASAS Aruba (219 days recorded in the home of a person living alone): about 53% of the time is unlabeled, so much of the day is "nothing in particular."
- Following eating research (about 5 bites per minute), I had the person pick up and put down the spoon and chopsticks many times during a meal. For phone use, I referred to a study that observed 94 people for 5 days (an average of 76 times a day).

**Planted cases**

I planted the same 13 cases as in the 7-day logs, with the following changes.

- In "Two candidates pass together," the second signal changed from putting the spoon down to wiping the mouth with a napkin.
- The spoon is now put down many times during the meal, as in real life, and was moved to "Candidate repeated without action."
- "Action seen for the first time" changed from putting away the desk lamp to fetching a book, because if the lamp were put away it could not be turned on for reading that night.
- With 5 days, "Habit with an occasional miss" and "Action that is already frequent" are expected to pass on night 5.

**Two checks**

- **Experiment 1 (answer key in place of the AI, no cost).** I put the answer key's answers in place of the nightly AI steps and ran 5 nights.
- **Building the scoring code.** A real AI writes candidates in its own words, so they cannot be compared directly with the answer key. So I built two kinds of scoring.
  - Night scoring (`night_scoring.py`): matches the AI's candidate sentences to answer-key events and checks whether pass/fail matches expectations.
  - Day scoring (`day_scoring.py`): checks whether the robot helps correctly on the next day's log using that night's rules (the paper's method).
- **Experiment 2 (real AI, Qwen3.5-27B).** I ran only the first night.

## Results

- Experiment 1: 12 candidates × 5 nights = 60 cells, all matching the answer key's expectations.
- Running night scoring on the same results also gave "match" for all 60 cells. Running day scoring with a fake robot that simply answers with the answer key gave 100% on every day from 2 to 5. The scoring code also works as designed.
- Experiment 2: there is a record of running only through the first night. It produced 21 candidates, none of which passed. I did not write up the results.

## Limitations and next steps

- The 16-hour daily logs required inserting a step not in the paper, and problems kept recurring at that step. So I shortened the logs to a 1-hour morning × 5 days, matching the paper's method in which the AI reads the raw log directly (`2026-11-16_synthetic-logs-morning-1-hour/`).
- Weekends are not included. The figure of fetching drinks 7–9 times a day is an estimate, not from a study.

## Files

| Folder | Contents |
|---|---|
| `data/` | The 5 daily logs (`day1.txt`–`day5.txt`) and the answer key (`answer_key.json`) |
| `data_고치기전/` (before fixes), `data_중간판/` (intermediate version), `data_천장불/` (ceiling light) | Earlier versions kept while revising the logs |
| `code/` | Building the logs and answer key (`make_records.py`; event sentence list `vocabulary.py`), running the nightly calculation with the answer key (`free_run.py`, `free_steps.py`), night scoring (`night_scoring.py`), day scoring (`day_scoring.py`), tests (`test_*.py`) |
| `code/옛_밤코드_16시간/` (old night code, 16 hours) | A copy of the night-step code as of this point |
| `runs/free/` | Experiment 1 results and scoring results (`scoring/`) |
| `runs/free_고치기전/` (before fixes), `runs/free_중간판/` (intermediate version) | Experiment 1 results run on earlier log versions |
| `runs/model/night-1/` | Experiment 2 first-night results (including the text sent to the AI and its replies) |
