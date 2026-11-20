# Fridge Door Open, Two Scenes — Same Alert, Different Situations (2026-11-08)

## Summary

I gave the model two scenes separately, each with the same "fridge door open" alert, and had it build rules. The scene where the person walked away produced 1 rule, "alert sounds → close the door," and the scene where the person keeps taking things out produced 0 rules. But the first rule is missing the condition "the person has left," so it would misfire in a situation like the second scene.

## Why I ran this experiment

- To use appliance signals as triggers (the signals that make a rule run), I need to be able to tell, for the same signal, when to help and when to wait.
- The fridge door-open alert is such a signal. If the person left with the door open, the robot closing it is help; if they are still taking things out, closing it gets in the way.
- I wanted to see whether, given only observation logs and no example answers, the model would build a rule that tells these two apart.

## What I did

The two scene logs (as given to the model)

| Time | A: Leaves with the door open | B: Keeps taking things out during the alert |
|---|---|---|
| 0 s | The person takes a bottle out of the fridge | The person takes a bottle out of the fridge |
| 10 s | Leaves the door open, goes to the living room, and sits on the sofa | Stands in front of the fridge, taking ingredients off the shelves one by one |
| 60 s | The fridge door-open alert sounds | While the door-open alert sounds, is still taking out ingredients from inside |
| 80 s | The person comes back to the kitchen and closes the door | Takes out the last ingredient and closes the door themselves |

- Same model (Qwen3.5-27B, via OpenRouter, pinned to a single Alibaba server), same prompt, temperature 0.3, thinking on.
- Each scene was run once, separately, so that neither run saw the other's content.
- For each thing the person did that the robot could have done instead, the prompt had the model consider four questions.
  1. Before the person did it themselves, was there an event or state the robot could use as a start signal?
  2. Looking only up to that point, why does that cue show that this help is needed now?
  3. Is there a situation where, even with the same cue, waiting is the right call? If so, was a cue that tells the two apart already present at that point? If not, hold off.
  4. Would that start signal still have appeared if the robot had done the task instead?
- The output was a single FSM (a memory that records states, the conditions for moving between them, and the help rules for each state). No example rules or states were given.
- The two runs cost about $0.02 in total.

## Results

| Scene | States | Rules | Rule |
|---|---|---|---|
| A: Leaves | 1 | 1 | "Fridge door-open alert sounds → close the fridge door" |
| B: Keeps taking things out | 4 | 0 | None |

- Both responses finished normally and were readable.
- Whether each scene produced a rule matched what I expected.

## What I found digging into the results

1. **Rule A is missing the condition "the person has left."** Its trigger is the alert alone, so it would close the door even when the alert sounds while the person is still taking things out, as in B. Question 3 in the prompt asked for a cue that separates this from situations where waiting is right, yet that cue did not make it into the rule. This is an interpretation from reading the output; I did not actually run rule A on scene B.
2. **The first state in B's output is not in the log.** It wrote the first state as "fridge door closed, before the user approaches," but the log starts at 0 s with the person already taking out a bottle.
3. **The 60-second alert is an assumption built into the synthetic scenes.** Log A does not directly say what is happening in front of the fridge at 60 s. When, and under what conditions, a real appliance signals that the door is open needs to be checked on the model actually in use.

## Limitations and next steps

- Each scene was run only once. I did not check whether the results repeat.
- There are 2 scenes, each 4 lines of text.
- The 60-second alert timing is an assumption.

The next plan is to keep the rule built from A fixed and apply it again to three scenes that differ only in what is observed at the moment of the alert. The expected results are: close if the space in front of the fridge is empty, wait if the fridge is in use, and also wait if it is unclear whether it is in use. These three scenes were not run.

After this experiment, "choosing only triggers it can be sure of" became the central question. That question led to work on how to read appliance signals and on designing the trigger adoption criteria (the 2026-11-09 design document "Building robot help rules by observing appliance use").

## Files

| File | Contents |
|---|---|
| `run.py` | Code that sends one scene to the model and saves the response. Does not overwrite a response file that already exists |
| `a_request.json`, `b_request.json` | The full requests sent to the model (prompt, scene log, settings) |
| `a_response.json`, `b_response.json` | Model, server, token counts, cost, and response |
| `a_content.txt`, `b_content.txt` | The raw FSM text the model produced |
