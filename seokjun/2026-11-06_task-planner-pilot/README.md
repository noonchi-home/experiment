# Task Planner Pilot — How Should Rules Write Their Actions? (2026-11-06)

## Summary

For the nightly self-reflection, I compared two ways of writing the "action" part of a rule: filling in one of 3 fixed templates, or writing freely as long as the text can be broken down into the robot's atomic actions. I ran each 3 times on the same day log. Templates split multi-step tasks into several rules with no order (8/6/12 rules), while free form wrote each task as one rule (5/5/5).

## Why I ran this experiment

- I decided to attach a task planner (the part that breaks a goal such as "bring something to drink" into a sequence of the robot's atomic actions) after the PAM decision step (the part that picks, at each moment, what to help with now). The first version handles only appliance-related help.
- For that, the nightly reflection (the step that reads the day's log and builds rules for the next day) has to write each rule's action in a form the task planner can accept.
- There were two options.
  - **Template:** only fill in the blanks of 3 fixed sentence templates (operate an appliance / take something out of an appliance and put it somewhere / take something from somewhere and put it into an appliance).
  - **Free:** write natural sentences, but they must be decomposable into a sequence of the robot's atomic actions (move, open/close a door, check an object, pick up, put down, control an appliance over its network connection, read an appliance's state).
- I decided to compare the two experimentally.

## What I did

### The day log

- One English log covering about 45 minutes in the evening (18:58–19:45), written by hand as text with no video. It has 7 scene lines and 12 appliance-signal lines, 19 lines in total.
- Each appliance-signal line is tagged with who caused it (the appliance itself / a person).
- What it contains:
  1. Comes home and turns on the air conditioner (29°C indoors, set to 26°C)
  2. Takes a cola out of the fridge and puts it on the table next to the sofa. Sits down on the sofa, leaving the fridge door open
  3. After a signal that the fridge door has been open for 1 minute, gets up and closes the door
  4. After the wash finishes, moves the laundry to the dryer and starts the dryer
  5. Takes milk out of the fridge, pours it into a cup, and puts it back
  6. Puts the empty cup in the dishwasher

### Runs

- Model: Qwen3.5-27B (via OpenRouter, pinned to a single Alibaba server), temperature 0.3 (randomness of the answers; lower means less variation), thinking on.
- Of the nightly reflection, I ran only the "initial build" step (building first-day rules with no memory).
- The two methods' prompts differ only in the part about how to write actions. What each appliance can do, the list of allowed names, and how to read appliance signals are the same.
- 3 runs per method, 6 in total. All 6 finished normally and their outputs were readable. The 6 runs cost about $0.10 in total.

## Results

Whether each help was captured as a rule (○ captured, △ captured but with a problem, × not captured). The trigger is the signal that makes a rule run.

| Help | Template 1 | Template 2 | Template 3 | Free 1 | Free 2 | Free 3 |
|---|---|---|---|---|---|---|
| Turn on air conditioner | ○ | ○ | ○ | ○ | ○ | ○ |
| Cola from the fridge | △ trigger is "approaches the fridge" | × | ○ | ○ | ○ | ○ |
| Close the open fridge door | ○ | ○ | ○ | ○ | ○ | ○ |
| Laundry → dryer | ○ | ○ | × puts it next to the person | ○ | ○ | ○ |
| Start the dryer | ○ | △ same trigger, no order | △ same trigger, no order | ○ | ○ | ○ |
| Milk (fetching only) | △ | × | × | × | × | × |
| Cup → dishwasher | ○ | ○ | ○ | ○ | ○ | ○ |
| Number of rules | 8 | 6 | 12 | 5 | 5 | 5 |

The grades were assigned by an AI (Claude) after reading the outputs.

## What I found digging into the results

1. **Templates split multi-step tasks into several rules on the same trigger and lost the order.** In Template 3, five rules hung off the single trigger "wash finished" (open the washer door, take out the laundry and put it next to the person, open the dryer door, close the dryer door, start the dryer). Nothing says which to do first. In Template 2 as well, moving the laundry and starting the dryer were attached separately to "wash finished."
2. **Free form wrote each task as one rule, with the steps in order.** Example: "wash finished → open washer, pick up laundry, put it in the dryer, close dryer, start dryer." All three runs produced the same number of rules, 5.
3. **Milk was missed in 5 of the 6 runs.** The prompt said that if the robot cannot do the whole task (pouring milk), it should write only the part it can do, but only Template 1 wrote "take out the milk and put it next to the person."
4. **No air conditioner rule used both "came home" and "29°C indoors."** All 6 runs used only one of the two as the trigger. The prompt merely allowed triggers that mix a person's action with an appliance state; it did not say when both should be considered together.

### Coffee prompt test (2026-11-07)

I ran prompts for building rules that move between states (eating → after eating) once each with the same model.

- **First test.** The prompt contained the state sequence (before eating → eating → after eating), a user preference (wants coffee ready in advance for after the meal), two observation lines (clears the meal dishes, then washes those dishes), and a decision criterion. The criterion said to move to the next state once both observations are confirmed, and to "include both observation conditions in the trigger."
  - Result: trigger "clearing meal containers from the dining table completed AND washing of those containers at the sink started," action "prepare coffee in advance."
  - The AND rule, which requires both, came out because the prompt demanded both conditions. Since the prompt nearly spelled out the trigger and action, the test ended up checking whether the model followed the criterion, not whether it found the rule on its own.
- **Second test.** I changed the first rule's trigger to an OR form, where either condition is enough, gave it as an existing rule, and with no observations asked the model to "propose one more rule that comes after it."
  - Result: "after eating → before eating," trigger "coffee cup placed in sink detected OR 30 minutes elapsed after the meal ends," action "switch kitchen lighting and appliances to standby mode, activate next-meal schedule reminder."
  - With no observations, it invented ungrounded conditions and actions such as "30 minutes elapsed."
- The two runs cost about $0.006 in total.

## Limitations and next steps

- One day log, with only 3 runs per method.
- The grades were assigned by an AI (Claude) after reading the outputs.
- I looked only at the first-day "initial build." I did not check whether the rules it built actually help on the next day.
- In the coffee test, the prompt nearly dictated the answer, and each prompt was run only once.

The next step is to rewrite the coffee scenario as two cases: "a day when coffee is taken out of the fridge / a day when it is brewed with the coffee machine." I only made the plan and did not run it.

## Files

| File | Contents |
|---|---|
| `day_log.txt` | The evening day log (English; scene lines and appliance-signal lines) |
| `prompt_base.txt` | Prompt shared by both methods (method-specific parts left blank) |
| `prompt_template.txt`, `prompt_free.txt` | Complete prompt for each method (template / free) |
| `run_spike.py` | Code that runs each method 3 times |
| `out/template_1~3.json`, `out/free_1~3.json` | Raw model responses and the rules produced |
| `coffee_prompt.txt`, `coffee_next_prompt.txt` | Coffee test prompts (first rule / next rule) |
| `run_coffee.py`, `run_coffee_next.py` | Coffee test code |
| `out/coffee_1.json`, `out/coffee_next_1.json` | Coffee test responses |

Rerunning the code makes paid model calls and overwrites the results in `out/`.
