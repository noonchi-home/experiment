# Reading User Intent from Reactions After Help — Comparing Three Methods (2026-11-06)

## Summary

I compared three methods for inferring what the user wanted at a given moment from the observation log after the robot helped, using 15 text scenes written by an AI. Reading the whole log and answering directly did best, getting 10 right. Inverse planning was lowest at 6, so I dropped it.

## Why I ran this experiment

- I had planned to use the drink handoff videos (2026-11-02) to read reactions after help and revise rules accordingly. I was considering inverse planning (inferring what a person originally wanted by working backward from how they act after being helped) as the way to read those reactions.
- Before moving to video, I wanted to check on text scenes with clear answer keys whether inverse planning actually does better than simpler methods.

## What I did

I did this from 2026-11-04 to 11-06.

### The 15 scenes

- An AI (Claude) first fixed the intended answer for each scene, then wrote a time-ordered observation log to match. These are not logs extracted from real user videos.
- Besides drinks, the scenes include help with things like blankets, curtains, desk lamps, and tissues.
- Example: after the robot sets down a glass of water, the user takes medicine out of a drawer, puts one pill in their mouth, and drinks the water. The hidden answer is "they needed water to take medicine, not because they were thirsty."
- Scene titles and answers were hidden from the model.

### The three methods

| Method | What the model was given and asked |
|---|---|
| Read the whole log | Given the full time-ordered observation log and asked, in one sentence, what the user wanted at the moment the robot acted |
| Summarize as state changes | The same model first converted the log into an FSM (a summary that records states and the events that move between them). Given only that summary, it was asked the same question |
| Inverse planning | From the log up to just before the robot's action, plus the action the robot would take and its reason, the model generated 6–10 candidate intents. Then, for each line of user behavior, it gave a score for "if this were the intent, how likely is this behavior?"; the scores were multiplied, and the highest candidate was chosen |

- Model: gpt-6.1-terra (an OpenAI language model), thinking off. Each method was run once per scene.
- Grading: an AI (Claude) compared the meaning of each model answer with the hidden answer and marked it correct, partly correct, or wrong. There is no record of a person grading or re-checking the grades.

### Deciding first how inverse planning would get its scores

Inverse planning needs a numeric answer to "if this were the intent, how likely is this behavior?" I first tried out scoring methods on 8 short English questions, each pairing an intent with a behavior (e.g., "does not want the drink + pushes it aside"). Each question was asked with 2 option orders × 3 times, 48 times per model. Claude decided whether each should come out high or low.

| Method | Result |
|---|---|
| Have the model choose between "A) plausible B) not plausible" and read the probability of the answer letter | gpt-6-luna shifted by up to 0.36 just from swapping the option order, and by up to 0.34 across 3 repeats of the same question. gpt-6-sol and gpt-6.1-terra gave 0 or 1 on all 48 |
| Have it answer yes or no | The directions were right, but gpt-6.1-terra was nearly 0% or 100% on all 48, so it was hard to express differences between candidates |
| Have it give a number from 0 to 100 | Spread from 5 to 95, but all were multiples of 5, so ties occurred |
| Multiply each number it could have answered by the probability of writing that number, then average | For pushing the cup aside, "might drink it later" and "doesn't want it," previously tied at 90 vs. 90, separated to 90.6 vs. 86.8 |
| The above plus one line: "don't be overconfident" | The same two candidates became 81.3 vs. 74.7 |

I put the last two methods into the 15-scene test together (default setting and warning setting). If the top score fell below a threshold (30 for default, 40 for warning), the model was made to generate candidates again.

## Results

| Method | Correct | Partly correct | Wrong | Cost for 15 scenes |
|---|---|---|---|---|
| Read the whole log | 10 | 4 | 1 | about $0.0043 |
| Summarize as state changes | 8 | 7 | 0 | about $0.048 |
| Inverse planning (default setting) | 6 | 3 | 6 | about $0.261 (including the warning setting) |

- For inverse planning, the default and warning settings made no difference to the grades. The top candidate was the same in 11 of the 15 scenes.
- Across both settings, inverse planning took 1,107 calls, 0 errors, and 5 min 24 s.
- Reading the whole log got the most scenes fully right and was also the cheapest. Summarizing as state changes had no wrong scenes.
- I dropped inverse planning. Later experiments give the model the full observation log and have it judge directly. I also decided not to use the step that converts the log into state changes.

## What I found digging into the results

1. **Inverse planning missed scenes where the clue comes after the robot's action.** I attributed this to the candidates being generated only from the log up to just before the robot's action. In the medicine-water scene, the top candidate was "may have wanted to drink water," which leaves out why the water was needed. It also got the "grateful but too warm (blanket)," "desk lamp too bright," and "tried to hold back but drank anyway" scenes wrong.
2. **Candidate regeneration never kicked in.** The top score fell below the threshold in 0 scenes.
3. **Score gaps between candidates were small.** In the default setting, the top candidate's share was 15.5–34.4%, and in 11 of the 15 scenes the gap between first and second place was under 2 percentage points.
4. **Each candidate held only one state of mind.** In the scene where the user didn't see the cup (hidden answer: wanted water but didn't know it had been set down), "wants water to be there" (19.4%) and "doesn't know the robot brought water" (8.7%) became separate candidates.
5. **Answers based on the state-change summary were more cautious ("it may be that…").** In the scene where the user didn't see the cup, only this method pointed out "may not have seen the water being set down." On the other hand, in the "tried to hold back but drank anyway" scene, the robot's action got buried as an observation inside one state instead of being an event that moves between states. The effect of the summary format and the information lost in the conversion are mixed together.

## Limitations

- The 15 scenes are text written by an AI (Claude) with the answers fixed in advance. The clues are clear, so they may be easier than logs extracted from real videos.
- I did not test on real user videos.
- Each method was run only once.
- Grading was done by an AI (Claude). No person graded.
- These are interpretations made after seeing the full reaction to the help. I did not look at real-time judgment before helping.
- Only inverse planning was given the robot's action rule, and its candidates were generated at a different point in time. So it is hard to pin the differences between methods on a single cause.

Based on this result I dropped inverse planning and did not run the experiment on the drink videos (2026-11-02).

## Files

| File / folder | Contents |
|---|---|
| `장면별_답변과_채점.md` (per-scene answers and grading) | Hidden answer for each scene, the three methods' answers (translated into Korean) and grades, observation logs, and the actual English inputs and responses |
| `code/` | The 11 scripts that were run, and how to run them (`code/README.md`). Scene and answer definitions (`ip_scenes.py`), runners for the three methods (`direct_ask.py`, `fsm_test.py`, `ip_run.py`), and the scoring-method pilot tests |
| `data/` | Raw model responses (JSON), inverse planning run logs, Korean translations of the scenes, and a review page for the English prompts (`ip_test_texts_review.html`) |

Rerunning the code makes paid model calls, and running it in the same folder overwrites the original results.
