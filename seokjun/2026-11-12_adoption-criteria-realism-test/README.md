# Adoption Criteria Realism Test — Do the 80% Rule and the Chance Test Hold Up in a World with Mistakes? (2026-11-12)

## Summary

I tested the rule adoption criteria (the 80% rate and the chance test) with a computational simulation in which 200 virtual people each live for 12 weeks. At the "moderate" realism level, the robot did 52.0% of habit actions before the person did, but 71.5% of people still had false rules in week 12. I found two holes in the criteria. No model was called, so it cost nothing.

## Why I ran this experiment

- Earlier, I set the first criteria for adopting rules.
  - Rules without conditions: matched on at least 4 different days, and the person acted in that situation at least 80% of the time.
  - Rules with conditions such as day of week or weather: in addition to the two above, the rate is at least 20 percentage points higher than without the condition, and the chance test (the p-value of a one-sided binomial test, that is, the chance probability of this result) is below 0.001.
- The design document reported that, across 50 simulated logs, adding the chance test reduced the number of logs that produced a false rule from 20–24 to 1.
- This time I wanted to see whether the criteria still hold up once I add days the person skips a habit, observation errors, and days the robot helped instead, with rules set each night and the robot acting on them the next day.

## What I did

- I implemented the design document's adoption criteria in code. One virtual person lives for 12 weeks (84 days). Each night the rules are re-derived from the entire log up to that day, and the next day the robot acts on those rules.
- I created 200 people per setting. No model was called, and the total run time was 508 seconds.

### The virtual person's habits

| Habit | Trigger | Days it applies |
|---|---|---|
| Daily water | TV turned on | Every day |
| Friday beer | TV turned on | Fridays |
| Weekday coffee | Waking up | Weekdays |
| Dryer on rainy days | Washing machine finished | Rainy days |
| Mon/Wed/Fri snack | TV turned on | Mon, Wed, Fri |
| Chips when guests visit | TV turned on | When a guest is present |

- Separately from the habits, I added 8 random actions that the person simply does at a fixed rate (15, 30, 45, or 60%, two actions each), unrelated to any condition. If a rule formed for a random action, I counted it as a **false rule**.
- Each trigger happens once a day. The available conditions are day of week, weekday/weekend/holiday, 30-minute time slot, who else is present, weather, outdoor temperature, humidity, and indoor temperature.

### Realism levels

| Realism level | Does it on habit days | Also does it on non-habit days | Outcome not observed | Did / did not observed flipped | Trigger missed | 3-day trips away |
|---|---:|---:|---:|---:|---:|---:|
| Ideal | 100% | 0% | 0% | 0% | 0% | 0 |
| Moderate | 90% | 5% | 10% | 5% | 5% | 2 |
| Poor | 80% | 10% | 20% | 10% | 10% | 2 |

All of these are values I set for this test, not measurements.

### What I compared

- Rate threshold: 70%, 80%, 90%, 100%
- Chance test: on, off
- Three fixes: only observe for the first 2 weeks; adopt rules without conditions only after 10 opportunities have built up; count the person's reaction (if the person uses what the robot brought, it counts as "did"; if they undo it, "did not")

### What I counted

Numbers are averages per person over 12 weeks.

- **Times helped**: the number of times the robot did first something the person would have done anyway
- **Help rate**: of the days the person performed a habit action, the share where the robot did it first
- **Wrong interventions**: the number of times the robot stepped in when the person would not have done the action. I counted those coming from real habit rules and those coming from false rules separately.

## Results

By rate threshold (moderate realism)

| Rate threshold | Times helped | Help rate | Wrong interventions (real habits) | Wrong interventions (false rules) | People with false rules remaining in week 12 |
|---|---:|---:|---:|---:|---:|
| 70% | 98.4 | 56.8% | 32.0 | 37.3 | 89.5% |
| 80% | 90.2 | 52.0% | 26.0 | 24.4 | 71.5% |
| 90% | 69.0 | 39.8% | 17.3 | 8.9 | 35.5% |
| 100% | 54.7 | 31.6% | 15.7 | 8.6 | 34.0% |

At the 80% threshold, the help rate was 77.2% (ideal), 52.0% (moderate), and 30.0% (poor). The share of people with false rules remaining in week 12 was 77.5% (ideal), 71.5% (moderate), and 71.0% (poor).

With and without the chance test (moderate realism, 80% threshold)

| Chance test | People who got a false rule with a condition | People who got a false rule without a condition | Wrong interventions (false rules) | Times helped |
|---|---:|---:|---:|---:|
| On | 8.0% | 70.5% | 24.4 | 90.2 |
| Off | 100.0% | 71.5% | 59.4 | 116.7 |

Fixes (moderate realism, 80% threshold)

| Method | Times helped | Help rate | Wrong interventions (false rules) | People with false rules remaining in week 12 |
|---|---:|---:|---:|---:|
| As designed (days the robot stepped in are left out of the calculation) | 90.2 | 52.0% | 24.4 | 71.5% |
| Only observe for the first 2 weeks | 68.4 | 39.5% | 8.2 | 50.0% |
| Rules without conditions also only after 10+ opportunities | 72.8 | 42.0% | 6.5 | 35.0% |
| Count the person's reaction | 70.9 | 40.9% | 3.6 | 9.5% |

## What I found digging into the results

1. **Rules without conditions skip the chance test, so false rules remained.** The chance test applies only to rules with conditions. Adding it cut the share of people who got a false rule with a condition from 100.0% to 8.0%, but the share who got a false rule without a condition was 70.5%, almost the same as without the test (71.5%). The more often a random action was done, the more people got a rule for it (15% actions: 0.5% and 3.5%; 60% actions: 32.0% and 40.0%).
2. **Because days the robot stepped in were left out of the calculation, wrong rules were never corrected.** Under the design, days the robot acts are dropped from the rate calculation. When I counted the person's reaction, the share of people who ever got a false rule stayed the same at 72.5%, but the share whose false rule remained in week 12 fell from 71.5% to 9.5%. On the other hand, the help rate also fell from 52.0% to 40.9%.
3. **The Mon/Wed/Fri habit was actually adopted later.** The Mon/Wed/Fri snack, done three times a week, has more evidence than the Friday beer done once a week, yet it was picked up later and less often. I did not check the cause in this test.

   | Habit (moderate, 80%) | First week helped (median) | People never helped within 12 weeks | Most common rule in week 12 |
   |---|---:|---:|---|
   | Daily water | 1 | 0.5% | No condition (100%) |
   | Weekday coffee | 2 | 9.0% | No condition (57%) |
   | Friday beer | 9 | 21.0% | Day of week = Fri (76%) |
   | Chips when guests visit | 9 | 28.0% | Who is present = guest (74%) |
   | Mon/Wed/Fri snack | 11 | 57.0% | No rule (46%) |
   | Dryer on rainy days | 11 | 80.5% | No rule (72%) |

4. **Lowering the rate threshold increased wrong interventions more than help.** At moderate realism, lowering the threshold from 80% to 70% raised times helped from 90.2 to 98.4 (up 8.2), while wrong interventions rose from 50.4 to 69.3 (up 18.9).

## Limitations and next steps

- All numbers come from assumptions set in this test (how often habits are kept, observation errors, number of trips away, and so on), not from measurements.
- The design document gives no numbers for counting the person's reaction, so I ran it with assumptions set in this test.
- I did not include cases where a time of day is the trigger, where the person has already done the action, or where the person acts before the robot.
- I kept things simple: one trigger per day and one weather value per day. Indoor temperature in 2-degree steps and 3 public holidays are also assumptions of this test.

In the next design (November 14), I simplified the criteria. I dropped context conditions such as day of week and who is present from this version, kept the PAM paper's method as it is, and decided to filter only the trigger candidates produced by nightly self-reflection (the step where, after the day ends, the AI updates the habit memory from that day's log) using the 80% rate and a p-value below 0.001. The p-value applies to the trigger itself, not to a condition.

## Files

| Folder / file | Contents |
|---|---|
| `결과표.md` (results tables) | All results tables (by realism level and rate threshold, with and without the chance test, by habit, fixes, and by rate threshold when reactions are counted) |
| `code/sim.py` | Simulation code. Contains the adoption criteria, the virtual people, and the realism-level settings. Running it with `검사` (check) only verifies that it reproduces the worked calculation examples in the design document |
| `data/결과.json` (results) | All numbers for each setting |
