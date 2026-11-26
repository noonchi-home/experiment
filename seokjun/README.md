# Seokjun's Research — When Should a Robot Help a Person?

## Starting point

In our team project (a home where the LG CLOiD home robot helps people before they ask), I was responsible for the decision engine. I held on to one question: **when should a robot help a person?**

The same empty bowl is a cue to help with preparation before a meal and something to clear away after it. Whether putting down utensils means the person has finished eating or is just pausing also depends on the situation. Knowing each person's disposition would help, but disposition is too broad and vague. So I decided to look at **habits** instead of disposition. Among the actions a person repeats every day, the robot finds tasks it can do on the person's behalf, and when it sees the action that appears right before that task (the trigger), it helps without asking.

While looking for research that answers the question of when a robot should help, I came across and read KAIST's PAM paper (CoRL 2026). The robot watches the person during the day, then looks back over the day at night and builds a rule table for each person of the form "after this action, this help." It matched our question exactly, so I started by turning the paper's method into code and reproducing it.

- Paper: An Agentic Framework for Proactive Robots with Procedural Assistance Memory — [arXiv 2610.21211](https://arxiv.org/abs/2610.21211) · [authors' public materials](https://github.com/DAVIAN-Robotics/PAM)
- This is not the authors' official code; I rewrote it from the paper and its appendix.

## Terms to know first

| Term | Meaning |
|---|---|
| PAM | The method the paper proposes. The robot reads photos together with its habit memory to decide whether to help, and at the end of each day revises the memory using that day's log |
| Habit memory (FSM) | A rule table that splits the day into stages such as "sits at the table → eating → finished eating" and attaches "when this → this help" rules to each stage |
| Trigger | The signal for the robot to start helping. An action or appliance signal that appears just before the person does that task |
| (Nightly) self-reflection | The step after the day ends in which the AI reads that day's log and revises the habit memory |
| Inverse planning | A way of working backward from a person's actions to estimate what they originally wanted |
| Adoption test | A test that accepts as rules only those trigger candidates from the AI that are followed by the task often enough and are unlikely to be chance |
| Activity chunks | The per-second observation log first grouped into units of "what the person is doing" |
| F1 | A score for how accurate the predictions are. 0–1, with 1 being perfect |
| p-value | "The probability that this is chance" (chance probability). The smaller it is, the less likely it is chance |

## How my thinking developed

### 1. Deciding without asking — decision logic and PAM reproduction (October 23–26)

- **The problem.** Getting information by asking the user doesn't fit a robot that "helps first." Almost no information should have to come from the user, and the robot must decide on its own whether to "look more, or help now."
- **How I decided.** I didn't settle the decision structure right away. I got separate opinions from two AIs (Codex and Claude), had them review each other's, and then decided. I narrowed the first situation to "whether to clear the cup."
- **Reproduction.** I ported the paper's method as is, changing only the setting (the breakfast table) and the output (a written decision instead of robot motion). While reproducing it, I fixed two things.
  - The self-reflection step existed in the code but had never actually run.
  - My initial design, "when the person gets out of bed, bring milk," was too early a signal. I redesigned it as "when the person sits at the table."
- **Next question.** Whether a decision method that estimates the situation with probabilities (POMDP) could be layered on top of PAM.

### 2. Does memory actually help? — four days of routine videos I recorded myself (November 3–4)

- **What I did.** I filmed two days of an evening studying routine and two days of an evening meal routine myself and ran PAM on them.
- **I didn't take the paper's numbers as is.** The shortest signal in our videos lasted 0.5–1 second. So instead of the paper's 2-second interval, I reset it to a 1-second interval (9 frames).
- **I decided first what to measure.** (1) Does it build the right rules? (2) Does it correct them properly after seeing the reaction to its help? (3) Do triggers actually fire?
- **I kept information known only to the evaluator from leaking into the model.** Even the daily summary was built only from the scene descriptions the robot wrote every second.
- **Results.** With memory, the action F1 was 0.41, 0.27, and 0.25; without memory, 0.04, 0.00, and 0.08. But running the same input twice swung between 0.04 and 0.15, so I drew no conclusions about small differences between memory types.
- **What I found by digging into the results.**
  - When the routine changed, the rule table deleted the old routine's stages and 5 rules. In the paper (Figure 7), they were kept.
  - Self-reflection learned only from what the person did themselves, and never looked back at whether the actions the robot itself chose were wrong.
- Folder: [2026-11-04_four-day-routine-videos](2026-11-04_four-day-routine-videos/)

### 3. How much intrusion is acceptable? — intrusiveness and personal preference (October 31–November 1)

- **The problem.** The discomfort caused by wrong help differs by action. Bringing milk that isn't needed and clearing away something still in use carry different weight. No reaction does not mean satisfaction, and the person doing a task themselves does not mean the robot missed a chance to help.
- **My thinking.** I separated the desire for help (h) from the discomfort a way of helping causes (w). This was to represent a person who "wants help but doesn't like the robot coming close." Piling up per-action rules alone gives no way to judge help the robot has never seen before, so I kept the direction of judging by the person's traits.
- **Keep questions to a minimum.** Since helping first is the core idea, the process of getting feedback from the user is kept to a minimum.
- **A question I left for myself.** How is this different from PAM with just an added prompt?
- **Status.** I got as far as the design and a presentation; no experiment was run. → [notes](notes/)

### 4. Reading reactions after helping — inverse planning (November 1–6)

- **The problem.** How can preferences be learned from behavior without asking in words? If you force a person's mind into predefined reasons (such as "dislikes the robot coming close"), you learn the wrong thing when the person acted for an entirely different reason.
- **My thinking.** Watch the person's behavior after the robot helps, and work backward to estimate what that behavior originally aimed for (inverse planning). I lowered the goal from "discovering preferences" to "learning help rules."
- **Preparation.** For the inverse planning experiment, I designed and filmed 10 videos of someone being handed a drink while studying. I filmed four reactions (drinks right away, drinks after a delay, refuses by shaking their head, refuses by putting it back where it was) in two situations. The reaction types were kept only as the answer key for evaluation and were not given to the model.
- **Experiment.** Before running on the videos, I first compared three methods on 15 scenes written as text (the scenes were written and graded by AI). Reading the whole log and answering directly got 10 right, organizing it into state changes got 8, and inverse planning got 6.
- **Decision.** Inverse planning scored lowest, so I didn't go on to the video experiment. I dropped inverse planning, and later experiments gave the model the entire observation log and had it decide directly.
- Folder: [2026-11-06_intent-inference-comparison](2026-11-06_intent-inference-comparison/)

### 5. What counts as a trigger? — appliance signals and trigger criteria (November 5–11)

- **The problem.** When I tested with two scenes in which the fridge door was left open, the model created the rule "when the alarm sounds, close the door" but left out the condition "the person has left." That rule would close the door even while the person was still using the fridge. I saw choosing only reliable triggers as the core of this research.
- **Appliance signals as triggers too.** For a signal the machine reports (laundry done), look at what follows; for a signal a person operates (turning on the air conditioner), look both before and after. The question that decides whether something is a trigger is: "If the robot does the task instead, does this event still happen?"
- **Criteria for choosing triggers.** The event closest to the action; within 10 minutes; exclude motions repeated many times within the same stage (such as putting down utensils); record the same event under the same name.
- **After the robot helps.** Detect tasks the robot missed, watch reactions for 5 minutes after helping, and classify the strength of the reaction (undoing, blocking, refusing verbally).
- **Status.** I got as far as the design, four weeks of appliance logs, and an answer key, but did not run them through the model.
- Folders: [2026-11-08_fridge-door-two-scenes](2026-11-08_fridge-door-two-scenes/), [2026-11-10_appliance-signals-4-weeks](2026-11-10_appliance-signals-4-weeks/)

### 6. What the robot can do — atomic actions (November 5–12)

- **My thinking.** Break a task like "bring a cup" into 9 atomic actions (move, look, open, close, pick, place, operate appliance, query appliance, wait). Appliances that differ by model sit behind a common interface.
- **Experiment design.** I designed an experiment comparing three methods (leave it directly to the AI / have the AI write a rule table first / a classical planner) on the same 49 problems. I ran only the classical planner, and it solved all 49.
- **Decision.** I stopped there to focus the remaining time on habit-based decisions.
- Folder: [2026-11-11_atomic-action-composition](2026-11-11_atomic-action-composition/)

### 7. Separating chance from habit — adoption test (November 9–16)

- **The problem.** PAM turns even something seen on a single day straight into a rule. In fact, in the four-day videos, a rule "when the person sits at the desk, bring the bowl," created from day 3 alone, made the robot choose the bowl action on day 4 even while the person was sitting and looking at their phone (13 seconds).
- **First criteria.** At least 4 times on different days, and the same action in that situation at least 80% of the time. Conditions such as day of the week and weather were added on top, and attaching a condition required a chance probability (p-value) below 0.001 to pass. Running this on 50 virtual logs, the number of logs that produced false rules dropped from 20–24 to 1. (The simulation code for the 50-run virtual-log test no longer exists; only the results remain.)
- **Does it hold up in reality?** A test with 200 virtual people living for 12 weeks revealed two holes. Rules without conditions skipped the chance test, so false rules remained; and because days when the robot did the task were dropped from the calculation, wrong rules never got corrected. I also found a flaw in which habits with plenty of evidence, such as one done only on Mondays, Wednesdays, and Fridays, were actually adopted later.
- **Simplify.** I left PAM as is and decided to filter only the trigger candidates produced by self-reflection, using "follow-through rate of at least 80% and chance probability below 0.1%." Context conditions were dropped from this version.
- **Fixing how things are counted.**
  - Only the last candidate right before the action is counted as "followed by the task." This prevents candidates from inflating when utensils are put down several times.
  - The synthetic logs differed from real life (putting the spoon down only once a day, for example). I rebuilt them using real observation logs as a model.
  - A 16-hour daily log caused problems by pulling in stages that are not in the paper. I cut it down to 1 morning hour × 5 days to match the paper's setup.
- **Results.** Running 5 days with a real AI filtered out 10 weakly supported signals and got 3 of 6 robot tasks right.
- Folders: [2026-11-12_adoption-criteria-realism-test](2026-11-12_adoption-criteria-realism-test/), [2026-11-14_synthetic-logs-7-days](2026-11-14_synthetic-logs-7-days/), [2026-11-15_synthetic-logs-5-weekdays](2026-11-15_synthetic-logs-5-weekdays/), [2026-11-16_synthetic-logs-morning-1-hour](2026-11-16_synthetic-logs-morning-1-hour/)

### 8. Late signals and the same moment — with real videos (November 16–18)

- **The problem.** A motion like "walks toward the curtain," where the person has already started moving to do the task, passed as a trigger. It is a late signal — too late for the robot to help first.
- **Decision.** I redefined the moment an action begins as "the moment the person starts walking to do the task." All 3 late signals were filtered out, and it got 4 of 6 robot tasks right plus 1 half right. Because the AI discarded a signal in the answer key (3 times out of 4), I adjusted the criterion to 75%.
- **Real videos.** Four real videos recorded by teammate Junhyeong Kim at my request were transcribed by AI at one line per second, then reviewed and finalized by hand. I appended them after synthetic scenes written in the same style (eating a meal, canned coffee).
- **Counting the same moment more than once.** I first grouped the log into chunks of "what the person is doing" (activity chunks). Robot tasks found went from 2 of 4 to 3 of 4.
- Folder: [2026-11-18_real-video-cup-clearing](2026-11-18_real-video-cup-clearing/)

## What went into the final product (noonchi)

- **Moved to the team server (noonchi).** The paper's 7 decision and reflection prompts; the adoption test (follow-through rate of at least 75%, chance probability below 0.1%, 5-minute window, floor (minimum base rate) of 1%).
- **"Learning habits" in the final product's README.** The day's log is grouped into activity chunks, and if a task follows a signal within 5 minutes at least 75% of the time with a chance probability below 0.1%, the signal goes into the next day's rule table.
- **Results table in the final product's README.** Scores from the four-day routine experiment (with memory 0.41 / without 0.04, etc.).

## Open problems

- **When triggers overlap in time.** In what order to handle several triggers from one person, or triggers from several people (scheduling).
- **When the robot isn't working alone.** A real home has many devices, such as robot vacuums and air conditioners.
- **Estimating each person's intervention preferences without asking.** This is the question that stalled at intrusiveness and inverse planning.
- **Getting self-reflection to look back on the robot's own decisions.**
- **Counting candidates that say the same thing in different words as one.**
- **Running the same experiment several times to check how much the results vary.**

## Experiment list

| Date | Experiment | Inputs | One-line result | Folder |
|---|---|---|---|---|
| **Real videos** | | | | |
| 11-04 | Does memory help? | 4 days of routine videos I recorded myself | With memory 0.41 / without 0.04 (day 2) | [2026-11-04_four-day-routine-videos](2026-11-04_four-day-routine-videos/) |
| 11-18 | Real-video cup clearing | 4 real videos recorded by teammate Junhyeong Kim at my request + synthetic log | Grouping into chunks: 2 of 4 → 3 of 4 | [2026-11-18_real-video-cup-clearing](2026-11-18_real-video-cup-clearing/) |
| **Text-based experiments** | | | | |
| 11-06 | Inferring what the person wanted | 15 text scenes | Reading the whole log 10 > state changes 8 > inverse planning 6 | [2026-11-06_intent-inference-comparison](2026-11-06_intent-inference-comparison/) |
| 11-06–07 | How to write a rule's "action" | Hand-written evening log | A fixed template loses the order of the steps | [2026-11-06_task-planner-pilot](2026-11-06_task-planner-pilot/) |
| 11-08 | Two fridge-door-open scenes | 2 text scenes | The rule was missing the "person has left" condition | [2026-11-08_fridge-door-two-scenes](2026-11-08_fridge-door-two-scenes/) |
| 11-12 | Adoption criteria realism test | Numerical simulation (200 people × 12 weeks) | Found 2 holes | [2026-11-12_adoption-criteria-realism-test](2026-11-12_adoption-criteria-realism-test/) |
| 11-14 | Synthetic logs, 7 days | Text logs | All 84 cells from the calculation code matched the answer key | [2026-11-14_synthetic-logs-7-days](2026-11-14_synthetic-logs-7-days/) |
| 11-15 | Synthetic logs, 5 weekdays | Text logs | All 60 cells matched the answer key | [2026-11-15_synthetic-logs-5-weekdays](2026-11-15_synthetic-logs-5-weekdays/) |
| 11-16 | Synthetic logs, 1 morning hour | Text logs + real AI | Filtered out 10 weak signals; 3 of 6 → 4 of 6 + 1 half | [2026-11-16_synthetic-logs-morning-1-hour](2026-11-16_synthetic-logs-morning-1-hour/) |
| 11-22–25 | Saturday evening, TV and beer (weekday/time context) | 3 weeks of synthetic evening logs + real AI (Qwen3.5-27B) | 2 of 12 runs learned both rules for Saturday 18–21h; chunking failed in every run | [2026-11-22_beer-saturday-context](2026-11-22_beer-saturday-context/) |
| **Prepared but stopped** | | | | |
| 11-02 | Drink-handoff reaction videos (for inverse planning) | 10 videos I designed and filmed | Stopped before the video experiment because inverse planning scored lowest in the text-scene comparison | Only the video list file is included (videos not uploaded) |
| 11-10 | Appliance signals, 4 weeks | 28 days of logs and an answer key | Not yet run through the model | [2026-11-10_appliance-signals-4-weeks](2026-11-10_appliance-signals-4-weeks/) |
| 11-11 | Combining atomic robot actions | 49 problems | Only the classical planner was run: 49/49 | [2026-11-11_atomic-action-composition](2026-11-11_atomic-action-composition/) |

## Also included

- **"Intended behavior" figure (11-12).** The actual result was "when the person sits at the desk, bring the cup," but I judged "when the person starts eating, bring the cup" to be correct and redrew the figure myself to show the target. It shows intended behavior, not an experiment result.
- **Notes.** Designs I thought through in depth but didn't take as far as an experiment → [notes](notes/)
