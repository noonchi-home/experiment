# 6. Atomic actions and task planning (November 5–12)

## What was the problem

What PAM's judgment outputs is a single goal, such as "bring a cola from the fridge." For the robot to actually move, this goal has to be turned into a sequence of motions such as "go to the fridge → open the door → pick up the cola → …". If the result ends as a line of text, it does not connect to a real robot.

The same goal calls for a different sequence depending on the state of the home at that moment.

- If the fridge door is already open, the "open" step must be dropped.
- If it is unknown whether there is beer in the fridge, the robot must look first.
- If the washing machine is still running, its door cannot be opened, so the robot must wait until it finishes.
- If the robot is already holding a cup, it must put it down before it can pick up the beer.

What appliances can do differs by model. As Jeong-O Heo pointed out at the November 6 all-hands meeting, some fridge models can close the door through the connection and some cannot. If not, the robot has to go and close it itself. And the robot must not answer that it can do things it cannot (hanging laundry, folding a blanket).

## How I thought about it

### Breaking tasks into atomic actions (November 6–10)

At the November 6 meeting we agreed to attach task planning (breaking a goal into a sequence of motions) after the judgment. The robot splits a task into the smallest motions (atomic actions) and then combines them to carry it out. We decided to first write pseudocode (the steps written out in plain text before writing real code), for example "go (current position → fridge), open (fridge), pick up the cola if it is there, otherwise return that result," and to make it concrete later.

In the November 8 design summary I laid out the overall structure as follows.

```
① 1-second judgment (PAM): what is it time to help with now → one goal (e.g., bring something to drink)
② Probability part: if it is a drink, cola or milk
③ Task planner: goal → sequence of atomic actions
④ Execute → if it fails, decide what to do instead
```

- I define the atomic actions myself, and for each motion write "what it does / what it needs first / result."
- Navigation is left to a navigation implementation, like the navigation stacks used in practice (Nav2 in ROS 2, which plans paths, avoids obstacles using sensors, and runs recovery behaviors such as backing up when stuck). The task planner only receives the result of navigation (success, or failure and the reason). I could not confirm whether LG CLOiD uses Nav2.
- I first tested how to write actions on November 6 (one handwritten daily log, 3 runs per method). When the model filled in blanks in three fixed templates, multi-step tasks were split into several rules with the same trigger and lost their order (8, 6, and 12 rules). When it wrote freely, but in a form that could be broken into atomic actions, one task became one rule with its steps in order (5, 5, and 5 rules).

On November 10 I fixed the motions at nine and wrote them into the team server code (noonchi) as an interface (an agreement on which motion is called with which inputs and what it returns). I added "wait" to the eight on the November 8 list.

| Motion | What it does | When it counts as done |
|---|---|---|
| Go (`go`) | Goes to the front of the destination | When the actual arrival position is confirmed. If it is blocked in the end, it returns failure and the last position |
| Look (`look`) | Checks whether the target is within an area | "Not there" only after the whole area has been checked |
| Open (`open`), Close (`close`) | Opens and closes doors that can be operated | When a door sensor or camera confirms open or closed |
| Pick (`pick`), Place (`place`) | Picks up an object with an empty hand; places a held object in an empty spot | When the grasped object, or the placed object and the empty hand, are confirmed |
| Set appliance (`set`) | Sends a command from that appliance's command list | When the state after the command matches the request |
| Read appliance (`read`) | Reads the current value or past records of an appliance item | When the value is received together with the time it was actually confirmed |
| Wait (`wait`) | Waits until a condition becomes true or that appliance sends a signal | When the condition becomes true. Failure if the time limit is exceeded |

In settling this table I weighed four points.

- **There are five outcomes.** Done, failed, could not confirm, not supported, cancelled. Unless the outcome is "done," the plan does not move on to the next motion. "Done" records the confirmed result together with the time and source (sensor, camera, twin) of the actual confirmation.
- **Separate "did not see" from "saw, and it was not there."** Look records "not there" only after seeing the whole area. If the view was blocked or the area was out of sight, the result is "could not confirm." Mixing the two leads to judging that there is no beer when there is.
- **Recheck the current state right before execution.** Even after the trigger arrives, the robot checks the stock, whether the user has already started, and the current state of the target before moving (November 9 design). It brings the beer only if there is beer and the user has not gone to get it yet.
- **A separate wait is needed.** A running washer or dishwasher cannot be opened. "Take out the laundry when the wash is done" must be planned as "wait for the stop signal, then take it out." Asking it to wait for a signal that the appliance does not send returns "not supported."

### Hiding appliances that differ by model behind a common interface (November 10)

- Each appliance gets its own driver (code that communicates with the actual device), and the task planner finds that driver by device ID. The driver reports its installation ID, appliance type, model, and firmware (the software inside the device) version.
- Properties such as door-open are called by common names, and each manufacturer's different signal names and values are translated inside the driver. Since the same property may be available only by query or only as notifications depending on the model, I made query, notification, and history separately optional. Read-only devices can also be represented.
- I decoupled it from the 11 commands that had been hard-coded in the twin (a digital model of the home on screen) server. Each model registers the command names and input formats it supports; unregistered commands return "not supported," and inputs outside the allowed range return "failed." I confirmed by test the case where washers of the same type offer different courses depending on the model.
- Drivers for real appliances will be attached later. We agreed that Jeong-O Heo would handle the appliance drivers and the digital twin side would handle per-model appliance information.

### Relationship to task-planning methods

- The condition table listing, for each motion, "what it needs / what it removes / what it creates" has the same shape as classical task planning (STRIPS (1971) and PDDL: you give the current state, the goal state, and each action's conditions and effects, and the computer finds a sequence of actions). If no sequence is found, the answer is "cannot do."
- Task planning handles only "how." It does not handle "when to do it" or "whether the person wants it"; PAM's judgment and the triggers take care of those. It also does not handle fine-grained motion such as arm movements or paths, which are left to the navigation and grasping implementations.

### What to bring: choosing by probability (November 8)

Whether to bring something is decided by the FSM (a rule table that splits the day into stages and attaches help rules to each stage); the probability part only chooses what to bring. Even if there is only one record, the robot brings that drink. The score adds up the records, each multiplied by a weight that depends on how many days ago it was (a value multiplied in for each day that passes).

| Value multiplied per day | Cola, 5 times (3–7 days ago) | Milk, 2 times (today, yesterday) | Choice |
|---|---:|---:|---|
| 1 | 5 | 2 | Cola |
| 0.9 | 2.99 | 1.9 | Cola |
| 0.8 | 1.72 | 1.8 | Milk |

The multiplier has to be set separately, and days when milk was drunk because there was no cola have to be marked separately using the fridge records. I only settled the calculation method; I found no record of implementing or testing it.

### Designing a three-method comparison (November 10–11)

Rather than deciding right away who would produce the sequence, I decided to compare three methods on the same problems. The comparison checks whether atomic actions are combined in the right order, and whether tasks that can and cannot be done are told apart.

| Method | What it does |
|---|---|
| Hand it straight to the AI | Give a description of the home, the problem, and the motions, and have it write the motion sequence directly |
| AI writes a rule table (FSM) first | Have it first write a rule table that divides the task into subtasks and transition conditions, then convert that table into a motion sequence. The idea comes from the paper approach of building an FSM first and then turning it into code |
| Classical planner | Tries attaching possible motions one at a time according to the condition table and finds the shortest sequence that reaches the goal state. It does not call the AI |

- I made 49 problems: 25 robot actions that appeared in the rule list of the 4-week virtual log, 8 actions the robot cannot do (folding a blanket, wiping the table, etc.), and 16 tricky variants (door already open, already holding a cup, TV command without a channel, unknown whether there is beer, etc.). The answer key has 33 doable, 15 not doable, and 1 knowable only after looking.
- I took the condition table from code comments and froze it on November 11. It is a table a person sets in advance, not one the AI writes. Conditions I added because they were not in the comments (an object behind a door can be picked only if that door is open, etc.) are marked separately.
- For the two AI methods I prepared one version given only the motion descriptions and one also given the condition table, and chose DeepSeek as the model.
- Scoring: the answer's sequence is executed step by step according to the condition table, and it is correct if the goal state results. For tasks that cannot be done, the answer is correct only if it says so.

## How far it got

- **Two interface files** (atomic actions, appliance driver) created on a local noonchi branch. Type checking and 2 tests passed; not committed. No real driving, appliance connection, or hardware execution.
- **Of the comparison, only the classical planner was run.** It got all 49 right (15/15 on impossible tasks, 0 claims of doing what it cannot, 0 execution failures) in 2.4 seconds. The two AI methods were never called, so there is no result comparing the three methods.
- **What I found while making the problems.**
  - Of the 25 robot actions in the 4-week answer key's rule list, 4 could not be done with the nine motions: getting water from the water purifier (the purifier is not an operable appliance, and there is no motion for filling with water), hanging laundry, laying out a waterproof mat, and folding a folding table (moving it is possible, but there is no motion that changes an object's shape).
  - The classical planner and the scoring program use the same rule code. 49/49 means the planner does not contradict the condition table, not that the condition table matches a real robot.
  - In the problem with a side-dish container caught in the fridge door, the goal left out where the container should end up, so an answer that closes the door while still holding the container also counted as correct.
- **Why it stopped.** On November 12 I postponed atomic-action composition and the appliance interface and decided to spend the remaining time on habit judgment (context conditions and chance probability). The actions the robot can do were fixed to a predefined list (10 in the November 14 design).

## Open questions

- Whether handing it straight to the AI, or having the AI write a rule table first, gets as many right as the classical planner, and says that impossible tasks are impossible, remains unchecked.
- Does the condition table match a real robot? I added conditions not in the comments, such as reading "reachable" in the comments as "at the standing spot for that location."
- Whether to add motions that change an object's shape, such as hanging, spreading, folding, and pouring, or leave them to people.
- How to replan when the state changes during execution or is unknown from the start. This time I looked at it only through one problem, "unknown whether there is beer," solved in advance by splitting it into the case with beer and the case without.
- How to set the per-day multiplier when choosing by probability.
- When attaching the appliance drivers to real LG devices (ThinQ, LG's appliance connection service), where to get the commands and signals each model supports.

## Related

- Experiment folders: [2026-11-06_task-planner-pilot](../2026-11-06_task-planner-pilot/), [2026-11-11_atomic-action-composition](../2026-11-11_atomic-action-composition/)
- Note [5. Appliance signals and trigger finding](05_appliance-signals-and-trigger-finding.md): the same period, on "when to help." The home and actions in the comparison came from the 4-week appliance log.
- Note [11. Open questions](11_open-questions.md): a home where several devices work together, not a robot alone

## Sources

- `seokjun/notes/sources/설계문서/2026-11-08_작업계획기_가전도움_설계정리.md` (task planner and appliance-help design summary: ch. 1 structure, ch. 4 atomic-action pseudocode and navigation, ch. 6–7 how to write actions, ch. 10 probability part)
- `seokjun/notes/sources/ai-collab/codex_atomic_actions_2026-11-10.md`, a work handoff note (not in this repository) (interface work; the change that decoupled the 11 commands)
- `noonchi/src/contract/atomic-actions.ts`, `noonchi/src/contract/appliance-driver.ts` (branch `feat/atomic-action-interfaces`, not committed)
- `seokjun/2026-11-11_atomic-action-composition/problems/원자행동_설명.md`, `seokjun/2026-11-11_atomic-action-composition/problems/원자행동_조건표.md` (descriptions of the nine motions and the frozen condition table)
- `seokjun/2026-11-11_atomic-action-composition/answer-key/검토용_요약.md` (summary for review: the 49 problems and their answer key)
- `seokjun/2026-11-11_atomic-action-composition/data/결과표_본.md` (results table)
- `seokjun/notes/sources/설계문서/2026-11-14_트리거_채택기준_80퍼센트와_p-value.md` section 1 (trigger adoption criteria: 80% and p-value; robot actions fixed to a list of 10)
- Team meeting minutes: `02_Meetings/2026-11-06_전체회의록.md` in `noonchi-home/docs` (November 6 all-hands minutes: the proposal to add task planning; closing the fridge differs by model)
- Conversation logs (content summarized, not quoted): Claude conversation, November 10–12 (explanation of task-planning methods, three-method comparison, the decision to stop)
