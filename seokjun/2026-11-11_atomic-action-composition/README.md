# Composing the Robot's Atomic Actions — Can Nine Actions Break Down Household Tasks Correctly? (2026-11-11)

## Summary

I designed a comparison of three ways to compose the robot's nine atomic actions into tasks such as "bring the beer from the fridge to the sofa table" (asking the AI directly / having the AI write a rule table first / a classical planner), using the same 49 problems. I ran only the classical planner, and it solved all 49 (2.4 seconds). I stopped without running the two AI methods.

## Why I ran this experiment

- When the PAM decision outputs a single goal such as "bring something to drink," something has to break that goal down into the sequence of actions the robot actually performs (a task planner).
- I decided to define the atomic actions (the smallest basic actions the robot can perform) myself.
- I wanted to check two things:
  1. Does it combine atomic actions in the correct order?
  2. Does it recognize tasks that cannot be done as impossible?

## What I did

### The robot's nine atomic actions

I took these from the comments that define atomic actions in the team's server code (noonchi). The robot can do only the nine actions below.

| Action | What it does |
|---|---|
| `go` | Goes to the front of a destination |
| `look` | Checks whether a target is within range |
| `open` | Opens an unlocked door |
| `close` | Closes a door if the space it closes is clear |
| `pick` | Picks up an object when the hand is empty |
| `place` | Puts the held object down in a free spot |
| `set` (appliance control) | Sends a command that is in that appliance's command list |
| `read` (appliance query) | Reads the current value of an appliance field |
| `wait` | Waits until a condition becomes true or an appliance signal arrives |

- On November 11 I froze a condition table that lists, for each action, "what it needs / what it removes / what it creates."
- Some conditions were not in the comments, so I added them. For example, an object behind a door can be picked up only if that door is open.

### 49 problems

I built the house from the 9 observed locations and the 16 signal-sending appliances in the 4-week appliance-signal data.

| Group | Count | Examples |
|---|---:|---|
| Robot actions from the rule list in the 4-week data | 25 | Bring the beer from the fridge to the sofa table; turn on the bedroom reading lamp |
| Actions the robot cannot do | 8 | Fold the blanket; wipe the dining table; chop ingredients |
| Tricky variants | 16 | Fridge door already open; robot already holding a cup; no channel command for the TV |

- The answer key has 33 doable, 15 not doable, and 1 "must look to know." The "must look to know" problem is one where it is unknown whether there is beer in the fridge; it counts as correct only if the answer is right both when the beer is there and when it is not.
- I left the group names out of the problem file, because a group name would give away the answer.
- For each problem, the answer key records whether it is doable, why, and one example of a correct sequence. I checked every example sequence step by step against the frozen condition table, and all of them passed.
- I set aside 5 separate practice problems used only for refining the prompts.

### The three methods to compare

| Method | What it does | Run? |
|---|---|---|
| Ask the AI directly | Gives the AI the house, the problem, and the action descriptions, and has it write the action sequence directly | Not run |
| AI writes a rule table (FSM) first | Has the AI first write a rule table (FSM) that splits the task into subtasks and the conditions for moving between them, then convert that table into an action sequence | Not run |
| Classical planner | Starting from the current state, tries adding actions the condition table allows, one at a time, and finds the shortest sequence that reaches the goal state. Does not call the AI | Run |

- For both AI methods I prepared one version that gives only the action descriptions and one that also gives the condition table. I chose DeepSeek as the model.
- Scoring works like this. For a doable task, the answer's sequence is executed step by step according to the condition table, and it is correct if the goal state is reached. For a task that cannot be done, the answer is correct only if it says the task cannot be done.

## Results

| Item | Classical planner |
|---|---|
| Total correct | 49/49 |
| Not-doable tasks correct | 15/15 |
| Said doable when it is not | 0 |
| Said not doable when it is | 0 |
| Execution failures | 0 |
| Time taken | 2.4 s |

I never called the two AI methods, so there is no result comparing the three methods.

## What I found digging into the results

1. **4 of the 25 robot actions from the rule list in the 4-week data could not be done with the nine actions.**
   - Fill a cup with water from the water purifier and put it on the dining table: the water purifier is not an operable appliance, and there is no action for filling a cup with water.
   - Hang laundry on the drying rack, lay a waterproof mat by the window, fold up the folding table: carrying the item is possible, but there is no action that changes an object's shape, such as hanging, spreading, or folding.
2. **Only two problems took long.** Taking a mat out of a locked storage cabinet took 1.46 seconds, because the planner judged it impossible only after searching the whole house. A 16-step problem that moves four utensils one at a time took 0.70 seconds. The other 47 each took under 0.15 seconds.
3. **One problem had an underspecified goal.** In the problem where a side-dish container is stuck in the fridge door gap (C09), the example answer is 4 steps: move the container into the fridge, then close the door. The classical planner gave a 3-step answer that closes the door while still holding the container, and it was scored correct because the goal did not say where the container should be.

## Limitations and next steps

- I did not run the two AI methods, so I could not compare the three methods.
- The classical planner and the scorer use the same rule code (`world.py`). 49/49 means the planner does not contradict the condition table; it does not mean the condition table matches the real robot.
- The condition table includes conditions I added because they were not in the comments.
- Where the data said nothing, I made choices. I decided the string is in the drawer next to the dining table, and because the water purifier is not on the list of signal-sending appliances, I treated it as a fixture that cannot be operated.
- Some problems, like C09, have underspecified goal states.

I stopped here and decided to spend the remaining time on habit-based judgment.

## Files

**Experiment code and results.** In this folder.

| Folder / file | Contents |
|---|---|
| `code/world.py` | Rules that read the house definition and the problems and step through actions according to the condition table. Shared by the classical planner and the scorer |
| `code/planner.py` | The classical planner. Finds the shortest sequence and filters out impossible tasks in advance |
| `code/score.py` | The scorer, which checks answers against the answer key. This is the only file that reads the answer key |
| `code/check_scorer.py` | Tests for the scorer. Checks that example answers are scored correct and deliberately wrong answers are scored wrong |
| `code/llm.py`, `code/prompts.py`, `code/run_llm.py` | Code for running the two AI methods with DeepSeek (model calls, building the text sent to the model, running). Never run |
| `data/결과표_본.md` (results table) | Results table (classical planner only) |
| `data/계획기_본.jsonl` (planner answers) | The planner's 49 answers |
| `data/계획기_본_실행기록.txt` (planner run log) | Per-problem decision, number of steps, and time taken |
| `data/미리보기_글.txt` (text preview) | Preview of the text to be given to the AI methods. The model was not called |

**Problems (seen by all three methods).** In `seokjun/2026-11-11_atomic-action-composition/problems/`.

| File | Contents |
|---|---|
| `집.json` (house) | Standing spots, placement spots, doors, and appliances with their initial state, plus house rules |
| `문제.jsonl` (problems) | The 49 main problems (task, initial state, goal state) |
| `연습문제.jsonl` (practice problems) | The 5 practice problems used only for refining prompts |
| `원자행동_설명.md` (action descriptions) | Descriptions of the nine actions only |
| `원자행동_조건표.md` (condition table) | The frozen condition table |

**Answer key (scoring only).** In `seokjun/2026-11-11_atomic-action-composition/answer-key/`.

| File | Contents |
|---|---|
| `정답.jsonl` (answer key) | Whether each task is doable, why, an example sequence, and both cases for the "must look to know" problem |
| `연습정답.jsonl` (practice answer key) | Answer key for the practice problems |
| `검토용_요약.md` (review summary) | Summary of the problems and answers for human review |
