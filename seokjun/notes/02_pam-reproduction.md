# 2. PAM reproduction (October 24–26)

## What was the problem

To use PAM, which I chose in note [1](01_decision-logic-and-paper-choice.md), for our question, I first had to make it behave as the paper describes. I couldn't obtain the full runnable decision code from the authors' repository, so I had to rewrite it from the paper and its appendix. When rewriting, it's easy to slip in decision rules or scores that aren't in the paper, and then you can't tell whether the results come from PAM or from what we added.

## How I thought about it

### Principle: port it as is, change only the setting and the output

- I took what the paper states, as is, as the implementation baseline.
- Details the paper doesn't give (wiring up model calls, file input and output, error handling, etc.) I filled in so as to preserve the paper's behavior, and recorded separately what I filled in and why.
- I added no probability scores, action thresholds, extra observation rules, or action priorities that aren't in the paper. Swapping in a different model was also kept out of the reproduction path.
- I changed two things: the setting, from a desk to a breakfast table; and instead of moving a robot arm, the system shows the chosen action as text.

### What I kept from the paper

| Item | Paper setting |
|---|---|
| Prompts | The 7 prompts in the appendix. 3 for decisions (no memory, list memory, stage memory) and 4 for building and revising memory (list or stage format × initial build or revision) |
| Model | Qwen3.5-27B, temperature 0.3 (the lower it is, the more similar the answers to the same input). Thinking mode (reasoning at length before answering) off for decisions, on for revising memory |
| Decision input | Five time points at 2-second intervals over the last 8 seconds. At each time point, two camera views placed side by side; the wrist camera excluded |
| Decision output | One sentence of observation, one short sentence of rationale, and an action number (-1 means wait) |
| Memory format | Initial stage, list of stages, and for each stage "when this → this help" rules and the events that move to the next stage |
| Memory use | The model reads the whole memory as reference material and chooses. Code does not force a single current stage |
| Memory revision | Memory is fixed during the day; at the end of the day it is revised using that day's observations (200 evenly sampled time points), an action summary, and user feedback if any, and is used the next day |
| Rule principles | Base rules on objects the person actually moved; don't touch objects the person is holding until they put them down; don't delete a rule just because it didn't come up today |

The prompt still contains the phrase "one frame per second," but the appendix setting is a 2-second interval. I left the original wording unchanged and kept the actual interval at 2 seconds.

### What I changed

| Item | Paper | Ours |
|---|---|---|
| Living space | One person's desk | A home with a bedroom, breakfast table, kitchen sink, and entrance |
| Actions | 6 pick-and-place actions plus wait | Put milk next to the user, put the cup in the sink, put the plate in the sink, plus wait |
| Places to put things | Next to the user, storage location, trash can | Sink added |
| Examples in the prompts | Sitting at the desk | Sitting at the breakfast table |
| Initial memory | Built and accumulated from observation | Written by a person, assuming the habits are already known |
| Execution | A robot arm model (VLA, a model that generates motion from photos and instructions) moves | The chosen action is shown as text |
| Model serving | vLLM (a server program that hosts the model directly) | The model of the same name called through OpenRouter (a broker service for using many models remotely) |

I kept the original prompts as files and saved each changed sentence separately as "original string → replacement string → reason." I recorded in a separate file the fact that the initial memory was written by a person, so it wouldn't look like memory the model had learned from observation.

## How far it got

### Faithfulness check (October 25)

Before publishing on GitHub, I checked the code item by item against the paper PDF and a pinned version of the authors' repository. The conclusion: "This is an implementation with a changed setting that reflects PAM's core decision and memory-update structure; it does not reproduce the original paper's experiments under identical conditions or reproduce its performance."

- I re-extracted the 7 prompts from the PDF and confirmed they match the saved files character for character.
- Automated program checks: 141 passed before the fixes and 143 after. These checks use fake responses to verify input assembly and saving; they are not model performance tests.

Gaps that came to light:

- There was no runner that keeps deciding every second, and no scheduled job that revises memory automatically each night. There were only tools to make individual calls and to run things split by date.
- I did not reproduce the paper's evaluation (5-day comparison; comparison of no memory, list memory, and stage memory; accuracy scores such as precision, recall, and F1; latency statistics).
- Robot execution and its success rate were outside the reproduction scope.
- I couldn't check how well memory is built from scratch from initial observations, because a person supplied the initial memory.
- I couldn't confirm whether the OpenRouter model matches the paper's vLLM environment down to weight version, quantization (storing model values at lower precision), and image preprocessing.

I judged that the README's phrase "faithful reproduction" overstated the scope and changed it, and set the public name to "PAM-based breakfast action decision experiment."

### Two things I fixed during reproduction

**1. Self-reflection wasn't actually running.** Self-reflection (the step that revises memory from the day's log after the day ends) was in the code but had never been executed. The decisions up to that point merely applied the initial rules a person had written; they weren't the result of finding rules through self-reflection. Instead of editing the initial memory by hand, I changed the flow so that the observation log and user feedback go into the paper's memory-revision prompt, and the new memory the model returns is used for the next day's decisions. Because a person gave feedback in this experiment, I decided not to describe it as the model finding habits on its own.

**2. "Get out of bed → milk" was too early a signal.** The initial memory had the rule "when the person gets up, put milk next to them." Waking up is a signal that still occurs even if the robot helps, so it didn't violate the paper's rules. But the habit of drinking milk every morning alone couldn't determine where to put the milk the moment the person got up. I treated this condition as a design mistake and redesigned the start as "when the person sits at the table." During the faithfulness check, I found the wake-up condition still left in the initial memory and split it out into a four-stage memory that starts at the table.

| Stage | Help stored in memory | Observation that moves to the next stage |
|---|---|---|
| Meal preparation | Sat at the table, no milk, not holding milk → bring milk | Starts eating or drinking |
| Eating | Don't clear dishes in use | Finishes eating and starts tidying |
| Meal finished | Watch the remaining items and the person's actions | After clearing some items, leaves through the entrance |
| After leaving | A used cup or plate is left → move it to the sink | End |

The condition for clearing was set by observations such as the meal ending, partial tidying, and actually going out — not by "no person in the photo." Mental states such as "forgot" were not put in the answer key.

### Limitations the paper states

The authors list three limitations themselves (paper, p. 9).

- An observed action may not reflect actual intent. Merely touching an object related to a help condition briefly can be taken as the start of the next activity and lead to help.
- There is no ability to ask the user when things are ambiguous. The authors say asking might be better but left it out of scope.
- Generalization to new objects, layouts, and users was checked only to a limited extent. Because of the limits of the public robot execution model, evaluation stayed within scenarios already seen.

After reading the paper's conditions, I also added my own review. The main evaluation is 5 days of one person's records at 3.5–4.5 minutes a day, so it is hard to treat as a result of long-term operation. Because memory is fixed for the day, new preferences that arise during the day aren't reflected that same day. Since both photo interpretation and memory revision rely on a VLM (a model that reads photos and text together), there is no guarantee that the resulting rules are correct.

### Layering a POMDP on top of PAM (October 26)

When a plate is left on the table and the person isn't visible, it's unclear whether the meal is over or the person has just stepped away. PAM doesn't carry this uncertainty forward; the model simply picks on the spot. So I investigated whether a POMDP could be layered on top of PAM — one that assigns a probability to each possible situation, updates it with new observations, and compares the cost of clearing too early, the cost of waiting, and the value of watching longer.

| Paper | Why I looked at it | Scope confirmed |
|---|---|---|
| Chadès et al., POMDP primer (2021) | The distinction between "not visible" and "not there"; whether to act now or gather more information | An introductory paper for applied ecology researchers. The later part requires math |
| Kostavelis et al., POMDP design for assistive robot decision-making (HCI 2017) | Defining states, actions, observations, and rewards for a home assistive robot; checking and fetching | Centered on a design framework and simulation |
| Saborío et al., active intention recognition (2025) | Estimating intention without instructions, and choosing whether to observe more or fetch a part | An assembly-parts setting. Quantitative evaluation in simulation |
| Chen et al., trust-aware planning (HRI 2018) | Treats human trust as a hidden state while clearing a table together | What is estimated is trust, not whether the meal is over or whether clearing is allowed |

The division of roles proposed in the survey document was: PAM remembers recurring procedures and help rules, the VLM extracts cues from photos, and the POMDP updates per-situation probabilities from the observation history and compares the costs of actions. But plugging in PAM's natural-language rules or using only the confidence the VLM states doesn't make it a POMDP. It needs probability models for state changes and observations, rewards and costs, probability updates, and planning that uses them. I only investigated this; I didn't implement it.

## Open questions

- The prompts are verbatim, but there's no evidence that the model's runtime environment matches the paper's.
- Running decisions and self-reflection together on everyday-life videos I recorded myself moved to the November 4 routine-video experiment.
- Asking when things are ambiguous, and decisions that carry uncertainty as probabilities, remained outside PAM.

## Related

- Note [1. Decision logic and choosing a paper](01_decision-logic-and-paper-choice.md): why I chose PAM and the limitations I noted at the time.
- Note [3. Intrusiveness and personal preference](03_intrusiveness-and-personal-preference.md): dealt with "asking" and "degree of disruption," which the paper left out of scope. The POMDP comes up there again only as a way to frame the theory.
- Experiment [2026-11-04_four-day-routine-videos](../2026-11-04_four-day-routine-videos/): ran the reproduced code on four days of videos I recorded myself. I reset the decision interval to 1 second to match the shortest signal.
- Final product: the paper's 7 decision and reflection prompts were moved to the team server (noonchi).

## Sources

- Faithfulness check: `seokjun/notes/sources/논문충실도_검증보고서.md`
- Reproduction scope and mapping to the paper: `seokjun/notes/sources/PAM_실험/실험범위와논문대응.md`
- Sentences changed in the prompts: `seokjun/notes/sources/PAM_실험/아침상황_원문변경표.md`
- POMDP survey: `seokjun/notes/sources/PAM_실험/POMDP_로봇논문_조사_2026-10-26.md`
- Records of the two fixes: the October 24–26 experiment log (not in this repository) (October 24 entries "초기 기억의 의미를 다시 확인함" (Rechecked the meaning of the initial memory) and "발표 범위 변경: 식탁 착석부터 시작" (Presentation scope change: start from sitting at the table); October 25 entry "GitHub 공개 전 논문 충실도 검증" (Paper faithfulness check before GitHub release))
- Paper limitations: section "4. 논문의 한계" (Limitations of the paper) of `seokjun/pam-paper-explainer.md` in the experiment repository; the memory that starts at the table: section "5. 우리는 어떤 환경에 적용했는가?" (What environment did we apply it to?) of the same document
