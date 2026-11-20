# 8. Adoption criteria: 80% and chance probability (November 9–18)

## What was the problem

PAM (the method from the KAIST paper: watch the person during the day, then at night review that day's log and revise an "after this action, this help" rule table) turns even something seen on a single day straight into a rule. This is because the prompt for the nightly self-reflection (the step where, after the day ends, the AI revises the habit memory from that day's log), which revises the rule table at night, is deliberately written to make rules generously.

This problem actually appeared in the four-day routine videos I recorded myself. After seeing only day 3 (the first day the routine changed), a rule "when sitting at the desk, bring the bowl" was created, and on day 4, while the person sat looking at their phone, the robot followed this rule and chose the bowl action (at the 13-second mark). I needed a criterion that separates something that happened once from a daily habit.

## How I thought about it

### First criteria (November 9)

I first set the criteria within the appliance-signal design (Note 5).

| Rule | Adoption criteria |
|---|---|
| Rule without conditions | Matches on at least 4 different days, and the same action was taken in that situation at least 80% of the time |
| Rule with conditions such as day of week or weather | Both of the above, plus a rate at least 20 percentage points higher than without the condition, and a chance probability (p-value) below 0.001 |

- The chance probability was computed with a one-sided binomial test (a method that computes "if this happened at its usual rate regardless of the condition, the probability of getting as many hits as now"). The floor (minimum base rate) for the usual rate was set at 1%.
- Combining conditions yields hundreds of candidates, producing combinations that fit by chance, such as "snacks on Tuesdays." The chance check was added to filter these out.
- Running it on 50 virtual logs of random behavior cut the number of logs with spurious rules from 20–24 to 1. Real habits (water after exercise, morning coffee, etc.) were mostly still found, while rare habits such as Friday beer were hard to find with 6 weeks of data and needed about 12 weeks. The simulation code for this 50-run virtual-log test no longer exists; only the results remain, in the design document and the presentation slides.
- I treated it not as a test that proves the right answer but as a device for filtering out chance combinations, and chose to be late rather than intervene wrongly.

### Does it hold up in reality? (November 12)

I ran a numerical simulation (no AI calls) of 200 virtual people, each living 12 weeks, including days when the habit is skipped, observation errors, and days when the robot helped instead. With realism set to "medium" and a rate criterion of 80%, holes appeared.

| What surfaced | Numbers |
|---|---|
| Rules without conditions skip the chance check, so spurious rules remain | Even with the chance check, 70.5% of people got a spurious unconditional rule (71.5% without the check) |
| Days when the robot helped instead are excluded from the calculation, so wrong rules are never corrected | 71.5% of people still had a spurious rule at week 12. With human reactions included in the calculation: 9.5% |
| The Mon/Wed/Fri habit, which has more evidence, was caught later instead | First help at week 11; 57% were never helped within 12 weeks (Friday beer: week 9, 21%). Cause not checked |

Lowering the rate criterion from 80% to 70% added 8.2 helps per person over 12 weeks, and 18.9 wrong interventions.

### Examining the basis for each number (November 14)

Before attaching the checks to PAM, I examined the basis for each number.

| Number | What it does | Basis |
|---|---|---|
| 80% | Consistency | Earlier design. No recorded reason |
| 0.001 | Chance or not | Earlier design. No recorded reason |
| Floor of 1% | Minimum for the usual rate | Earlier design. No recorded reason |
| 5 minutes | Window for collecting candidates; window within which the action must follow | Provisional value |
| 4 different days | Blocks records concentrated on one day; minimum evidence | Earlier design |

Working through the numbers showed that the two checks overlap heavily.

- For actions done once a day, the usual rate almost always becomes the 1% floor. If the usual rate is about 3.16% or less, every candidate seen at least twice with at least 80% follow-through gets a chance probability below 0.001 (confirmed by computing every case from 2 to 200 occurrences). In that case, what the chance check adds to the 80% criterion is effectively just "must be seen at least twice."
- The chance check does independent work in two cases: when something has been seen only once, and when the action is frequent to begin with. If someone drinks water 40 times a day and the usual rate is 20%, even 4 follow-throughs out of 5 give a chance probability of 0.0067 and fail.
- The floor effectively sets the minimum count: 2 at 1%, 3 at 5%, 4 at 10%.
- Tightening the threshold to 0.0001 means every candidate needs one more observation to pass. It lowers the odds that something done only half the time passes by luck, but a real habit that happens only twice a week gets pushed to the following week.
- Neither check looks at dates, so something that happened 3 times on a single day when guests came also becomes a rule.

I compiled 8 questions, including whether there is a reason to keep both checks, whether the way the usual rate is counted is statistically correct, whether the problem of testing many candidates (multiple comparisons) can be handled with a single 0.001, and how to set the numbers on a sound basis, and decided to ask other AIs (ChatGPT, Gemini) as well. Their answers are not preserved in the documents.

### Simplifying (November 14–15)

I left PAM as it was and decided to filter only the trigger (signal that starts the robot's help) candidates produced by self-reflection through the checks.

| What | Before | Changed to |
|---|---|---|
| Context conditions (day of week, people present, etc.) | Up to 2 attached | Dropped from this version (Note 7) |
| Who proposes candidates | All events within 5 minutes before the action are collected | Self-reflection proposes 1–3 per rule |
| Chance check | Only for rules with conditions | On the trigger candidates themselves. Baseline: "the action rate when the trigger is absent" |
| 4 different days | Present | Not included. Because of the 1% floor, a candidate must be seen at least twice to pass |
| When the same candidate repeats | Repeats within 60 minutes grouped as one | Only the last candidate right before the action is counted (below) |
| Observation-only period | The first week | None. Recomputed every night over the whole log so far |

- Candidates that pass both checks are combined with "or" and given to the robot for the next day. Failed candidates are not deleted; they are tested again the next night.
- For a once-a-day habit, the first rule appears on the night of day 2, and the robot helps proactively from day 3.

### How to count

- **Only the last candidate right before the action counts as "followed."** If the spoon is put down at 18:57, 18:58, and 18:59 and the bowl is cleared at 19:01, that is 1 of 3. The robot moves the moment it sees the trigger, so crediting candidates that repeated without the action would create a rule that clears the bowl while the person is still eating. This also prevents a single action from being counted many times and passing on the very first night.
- **Occurrences that could not be seen are not counted.** If the person was not visible during the 5 minutes after a candidate, that occurrence is excluded. Without separating "seen and not done" from "not seen," real habits are missed.
- **The usual rate** is counted by dividing the time outside the 5 minutes after each candidate into 5-minute bins and taking the share of bins that contain the action. Bins where the person was not visible are excluded.

## How far it got

### Formula (in the form confirmed in the documents and code)

```
adopt(c → a)  ⟺  k/n ≥ τ  ∧  Σ_{i=k}^{n} C(n,i) · p₀^i · (1 − p₀)^(n−i) < α
                 p₀ = max(p̂₀, ε)

FSM trigger(a) = ⋁ { c : adopt(c → a) }        (at most 3 candidates)

τ = 0.75 (0.8 before November 18),  α = 0.001,  ε = 0.01,  Δ = 5 min
```

- c is a trigger candidate, and a is a predefined task the robot can do. The FSM is a rule table that splits the day into stages and attaches help rules to each stage.
- n is the number of times c occurred (excluding occurrences whose following 5 minutes could not be seen), and k is the number of those in which a came within 5 minutes (Δ) with no repeat of c in between.
- The first condition is consistency; the second is not-by-chance. p̂₀ is the usual rate and ε is the floor. ∧ means "and," and ⋁ means the passing candidates are combined with "or."
- This is not new math. It is an adoption rule that attaches a consistency threshold (τ) and a floor (ε) to a one-sided binomial test.
- Values in the check code (`seokjun/pam/trigger_check.py`): pass rate (`RATE_MIN`) 0.75, chance threshold (`ALPHA`) 0.001, floor (`FLOOR`) 0.01, reference time (`FOLLOW_SECONDS`) 300 seconds. The reference time can be changed at run time (1 minute in the November 18 experiment, where a day lasted 5 minutes).

### Experiments

| Date | Experiment | Result |
|---|---|---|
| 11-14 | Synthetic log, 7 days; answer key in place of the AI, computation only | All 84 cells matched expectations |
| 11-15 | Rebuilt as 5 weekdays of a person living alone; same check | All 60 cells matched |
| 11-16 | One morning hour × 5 days. Computed with the answer key; night step with a real AI (Qwen3.5-27B) | Answer key: all 45 cells matched. With the real AI: filtered out 10 weakly supported signals and got 3 of 6 robot tasks right ($0.31) |

- I rebuilt the synthetic log twice. The earlier 7-day log differed from real life, for example with the spoon being put down exactly once every evening. The 16-hours-a-day log pulled in a step not in the paper and caused problems, so I cut it down to one morning hour × 5 days to match the paper's method.
- Examples the check blocked in the November 16 experiment:
  - Wiping the mouth while eating → clear the bowl and cup: 2 of 6 (33%); when the AI chose again, 5 of 13 (38%). Without the check, the robot would come to clear the bowl every time the person wiped their mouth.
  - Sitting idly in front of the empty bowl → clear: 4 of 25 (16%).
  - Watching the news on the sofa with an empty can nearby → clear the empty can: 1 of 1 (100%), but failed with a chance probability of 0.01.
  - The coincidental "answers the phone → clear the empty can": passed at 2 of 2 on the night of day 2, then failed on the night of day 3 when it became 2 of 3 (in the experiment computed with the answer key).

### 80% → 75% (November 18)

When I redefined the action time and reran the 5 days (Note 9), on the night of day 4 the answer-key signal "getting up from the bed → open the curtains" stood at 3 of 4 (75%). Because the self-reflection prompt says "a candidate that has appeared 3 or more times but is below 80% may be replaced with another candidate," the AI discarded it, and it disappeared from the candidate list on the night of day 5. So I lowered both the pass threshold and this sentence in the prompt to 75%.

### The final product (noonchi)

The adoption test went into the team server (noonchi). Habit learning as described in the final product's README: the day's log is grouped into activity chunks (Note 10), and a candidate goes into the next day's rule table if the action follows within 300 seconds of the signal at least 75% of the time and the chance probability is below 0.001.

## Open questions

- 75% (initially 80%), 0.001, 1%, and 5 minutes are still values set without a basis. Comparing on synthetic logs only returns the time windows I planted, so the 5 minutes should be set by measuring how long it takes from signal to action in real logs.
- The effect of lowering the threshold to 75% was not measured. On the same night of day 4, another candidate at 3 of 4 was "carrying the bowl to the kitchen → bring a can of coffee over," and at 75% candidates like this pass too. In the realism test, lowering the threshold increased wrong interventions more than it increased help.
- Things concentrated on one day (3 times on the day guests came) are not blocked by the current criteria.
- There was also the idea of giving each habit its own reference time (3 minutes for clearing cups, 30 for laundry). If the AI were allowed to extend the time while looking at the check results, it would drift toward extending it until the rule passes, and the chance check would lose its meaning. If this is done, the code should set the time by measuring how long things actually take.
- Once a rule exists and the robot acts first, scenes of the person doing the task themselves stop. From then on, whether to keep the rule has to be judged from the person's reactions, but I have not decided after how many reactions to correct or delete it.
- The binomial test assumes that opportunities do not affect one another and that the action probability is constant. Multiple opportunities on the same day, and action probabilities that vary by time of day (comparing something done only in the morning against the daily average), may not fit this assumption.

## Related

- Experiment folders: `2026-11-12_adoption-criteria-realism-test/`, `2026-11-14_synthetic-logs-7-days/`, `2026-11-15_synthetic-logs-5-weekdays/`, `2026-11-16_synthetic-logs-morning-1-hour/`
- Notes 5 (Appliance signals and trigger finding) and 7 (Context conditions): where the first criteria came from
- Note 9 (Late signals and the definition of a trigger): late signals that passed the check; what prompted the 75% adjustment
- Note 10 (Activity chunks): the problem of counting the same moment many times

## Sources

- `seokjun/notes/sources/설계문서/2026-11-09_가전_관찰에서_도움_규칙_만들기.md` (making help rules from appliance observations: first criteria, results of the 50 virtual logs)
- `seokjun/notes/sources/설계문서/2026-11-14_트리거_채택기준_80퍼센트와_p-value.md` (trigger adoption criteria, 80% and p-value: basis for the numbers, properties confirmed by calculation, the 8 questions for other AIs)
- `seokjun/notes/sources/설계문서/2026-11-14_PAM_80퍼센트_p-value_구현계획서.md` (PAM 80% / p-value implementation plan: night-step flow, how to count, formula)
- `seokjun/2026-11-12_adoption-criteria-realism-test/결과표.md` (results table)
- `seokjun/2026-11-16_synthetic-logs-morning-1-hour/README.md`
- `seokjun/pam/trigger_check.py` (header description and threshold values), `seokjun/prompts/text/README.md` (the 75% adjustment)
- KIST presentation slides, pp. 6, 8, 9
- Four-day video case: `seokjun/2026-11-04_four-day-routine-videos/README.md`, item 3 under "What I found by digging into the results"
