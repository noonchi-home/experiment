# 11. Open questions (compiled November 21)

## What was the problem

To answer "when should a robot help a person?", I started from reproducing PAM (the method from the KAIST paper: watch the person during the day, then at night review that day's log and build an "after this action, this help" rule table for each person) and went on to the adoption test, the definition of a trigger (a signal that starts the robot's help), and activity chunks. All the experiments assumed one person and one robot, and looked only at cases where one task is done at a time. Real homes are not like that. The experiments also left questions unresolved even within the current approach.

## How I thought about it

I split the remaining questions into two groups.

- **Questions that go beyond the assumptions.** The order of handling overlapping triggers, multiple devices, and personalization without asking. I named the first two as limitations in the KIST presentation and proposed them as future research. KIST's "User-Centered Dynamic Service Scheduling (2022)" study rescheduled the tasks requested by a single user and left extending this to facilities with multiple users as future work. I considered feeding the habits found through observation into such a scheduler (a component that decides the order and assignment of tasks) as input.
- **Questions to fix within the current approach.** Having self-reflection review the robot itself, counting same-meaning candidates as one, and running the same experiment several times.

## How far it got

- On p. 10 of the KIST presentation slides, I listed as limitations the order of handling overlapping triggers and cases where the robot does not act alone.
- The README of the final product (noonchi) covers only one home and one person, and states that habits conflicting between multiple people are out of scope. The final product chooses tasks in this order: safety, spoken requests, goals, then idle-time tasks. The order when several habit rules fire at the same moment is not written down.
- The remaining questions were only identified as problems from experiment results and were not tested separately.

## Open questions

### 1. What to do first when triggers overlap

- **Why it matters.** When several triggers come from one person at once, or triggers from several people occur at the same time, the robot has to decide an order. Even if it learns the habits correctly, getting the order wrong makes it late or makes it do a less urgent task first. Scheduling (deciding the order and assignment of tasks) becomes necessary.
- **Evidence so far.** In the rerun of the November 16 experiment, a single signal in the night-5 rule table, "rests briefly after eating," became the trigger for three tasks: clearing the bowl, clearing the cup, and bringing a can of coffee over. The current rule table does not set an order among these three tasks.

### 2. When the robot does not act alone

- **Why it matters.** A real home has several devices, such as a robot vacuum and an air conditioner. Even for the same habit, it has to be decided whether the robot or an appliance does it.
- **Evidence so far.** All the experiments assumed a single robot. I did design the use of appliance signals as triggers (Note 5) and the placement of appliance control behind a common interface (Note 6), but I did not address dividing tasks among multiple devices. In the KIST paper above (2022), a scheduler divided tasks in an environment with a robot arm, a mobile robot, and a smart lamp.

### 3. Estimating individual intervention preferences without asking

- **Why it matters.** Even for the same help, how much people want it and how much it bothers them differ from person to person. Asking users for information does not fit a robot that helps proactively, so it has to be read from behavior.
- **Evidence so far.** The design that separates desire for help (h) from the discomfort a way of helping causes (w) stopped before any experiments (Note 3). Inverse planning, which works backward from the person's behavior after help, got 6 right in a comparison of 15 text scenes, the lowest of the three methods, so I set it aside (Note 4). In the realism test (a numerical simulation built on assumptions), including human reactions in the calculation cut the share of people still holding a spurious rule at week 12 from 71.5% to 9.5%. What to read as a reaction has not been decided.

### 4. Having self-reflection review the robot's own judgments

- **Why it matters.** Self-reflection (the step where, after the day ends, the AI revises the rule table from that day's log) currently learns only from what the person did themselves. Once a rule exists and the robot acts first, scenes of the person doing the task themselves stop, so from then on the only clues for correcting a wrong rule are what the robot did and how the person reacted.
- **Evidence so far.** In the four-day videos, 0 of the 6 reflections looked back on an action the robot chose as wrong. This was because the daily summary contained only "the robot did not actually move." The synthetic-log experiments also wrote "the robot did nothing today" in the self-reflection input. Writing down the reasons behind each night's judgment so that the next night can continue the reasoning (the same direction as Reflexion, which the PAM paper cites) was listed as a next step on November 16, but not tested.

### 5. Counting candidates that say the same thing in different words as one

- **Why it matters.** If candidates describing the same scene in different words are counted separately, the evidence is split, and a real signal passes late or fails.
- **Evidence so far.** On the night of day 4 of the November 18 experiment run without chunks, the three clear-the-empty-can candidates (sitting with an empty can there, typing with the empty can nearby, working with the empty can nearby) were counted separately at 4 of 18, 4 of 7, and 4 of 16, and all failed. Even after chunking, two similar candidates remained separate (Note 10). Self-reflection is not allowed to change the wording of existing candidates (a change would make it a new candidate that searches past dates again), so it does not merge them on its own.

### 6. Running the same experiment several times to check variation

- **Why it matters.** AI gives different answers to the same input. With a single run, you cannot tell whether a difference comes from the method or from random variation.
- **Evidence so far.** In the four-day videos, running the same input (day 1) twice gave scores (F1, a measure of how much it got right; 1 is perfect) of 0.04 and 0.15. Self-reflection runs with answer randomness (temperature) set to 0.3. The November 16 result "3 of 6 → 4 plus a half" and the November 18 result "2 of 4 → 3" were each run only once per setting.

## Related

- Notes 3 (Intrusiveness and personal preference), 4 (Inverse planning), 5 (Appliance signals and trigger finding), 6 (Atomic actions and task planning), 8 (Adoption criteria), 9 (Late signals), 10 (Activity chunks)
- Experiment folders: `2026-11-04_four-day-routine-videos/`, `2026-11-06_intent-inference-comparison/`, `2026-11-12_adoption-criteria-realism-test/`, `2026-11-16_synthetic-logs-morning-1-hour/`, `2026-11-18_real-video-cup-clearing/`

## Sources

- KIST presentation slides, p. 10 (limitations and links with KIST)
- `seokjun/2026-11-04_four-day-routine-videos/README.md` ("What I found by digging into the results," "Limitations and next steps")
- `seokjun/2026-11-16_synthetic-logs-morning-1-hour/README.md` ("Remaining problems and causes," "Next steps")
- `seokjun/2026-11-16_synthetic-logs-morning-1-hour/runs/model_start/night-5/predictor_fsm.json` (three tasks on one signal)
- `seokjun/2026-11-18_real-video-cup-clearing/README.md` ("Remaining problems"), `runs/model/night-4/check_results.json`
- `seokjun/2026-11-12_adoption-criteria-realism-test/결과표.md` (results table), section 4
- `seokjun/notes/sources/설계문서/2026-11-14_PAM_80퍼센트_p-value_구현계획서.md` (PAM 80% / p-value implementation plan: section 5.1 self-reflection settings and the candidate-wording rule; chapter 11)
- `seokjun/README.md` ("Remaining problems")
- README of the final product (noonchi repository), "III-E" and "VI. Limitations and Next Steps"
