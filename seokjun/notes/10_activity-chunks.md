# 10. Counting the same moment only once — activity chunks (November 18)

## What was the problem

The daily logs in the November 18 experiment have one line per second. I took four real videos, recorded by teammate Junhyeong Kim at my request, transcribed by AI at one line per second, then reviewed and finalized by hand, and appended them after synthetic scenes written in the same style (eating a meal, a can of coffee), building 4 days of logs at about 5 minutes per day (277–298 lines). Running the night step (self-reflection → time marking → adoption test) on these logs for 4 days exposed two problems. Self-reflection is the step where, after the day ends, the AI revises the rule table from that day's log; time marking is the step where the AI finds at what time in the log the trigger (signal that starts the robot's help) candidates and the actions occurred.

### The same moment was counted several times

A one-second log keeps describing what was just done for several more lines. The day 3 log (synthetic part), quoted from the original English log:

```
20:02:37 | The person has finished the coffee and set the empty can down on the desk.
20:02:38 | The person is seated at the desk, working on a laptop, with a glass of water on the table.
20:02:39 | The person is sitting at the desk using a laptop, while an empty can and a glass of water sit to their left.
20:02:40 | The person has finished the coffee and set the empty can down on the desk, and is now using a laptop.
20:02:41 | The person has finished drinking from the can, placed the empty can on the desk, and is now typing on a laptop, with a glass of water nearby.
```

- Setting the empty can down happened once, at 20:02:37. But the time-marking AI recorded the candidate "sets the empty can down on the desk" three times, at 20:02:37, 20:02:40, and 20:02:41, and recorded the clear-the-empty-can action at 20:02:54.
- The adoption test counts only the last candidate right before the action as "followed" (Note 8). So the first two became "not followed."
- This answer-key signal passed at 2 of 2 on the night of day 2, dropped to 3 of 5 (60%) on the night of day 3, and disappeared from the candidates on the night of day 4.
- The time-marking prompt already said "a line that restates what was just done refers to that earlier moment, so do not count it again" and "if the same candidate reappears within 10 seconds, count it once." Even so, the AI recorded it three times within 4 seconds.

### Candidates saying the same thing in different words were counted separately

On the night of day 4, the three candidates for the clear-the-empty-can rule were nearly the same scene.

| Candidate | Follow-through |
|---|---|
| Sitting at the desk with an empty can on the desk | 4 of 18 |
| Typing on a laptop with an empty can on the desk | 4 of 7 |
| Working on a laptop with an empty can on the desk | 4 of 16 |

- While the same state continued, each line was counted as a new occurrence, which inflated the counts, and the three candidates split the same evidence among themselves. All three failed.

## How I thought about it

- **Considered but not chosen: merging times within 10 seconds of each other in code after receiving them.** It costs nothing and works right away. But it looks only at time, not at meaning. Restating lines that come more than 10 seconds later, and long-lasting state candidates such as "typing with the empty can nearby," would still be split into several occurrences.
- **Chosen: first send the whole day's log to the AI to turn it into activity chunks, then run the night step.** While reading the log, if the person is doing the same thing it is one chunk; when they start something else, a new chunk begins. Grouping is by meaning, not by time.
- Rules in the chunking prompt (`chunking.txt`):
  - Consecutive lines describing the same activity form one chunk, even if the wording differs.
  - Short actions such as picking up, putting down, standing up, sitting down, taking a sip, and finishing become separate chunks even if they are a single line. Different activities are not folded into one chunk.
  - A line restating what was just done goes into the chunk of the current activity.
  - Each chunk is written as one short sentence describing the activity and the surrounding objects that matter for it (something just emptied, something just put down).
- The night-step prompt files are left unchanged; the code only swaps the one sentence that describes the log for "one line per activity chunk."
- **This is a step not in the PAM paper.** Up to the November 16 experiment, the AI read the raw log directly and made rules, as in the paper.

## How far it got

### Chunks

- Each day's 277–298 lines became 38–48 chunks (cost $0.020).
- The key moments in the answer key (finished eating, picked up the bowl, finished the coffee, picked up the empty can, put down the empty glass, picked up the glass, returned empty-handed) all matched chunk boundaries, either exactly or within 1 second.
- The day 3 scene above became two chunks. All the restating lines went into the second chunk.

```
20:02:34 ~ 20:02:36 | Drinking from a can of coffee while using a laptop.
20:02:37 ~ 20:02:53 | Typing on a laptop with an empty coffee can and glass of water on the desk.
```

### Results (robot rules on the night of day 4)

| Robot task | Answer-key signal | Without chunks | With chunks |
|---|---|---|---|
| Bowl into the dishwasher | Finished eating | ✓ Has finished eating and an empty bowl is there (4 of 4) | ✓ Takes the last spoonful (4/4); sits with both hands resting after finishing (3/3) |
| Empty can to the storage spot | Finished the coffee | ✗ The same moment was counted many times, and all failed (4/18, 4/7, 4/16) | ✓ Sets the empty coffee can down on the desk (3/3); types on the laptop with the empty can nearby (3/4) |
| Cup into the dishwasher (real-video part) | Finished the water | ✓ Types with the empty glass nearby (4/5) | ✓ Types on the laptop with the empty glass mug nearby (4/4) |
| Can next to the person (bringing coffee) | Finished eating | ✗ No rule | ✗ A rule exists, but the time-marking AI never found the action |

- Robot tasks learned rose from 2 of 4 to 3.
- Candidates the check blocked in the chunked run: looking at the phone with an empty bowl or an empty glass nearby (1 of 1 each; they appeared on only one day, so the chance probability blocked them), and returning to the desk empty-handed → clear the cup (1 of 5).
- The check's reference time was 1 minute and the pass threshold 75%. Since a day lasted 5 minutes, a 5-minute reference would have made every event in a day count as "followed."
- The night step cost $0.083 without chunks and $0.066 with chunks.

### The final product (noonchi)

It went into habit learning in the README of the final product (noonchi). Once a day, that day's log is grouped into activity chunks, and PAM self-reflection proposes a candidate rule table. The candidates go through a code check (format) and an AI check (meaning), and then the adoption test. If the task was done within 300 seconds (5 minutes) of the signal at least 75% of the time and the chance probability is below 0.1%, the candidate goes into the next day's rule table. Before the cup-clearing habit is learned, the robot asks whether to clear; after it is learned, it clears cups confirmed to be empty without asking.

## Open questions

- **Candidates saying the same thing in different words are still counted separately.** Even after chunking, two similar candidates remained for the empty-can rule (sets it down, 3/3; types with it nearby, 3/4). Self-reflection is not allowed to change the wording of existing candidates (a change would make it a new candidate that searches past dates again), so it does not merge similar candidates on its own.
- **Bringing coffee.** The log contains "sits down at the desk and puts the can of coffee on the desk," but on all four days the time-marking AI did not treat this as "place the can next to the person." I suspect this is because the scene of taking out the can is off-screen. Time marking runs with reasoning turned off, so there is no record of why.
- **If chunking goes wrong, everything after it is thrown off.** It amounts to adding one more step that is not in the paper. This time every key moment matched a boundary, but that was observed on 5 minutes a day × 4 days; whether it holds for full-day logs was not checked.
- **It is a small test.** Four videos, 5 minutes a day, and most of each day is synthetic log. Each method was run only once.

## Related

- Experiment folder: `2026-11-18_real-video-cup-clearing/`
- Note 8 (Adoption criteria): the counting rule "count only the last candidate." When the same moment is recorded many times, this rule makes the answer-key signal fail
- Note 9 (Late signals): the first case of time marking counting one occurrence as several ("rests briefly after eating," 3 of 5)
- Note 11 (Open questions): counting same-meaning candidates as one; running several times to see the variation

## Sources

- `seokjun/2026-11-18_real-video-cup-clearing/README.md`
- `seokjun/2026-11-18_real-video-cup-clearing/data/day3.txt`, `data/day3_ko.txt` (lines 20:02:37–41)
- `seokjun/2026-11-18_real-video-cup-clearing/data/chunks/day1`–`day4.txt` (the chunking AI's answers)
- `seokjun/2026-11-18_real-video-cup-clearing/runs/model/` (without chunks: the three recorded times in `night-3/marks/day3.json`; `night-1`–`night-4/check_results.json`)
- `seokjun/2026-11-18_real-video-cup-clearing/runs/model_chunks/night-1`–`night-4/check_results.json` (with chunks)
- `seokjun/prompts/text/chunking.txt` (chunking prompt), `seokjun/prompts/text/marking.txt` (time-marking prompt)
- README of the final product (noonchi repository), section "III-F. Habit Learning"
