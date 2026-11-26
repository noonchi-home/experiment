# Saturday Evening, TV and Beer — Learning a Weekday/Time Context with a Real AI (2026-11-22 to 11-25)

## Summary

I gave the nightly learning steps of our team server (noonchi) three weeks of synthetic evening logs in which the person drinks beer while watching TV only on Saturday evenings, and let a real AI (Qwen3.5-27B through OpenRouter) do the reflection, the meaning check and the timestamp finding. Of the 12 runs, 2 learned both Saturday rules ("bring a beer when the person sits down to watch TV" and "clear the can after the TV goes off") with the context **Saturday 18:00–21:00**: one with the real AI finding the timestamps, one with timestamps taken from the synthetic log. A third run learned only "clear the can", also for Saturday 18:00–21:00. Most of the other runs stopped on network or provider errors, or on the meaning check rejecting the memory.

These runs were made **before** the fixes of 2026-11-25 (see "Code"). I will rerun the experiment with the fixed code and add the results here.

## Why I ran this experiment

- Demo scenario 2 of our project: on Saturday evenings the person watches TV with a beer. The robot should learn to bring a beer and to clear the can, but **only on Saturday evenings**, not every evening and not on Saturday afternoons.
- The adoption test alone gives "TV on → beer" a follow-through rate of 4/28 (14%), so it fails. The context search (none → a weekday or a 3-hour slot → both) has to find "Saturday" or "Saturday evening".
- With a fake AI that answers like the answer key, this already worked. The open question was whether it still works when a real AI writes the candidate rules and finds the timestamps.

## What I did

**Synthetic logs** (`scripts/beer-experiment-records.ts` in noonchi, no AI involved, no randomness)

- 21 days, starting Monday 2026-10-12 and ending Sunday 2026-11-01. Each day has only the evening window (18:59–20:36).
- Every day the person turns the TV on at 19:00 and off at 20:30.
- On Saturdays (10-17, 10-24, 10-31) the person gets up at 19:02:30, takes a beer can from the fridge, drinks it while watching TV, and after the TV goes off puts the can in the sink themselves.
- On the first two Saturdays the person also watches TV from 14:00 to 14:30 without beer. This is the counter-example that should make a time slot necessary.
- The lines look like what the server writes: short Korean change lines ("사람 TV 보는 중" = person watching TV) and one English scene sentence from the photo-reading model every 15 seconds.

**Nightly steps at the time of these runs**

1. Activity chunking: the AI groups the day's lines into activities.
2. Reflection: the AI writes candidate triggers for the two learnable tasks, "맥주 가져다주기" (bring a beer) and "맥주 캔 치우기" (clear the beer can).
3. Meaning check: a second AI call checks that states are person activities and conditions are person-side facts. On rejection the reflection is retried once.
4. Timestamp finding: the AI finds every moment of each candidate trigger and of each task in each past day.
5. Adoption test (code): within 5 minutes, follow-through rate at least 75% and chance probability below 1% (floor base rate 1%).
6. Context search (code): if a candidate fails without context, it is tested per weekday or 3-hour slot, then per weekday + slot.

**Models**

- Run `beer-experiment-real-20261122`: OpenAI gpt-5.4-mini.
- All other runs: `qwen/qwen3.5-27b` on OpenRouter. From the evening of 11-24 the provider was pinned to Alibaba, and calls were retried on HTTP 429/5xx and on cut-off answers.
- In runs `-h` and `-i`, timestamp finding did not call the AI: the times came from the synthetic log itself (ground-truth marking). This separates "does the reflection write good candidates" from "does the AI find the times".
- Runs from 11-24 on used `--only 2026-10-31`: the reflection and meaning check run only on the last Saturday night, while timestamp finding still covers every day up to it.

## Results

| Run | What was run | Outcome | Cost (USD) |
|---|---|---|---|
| `beer-experiment-real-20261122` | gpt-5.4-mini, 21 nights | Every night failed with HTTP 401 (API key rejected). Nothing learned | 0 |
| `beer-experiment-openrouter-20261122` | Qwen, 21 nights (stopped after 14) | Connection failures every night | 0.008 |
| `beer-experiment-openrouter-20261122-b` | Qwen, 1 night | Connection failure | 0 |
| `beer-experiment-openrouter-20261122-c` | Qwen, 21 nights (stopped after 2) | Night 1: the meaning check rejected the seed "eating or drinking" state as two activities. Night 2: empty answer | 0.046 |
| `beer-experiment-openrouter-20261122-e` | Qwen, 1 night, then 4 restarts on 5 chosen nights | Two restarts rejected by the meaning check; one night ran through but neither candidate passed (bring beer: 7 times, followed 0) | 0.182 |
| `beer-experiment-openrouter-20261122-f` | Qwen, 5 chosen nights | 10-24: learned "the person turns off the TV → clear the can" **without** a context (2 of 2 followed). Other nights: the reflection changed a seed state's activity (rejected) or connection failures | 0.298 |
| `beer-experiment-openrouter-20261124-g` | Qwen, night 10-31, 7 attempts | All failed: dropped connections, cut-off answers, a provider error, DNS failures | 0.588 |
| `beer-experiment-openrouter-20261124-h` | Qwen, night 10-31, 4 attempts, ground-truth marking | Attempt 4 learned "clear the can" for two candidates with **Saturday 18–21h** (3 of 3, chance 0.25%). The beer candidates were followed 0 of 3 | 0.215 |
| `beer-experiment-openrouter-20261125-i` | Qwen, night 10-31, ground-truth marking | Learned **both** with **Saturday 18–21h**: "sits on the sofa and turns on the TV → bring a beer", "turns off the TV and gets up → clear the can" (3 of 3 each, chance 0.25%) | 0.082 |
| `beer-experiment-openrouter-20261125-realmark-1` | Qwen, night 10-31, real marking | Failed on a connection error after 7.1 hours | 0.341 |
| `beer-experiment-openrouter-20261125-realmark-2` | Qwen, night 10-31, real marking | Ran through, nothing learned: "sits on the sofa → bring a beer" and "gets up from the sofa → clear the can" each 3 of 25; no context passed | 0.340 |
| `beer-experiment-openrouter-20261125-realmark-3` | Qwen, night 10-31, real marking | Learned **both** with **Saturday 18–21h**: "sits on the sofa → bring a beer" (3 of 4, chance 0.8%), "turns off the TV → clear the can" (3 of 3, chance 0.25%) | 0.326 |

Total about $2.4. Costs are the runner's estimate, or the value OpenRouter reported when the log has it. A full night with real timestamp finding took 41–45 AI calls and 1.3–1.4 hours.

## What I found digging into the results

- **Activity chunking failed on every day of every run.** Each `copies/marks-<day>.json` has an empty chunk list. The code saved the failure silently for past days, and the runner did not print the failure line for the current day, so I only noticed in the review on 11-25. The reflection therefore always read the plain day summary instead of chunks. The adoption test never used chunks. I removed the chunking step afterwards.
- **The meaning check rejected the team's own seed memory.** The seed state "eating or drinking" lists two camera values (eating, drinking). The check read that as two activities at once. Its prompt now says a state's activity list means "any one of them".
- **The AI copied seed text with different spacing.** In realmark-3 it wrote "사용자가 돌아와 TV 를 본다." for the seed "사용자가 돌아와 TV를 본다.", and the robot memory kept both. Triggers are now compared without spaces.
- **"Turn off the TV → clear the can" sat next to the seed "ask the user" arrow for the same moment.** The reflection never saw the seed arrows that carry a robot action, so it could not reuse their exact trigger text. The seed arrows are now shown to the reflection as already adopted.
- **Network and provider errors were the most common failure.** Long nights (1–7 hours, about 40 calls) are fragile: one dropped connection fails the whole night.

## Limitations and next steps

- One synthetic household and only three Saturdays. Every learned rule rests on 3 follow-throughs.
- The context search tries up to 72 weekday/slot combinations per candidate, each at a 1% chance threshold, so a coincidence can pass more easily than 1%. I keep the threshold for now and note it here.
- Each configuration ran once or twice, so I cannot say how often a real-AI night succeeds.
- Next: rerun three times with the fixed code (below) and add the results to this folder.

## Code

- Server code: [noonchi, branch `feat/context-rules`](https://github.com/noonchi-home/noonchi/tree/feat/context-rules). Runner: `scripts/beer-experiment.ts`; synthetic logs and ground-truth marking: `scripts/beer-experiment-records.ts`.
- The exact commit of each run was not recorded. All runs predate commit `30c5b3d2` (2026-11-25).
- Fixes made after these runs, from the review of 11-25: `30c5b3d2` and `c6d8fc49` … `f20474fe` (keep passed candidates, Saturday-only rules narrowed to their 3-hour slot, re-mark when the marking prompt or a state description changes, posture allowed as a condition, seed action arrows shown to the reflection, spacing-insensitive triggers, chunking removed, leftover "video" words removed from the prompt, unused habit filter removed).

## Files

Each run folder under `runs/` holds what the runner wrote:

| File | Contents |
|---|---|
| `run.log`, `run*.log` | Console output of one start of the runner (Korean). One file per restart. The PC path in the first line was replaced with `output/` |
| `nights.jsonl` | One line per night: success, new arrows, adoption checks, token use, cost, seconds |
| `days.json` | The days of the synthetic log |
| `noonchi.db` | The server's SQLite history database for the run: log lines, decisions, memory versions, reflection records. Its write-ahead log was merged in before upload |
| `copies/marks-<day>.json` | Timestamp-finding results per day (cache reused across nights) |
| `copies/check-<day>.json` | Adoption-check results of a successful night |
| `copies/old-marks-thinking-off/` | (`-e` only) timestamp finding with the model's thinking off, kept for comparison: it attached taking out the beer to "clear the can" |
| `check-inputs.jsonl` | The candidate memories sent to the meaning check, kept even when rejected |
