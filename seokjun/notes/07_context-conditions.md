# 7. Context conditions (November 9–13)

## What was the problem

PAM's rules take the form "after this action, this help." So they cannot capture a habit like drinking beer only on Fridays. If, over 28 days, the person turns on the TV every night and drinks beer only on the 4 Fridays, "TV on → bring a beer" holds on 4 of 28 days (14%), fails the 80% criterion, and the habit is missed.

Allowing conditions creates the opposite problem. Combining day of week, weather, and people present yields hundreds of candidates, and some of them fit by chance ("snacks on Tuesdays"). I needed a way to capture habits without mistaking chance for habit.

## How I thought about it

### Up to two from a predefined list

I extended rules to "trigger (a signal that starts the robot's help) + conditions → help." Conditions (called guards in the design document) are chosen only from a predefined list, and at most two are attached.

| Group | Conditions | Where the values come from |
|---|---|---|
| Time | Day of week, time of day, weekday/weekend/holiday | Filled in by code from the calendar and clock |
| Place and people | Location, people present | Extracted by the model from the observation log |
| Environment | Weather, indoor temperature band | Weather data; the indoor temperature the AC reports every 30 minutes |
| Device | Course, channel, mode | Appliance logs |
| History | Previous activity, things already done today | Observation log |

- On November 10 I refined the values. Time of day changed from one-hour slots to 30-minute windows found in the log. Weather changed from "rain / no rain" to weather state (clear, cloudy, rain, snow) plus outdoor temperature in 5-degree bands and humidity in 20% bands. Indoor temperature uses 2-degree bands, and people present becomes "unknown" if more than 30 minutes have passed since anyone was last seen.
- In the KIST presentation slides I showed a reduced set of six: day of week, weekday/weekend/holiday, 30-minute time of day, people present, weather, and indoor temperature.
- **I replaced "workday / day off" with "weekday / weekend / holiday."** Weekday, weekend, and holiday can be filled in from the calendar, but whether the person went to work that day cannot be known from the calendar alone. I do not infer that an individual went to work. Things actually observed, such as "left during the 8 a.m. hour," can be used as history conditions.
- Item stock is not a condition; it is something always checked right before execution.
- Condition values use only what could be known up to the moment of the trigger. If the TV is turned on at 23:00 and a friend arrives at 23:05, "people present" for the TV rule is "alone." Information learned later is not mixed into an earlier judgment.
- The model extracts only facts with a timestamp and a supporting sentence; choosing conditions and computing rates and probabilities are done by code.

### Search order

1. Look first at rules without conditions. If a rule occurs on at least 4 different days with a rate of at least 80%, adopt it immediately (Note 5 describes how this criterion came about).
2. If it fails, test every single-condition rule, and only if none pass, test pairs of conditions.
3. Among those that pass, choose the one that correctly covers the most actions. Ties are broken by fewer conditions, then time, place, and device conditions before history conditions, then a higher rate.
4. Remove the opportunities (the unit for evaluating one trigger–action pair once) covered by the chosen rule and search again with the remaining ones. So the result may be a single "sports channel" rule, two rules for "Friday" and "Tuesday," or nothing at all.

| Example | Without conditions | With conditions |
|---|---|---|
| TV on → bring a beer | 4 of 28 days, 14% | 4 of 4 Fridays, 100% |
| Wakes up → bring the laundry basket | 6 of 46 days, 13%. Weekend only: 4 of 13 (31%); clear weather only: 4 of 18 (22%) | 4 of 4 clear weekends, 100% |

### Filtering out combinations that fit by chance

I added two checks for rules with conditions.

- The rate with the condition must be at least 20 percentage points higher than the rate without it, for example going from 65% to 85%.
- The chance probability (p-value) must be below 0.001. This is the probability that, if the condition meant nothing, the usual rate alone would produce as many hits as observed or more. It is computed with a one-sided binomial test (a method that computes the probability of getting this many hits over several attempts with a fixed success probability). The usual rate is the action rate over all remaining opportunities, raised to 1% if it is lower. I used 0.001 rather than the common 0.05 because hundreds of combinations are tested.

| Example | Usual rate | Within the condition | Chance probability | Verdict |
|---|---|---|---|---|
| Friday beer | 4 of 28 days, 14% | 4 of 4 Fridays | 0.14⁴ ≈ 0.0004 | Below 0.001, adopted |
| Tuesday snack | 14 of 28 days, 50% | 4 of 4 Tuesdays | 0.5⁴ ≈ 0.06 | 0.001 or above, rejected |

If someone hardly ever drinks but drank on all 4 Fridays, that is hard to call chance. If it is a snack eaten every other day anyway, hits on all 4 Tuesdays are hard to tell apart from chance. However, since the usual rate and the conditions are computed from the same log, this is not a rigorous test. I treated it not as a device that proves the right answer but as a practical filter for chance combinations.

## How far it got

### 50 virtual logs (results recorded in the November 9 design document)

On 50 virtual logs of random behavior, adding the chance check cut the number of logs that produced spurious rules from 20–24 to 1. Real habits (sports channel, water after exercise, hand washing, morning coffee) were mostly still found. Rare habits came late: Friday beer was hard to find with 6 weeks of data and was found at 12 weeks, and the dryer's two conditions (rain, towels) were likewise hard to find at 6 weeks and mostly found at 12. I chose to be late rather than intervene wrongly.

- The morning-coffee condition in this test was run with the old wording, "workday / day off." There is no result rerun with "weekday / weekend / holiday."
- The simulation code for the 50-run virtual-log test (sim.py, fix.py) no longer exists; only the results remain, in the design document and the presentation slides. Nor do the results guarantee the overall error rate when hundreds of combinations are searched.

### What the 4-week answer key showed (November 10)

I computed the answer key for the virtual 4-week appliance log with these criteria (with conditions on the old basis: one-hour time slots and rain or not).

- Of the 8 times laundry was taken out, it was moved to the dryer on all 4 rainy occasions, but the chance probability was 0.0625, so "dryer when it rains" was not adopted.
- Beer after selecting the sports channel (channel 37) first passed on the night of November 4: 4 of 4 on channel 37, an overall base rate of 5 of 29, and a chance probability of about 0.000884.
- On the last night, the condition "turns on the TV during the 21:00 hour on weekdays" also met the criteria for the beer rule. Whether it explains this person's preference has to be checked separately with logs from new dates.

### Realism test (November 12)

I tested the criteria with a numerical simulation of 200 virtual people, each living 12 weeks (detailed results in Note 8). With realism set to "medium" and a rate criterion of 80%, the condition-related results were as follows.

| Habit | Week of first help (median) | People never helped within 12 weeks | Help rate | Most common rule at week 12 |
|---|---:|---:|---:|---|
| Water every day | 1 | 0.5% | 84.2% | No condition (100%) |
| Friday beer | 9 | 21.0% | 22.1% | Day = Friday (76%) |
| Snacks when guests visit | 9 | 28.0% | 21.3% | People present = guest (74%) |
| Snacks on Mon/Wed/Fri | 11 | 57.0% | 9.3% | No rule (46%) |
| Dryer on rainy days | 11 | 80.5% | 5.4% | No rule (72%) |

- The Mon/Wed/Fri snack, done three times a week, has more evidence than the once-a-week Friday beer, yet it was caught later and less often. The cause was not checked separately in this test.
- The chance check applies only to rules with conditions. Adding it cut the share of people with a spurious conditional rule from 100.0% to 8.0%, but the share with a spurious unconditional rule was 70.5%, almost the same as without the check (71.5%).

### Dropped from this version (November 12–14)

On November 12 I postponed the appliance-signal-centered design and decided to work only on context conditions and chance probability. The next day, when I reset the direction, I dropped context conditions too. I kept the PAM approach (watch the day, make rules, and keep correcting them through self-reflection) as the base and carried over only chance probability. The November 14 design document records it as follows.

- Conditions such as day of week and people present are not used in this version. A trigger is a single event; two events are not combined.
- Chance probability is applied to the trigger itself rather than to conditions. The baseline changes from "the rate without the condition" to "the action rate when the trigger is absent"; the formula stays the same.
- Whether to drop the "4 different days" criterion was not decided at that time.

## Open questions

- I did not check why habits with plenty of evidence, such as Mon/Wed/Fri, were caught late.
- The balance between finding rare habits early and blocking spurious rules. In the 50-log test this showed up as the difference between 6 and 12 weeks.
- How to tell whether a condition that passed by chance (TV during the 21:00 hour on weekdays) reflects a real preference.
- Whether it is statistically sound to compute the usual rate and the conditions from the same log, and to filter hundreds of combinations with a single 0.001 threshold.
- If context conditions are brought back, how to layer them on the current structure, where chance probability applies to the trigger itself.

## Related

- Experiment folders: [2026-11-10_appliance-signals-4-weeks](../2026-11-10_appliance-signals-4-weeks/), [2026-11-12_adoption-criteria-realism-test](../2026-11-12_adoption-criteria-realism-test/)
- Note [5. Appliance signals and trigger finding](05_appliance-signals-and-trigger-finding.md): the criteria for rules without conditions (4 different days, 80%) and the Friday-beer denominator problem
- Note [8. Adoption criteria](08_adoption-test.md): the design that applies chance probability to the trigger itself after context conditions were dropped, and other holes exposed by the realism test

## Sources

- `seokjun/notes/sources/설계문서/2026-11-09_가전_관찰에서_도움_규칙_만들기.md` (making help rules from appliance observations: section 3 list of allowed conditions, section 4 adoption criteria and the Friday calculation example, section 6 results of the 50-log simulation)
- `seokjun/notes/sources/설계문서/2026-11-09_가전_도움_FSM_팀원설명.md` (appliance-help FSM explained for teammates: conditions use only values knowable up to the trigger moment; explanation of the p-value)
- `seokjun/notes/sources/설계문서/2026-11-09_가전_도움_규칙_구현계획서.md` (appliance-help rule implementation plan: section 3 condition search; at the end, the plan to cross-check against the 50-seed simulation)
- `seokjun/notes/sources/설계문서/2026-11-14_트리거_채택기준_80퍼센트와_p-value.md` (trigger adoption criteria: 80% and p-value; section 1 dropping context conditions, section 9 relation to the earlier design)
- `seokjun/2026-11-12_adoption-criteria-realism-test/결과표.md` (results table: sections 2–3, assumptions behind the condition list)
- `seokjun/2026-11-10_appliance-signals-4-weeks/answer-key/예상정답_읽는법.md` (how to read the expected answers: dryer when it rains at 0.0625, channel 37, the weekday 21:00 hour)
- KIST presentation slides, pp. 7–9 (my KIST interview slides (not in this repository), in the Downloads folder)
- Conversation logs (content summarized, not quoted)
  - Codex conversation, November 9, 20:23 (fixing the condition list, why 0.001 was chosen, search order)
  - Claude conversations, November 10 (30-minute time windows, weather values) and November 12–13 (the decision to work only on context conditions, then to drop them)
