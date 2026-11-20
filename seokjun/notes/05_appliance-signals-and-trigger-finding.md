# 5. Appliance signals and trigger finding (November 5–11)

## What was the problem

PAM looks for triggers (signals that start the robot's help) in human actions. But much of the help worth offering proactively at home is tied to appliances. When the wash finishes, you take out the laundry; when it is hot, you turn on the air conditioner. At the November 6 all-hands meeting we agreed to narrow the first version's help to appliance-related tasks, and I took on refining the trigger-finding prompt so that appliance states, not only human actions, could serve as triggers.

The November 8 fridge test exposed a problem. I fed in two scenes, each with the same "fridge door open alarm," separately and had the model make rules (model Qwen3.5-27B, one run per scene, about $0.02 in total).

| Scene | Rule the model made |
|---|---|
| A. Leaves the door open and goes to the sofa | One rule: "Alarm sounds → close the fridge door" |
| B. Keeps taking things out while the alarm sounds | None |

Whether to make a rule for each scene was correct. But rule A lacked the condition "the person has left." Under this rule, the robot would close the door even while the person is still taking things out, as in B (this is my interpretation from reading the output; I did not actually run rule A on scene B). Even for the same signal, there are times to help and times to wait, and the cue that separates them had to go into the rule. Setting a standard for what counts as a trigger became my main concern in this period.

## How I thought about it

### Reading appliance signals in two ways (November 6–9)

The idea I raised at the meeting was the difference between the washing machine and the air conditioner. For the washing machine, you look at what the person does after the "done" signal; for the air conditioner, you look at what came before the person turned it on. I organized this by who caused the signal.

| Signal | Example | Where to look | What to find |
|---|---|---|---|
| Machine-issued signal | Wash finished, door-open alarm | After the signal | The signal is the trigger; what the person did afterward is the task the robot takes over |
| Human-operated signal | Turning on the AC, opening the fridge door | Before and after the signal | Before: trigger candidates. After: what the person actually did (whether they took out water after exercising, or a beer while watching TV) |

- The window was initially 5 minutes before and after. In the November 9 implementation plan I extended it to 10 minutes after a machine signal and 10 minutes each before and after a human operation.
- An appliance signal is a starting point for looking for actions. The signal itself is not automatically a trigger.
- This approach cannot learn help unrelated to appliances (such as bringing a book). It also requires the appliance side to report who caused each signal: a person, the machine, the robot, or a schedule.

### A question to tell whether something is a trigger

The PAM paper's prompt has a principle: "use as triggers only signals that appear whether or not the robot helps." To apply this to appliance signals too, I turned it into one question: **If the robot does this task instead, does this event still happen?**

- Wash finished → take out the laundry: even if the robot takes it out, the end-of-wash chime still sounds. It stays a candidate.
- TV turned on → bring a beer: even if the robot brings the beer, the person still turns on the TV. It stays a candidate.
- Fridge door opened to get a beer → bring a beer: if the robot does it instead, the person has no reason to open the door. It is part of the action, so it is excluded. This door opening is used only as evidence that a beer was taken out that day.

I decided not to define this relationship as a fixed number of seconds.

### Criteria for choosing a trigger (November 9–11)

When several candidates passed the question, I settled which one to pick, criterion by criterion, through discussion.

| Criterion | Content |
|---|---|
| The event closest to the action | A trigger must be an event the action follows right away. If, before bringing coffee, both "sits at the table" and "puts the spoon on the empty bowl" pass the criteria, pick the latter, whose median time across days is shorter. A preceding situation like "during a meal" is treated not as an added condition (guard) but as a stage of the FSM (a rule table that splits the day into stages and attaches help rules to each stage) |
| Within 10 minutes | Both the look-back window and the deadline for counting the action as having followed were set to 10 minutes (reduced from 30) |
| Avoid motions that repeat within the same stage | Motions that occur many times within one stage, such as wiping your mouth or putting down the spoon during a meal, do not signal a change of stage. The robot should not clear the bowl because you wiped your mouth |
| Same event, same name | Actions are written as "motion / object / origin → destination." "Moved the laundry to the dryer" and "took the laundry out of the washer and put it in the dryer" are the same action. Events are written only with predefined words; anything not on the list is marked "unregistered." The word list is drawn broadly from household life in general, not fitted to the 4-week virtual log. Objects are recorded individually but grouped by type of use when counted (coffee cups and water glasses separately); places are counted individually |
| Exception: relations where the device must come first | Relations where the device's operation necessarily comes first, such as "this cycle's wash complete → take out the laundry," are adopted after a single observation and are not subject to the 10-minute criterion. Choices such as where to dry the laundry are judged by the habit criteria |

### What changed the adoption criteria: the denominator for Friday beer (November 9)

The first criteria were two: ① the trigger appears first in at least 3 of every 4 occurrences of the action, and ② the action follows in at least 80% of the times the trigger appears. Working through a Friday beer example showed that ① rejected a correct rule.

| Assumption: drank beer 10 times on Fridays, 2 on Sundays, 3 on Tuesdays | Calculation | Result |
|---|---|---|
| ② Of the 11 times the TV was turned on on Friday nights, the share with beer | 10/11 ≈ 91% | Pass |
| ① Of the 15 beers, the share preceded by Friday TV | 10/15 ≈ 67% | Fail |

Because ① uses all beers as the denominator, beers on other days that the rule does not cover sink an accurate Friday rule. I took the view that a rule does not need to explain every action, only to be consistent within its own scope, and changed ① to **at least 4 actions, on different days, preceded by the trigger (and conditions)**. I also changed the counting unit from "4 different cycles" to "4 different days," because cycles cannot be known in advance.

The AI I asked to review this (Codex) suggested splitting the actions a rule fails to explain into two kinds. Actions outside the rule's scope (Tuesday beer) become material for finding new rules. Actions the person did first because the robot was slow, even though the rule fired on time, become material for adjusting the timing of the existing rule. I put this distinction into the design document.

### Boundary values (November 9 implementation plan)

| Item | Value set |
|---|---|
| Repeated signals | Repeats of the same trigger within 60 minutes of the first signal are grouped into one opportunity (the unit for evaluating one trigger–action pair once). Condition values and the deadline are set from the time of the first signal |
| Deadline for counting the outcome | Set per action; 30 minutes by default (reduced to 10 minutes in the November 10 discussion) |
| Outcome of an opportunity | Done / not done / already done / unobservable / done by the robot. The last three are excluded from both the numerator and the denominator of the rate and are counted by reason |
| Day boundary | A living day starts at 4 a.m. Going to bed at 0:30 a.m. on Tuesday counts as Monday |
| People present | The latest value confirmed up to the trigger time. "Unknown" if more than 30 minutes have passed since the last observation |
| Order unknown | If the trigger and the action are logged at the same time and it is unclear which came first, "unobservable" |
| Time-of-day candidates | If all event candidates fail, the time itself is treated as a candidate: the earliest start time of the 30-minute window that contains the most distinct days in the last 12 weeks |

### After the robot helps

The November 9 design sorted reactions into four kinds: undoing (logged as a wrong intervention; if repeated, the conditions are searched again), starting before the robot (cancelled and logged as a late execution; if repeated, an earlier event is searched for), using the item brought (evidence that the help was useful), and unclear reaction. A confirmed rule is kept even as scenes of the person doing the task themselves become rarer because the robot keeps doing it, and it is corrected through reactions. In the November 10 discussion I added three more points.

- **Watch reactions for 5 minutes after helping.** That record is used in the nightly self-reflection (the step where, after the day ends, the AI revises the rule table from that day's log). If there is no reaction, keep going; whether the user noticed or not is not considered.
- **Grade the strength of reactions.** Accidents (breaking something, etc.) were left out of the grading. For spoken refusals I assumed voice records arrive as a separate file. "Did it before the robot" is counted by the same standard, but the correction is to search for an earlier trigger.

  | Strength | Example | What it does to the rule |
  |---|---|---|
  | None | No reaction | Keep going |
  | Weak | Undoing (putting the coffee the robot brought back into the fridge) | Correct the rule if undoing exceeds 20% of the times the rule was executed and has occurred on 2 different days. First search the conditions again; if it continues, stop the rule and observe again |
  | Medium | Blocking (putting a hand in front of the robot) | Cancel on the spot and search the conditions again the next night |
  | Strong | Refusing by voice or through the app | Stop the rule immediately. Turn it back on only with the user's permission |

- **Detect missed tasks.** If the person's habit changes to suit the robot and the trigger disappears (after eating, going to their room without putting the spoon on the bowl), the robot does nothing, the person has nothing to react to, and no record is left. So if 10 minutes pass after the person leaves the place holding the task's starting state (for a bowl, the table) and it is unchanged, it counts as a missed candidate; if the person then does the task themselves, it counts as a confirmed miss. If they come back and use that bowl, it is not a miss. When confirmed misses accumulate on 4 different days, the trigger is searched for again in the 10 minutes before the person left. Cases where the robot failed to execute are recorded separately from misses.
- Doing the task simply because time has passed was considered but not chosen. There are many exceptions, such as clearing the meal of someone who has only stepped away for a moment.

These November 10 decisions were made only in conversation, and the direction changed before they were moved into the design document or the implementation plan.

## How far it got

- **Four design documents.** A summary of the task planner and appliance-help design (November 8); making help rules from appliance observations; a summary for teammates; and the first implementation plan (all November 9).
- **Fridge two-scene test (November 8).** Results above. As the next test, I planned three scenes that fix a rule made once and vary only the observation at the moment of the alarm (front of the fridge clear → close; in use → wait; unknown → wait), but I did not run it.
- **Virtual 4-week appliance log and answer key (November 10).** One person's 28 days (October 12–November 8): 861 appliance signals (714 human operations, 147 machine alerts) and 86,995 observation lines at 4-second intervals. Observations exist only for the 10 minutes after machine signals and the 10 minutes before and after human operations. The evaluator-only answer key has 980 rows that recompute 35 candidates every night, plus 646 next-day decisions (65 execute, 129 wait, 129 cancel, 323 do not intervene). It also includes scenes where the decision splits on the same fridge alarm: on October 18 the person's hand is on a shelf, so wait; on October 23 a paper bag blocks the front of the door, so wait; on October 25 the front of the door is clear, so execute.
- **Not run with a model.** The answer key was computed with the criteria from before the values changed in the November 10 discussion (30-minute deadline, one-hour time slots), and I found no record of recomputing it with the new values.
- **On November 12 I postponed the appliance-signal-centered input** and decided to spend the remaining time on habit judgment (the adoption test). The November 14 plan replaced the November 9 implementation plan, and at that point the window for finding triggers and the time within which the action must follow were reset to 5 minutes.

## Open questions

- Can the model be made to include, in its rule, the cue that separates helping from waiting on the same signal (has the person left)? The fixed-rule three-scene test remains to be run.
- Triggers that require weighing the person's situation and the appliance state together. In the November 6 action-notation test, neither method could combine "came home + hot" for the AC trigger.
- If the closest event comes too late, the robot is slower than the person. This actually surfaced as motions already heading toward the task passing as triggers (Note 9).
- Help given while the user is away (clearing bowls, taking out laundry) gets no reaction within 5 minutes. I have not decided whether to keep watching until the user returns to that place.
- When, and under what conditions, a real LG appliance reports an open door must be checked on the model actually used. The 60-second alarm in the test is an assumption built into the synthetic scenes.

## Related

- Experiment folders: [2026-11-06_task-planner-pilot](../2026-11-06_task-planner-pilot/), [2026-11-08_fridge-door-two-scenes](../2026-11-08_fridge-door-two-scenes/), [2026-11-10_appliance-signals-4-weeks](../2026-11-10_appliance-signals-4-weeks/)
- Note [6. Atomic actions and task planning](06_atomic-actions-and-task-planning.md): the same period, on turning the chosen help into a sequence of robot motions
- Note [7. Context conditions](07_context-conditions.md): the design that adds conditions such as day of week and weather on top of the adoption criteria set here
- Note [8. Adoption criteria](08_adoption-test.md): revisits repeating candidates such as the spoon by counting "only the last candidate right before the action"
- Note [9. Late signals and the definition of a trigger](09_late-signals-and-trigger-definition.md): where the question "does it happen even if the robot does it instead?" was used again

## Sources

- `seokjun/notes/sources/설계문서/2026-11-08_작업계획기_가전도움_설계정리.md` (task planner and appliance-help design summary: ch. 5 the two kinds of appliance signals and the paper's original trigger rules, ch. 7 action-notation test, ch. 12 points to align with the November 6 meeting)
- `seokjun/notes/sources/설계문서/2026-11-09_가전_관찰에서_도움_규칙_만들기.md` (making help rules from appliance observations: the trigger question, counting under the same name, opportunities and the five outcomes, reaction-correction table, fridge test)
- `seokjun/notes/sources/설계문서/2026-11-09_가전_도움_FSM_팀원설명.md` (appliance-help FSM explained for teammates: repeated motions are not used as end signals)
- `seokjun/notes/sources/설계문서/2026-11-09_가전_도움_규칙_구현계획서.md` (appliance-help rule implementation plan: section 4, boundary values)
- `seokjun/notes/sources/ai-collab/fridge_fsm_pair_result_2026-11-08.md`, `seokjun/2026-11-08_fridge-door-two-scenes/` (requests and responses for the two fridge scenes)
- `seokjun/notes/sources/ai-collab/codex_trigger_design_2026-11-09.md`, `codex_trigger_rules_revision_2026-11-09.md`, `codex_trigger_time_outcomes_2026-11-09.md` (the order in which the November 9 documents were revised)
- `seokjun/2026-11-10_appliance-signals-4-weeks/input/`, `seokjun/2026-11-10_appliance-signals-4-weeks/answer-key/예상정답_읽는법.md` (the 4-week log and the answer key)
- Team meeting minutes: `02_Meetings/2026-11-06_전체회의록.md` in `noonchi-home/docs` (November 6 all-hands minutes: look after the signal for the washer and before it for the AC; appliance states can be triggers too)
- KIST presentation slides, p. 5 (my KIST interview slides (not in this repository), in the Downloads folder; the principle of not using actions that repeat within the same stage as triggers)
- Conversation logs (content summarized, not quoted)
  - Codex conversation, November 9, 19:13–20:23 (the denominator for Friday beer, 4 different days)
  - Claude conversation, November 10–11 (closest event, 10 minutes, missed-task detection, 5-minute reaction window, reaction strength, excluding repeated motions)
