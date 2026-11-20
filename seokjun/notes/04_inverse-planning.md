# 4. Inverse planning (November 1–6)

## What was the problem

The presentation from note [3](03_intrusiveness-and-personal-preference.md) only said what I would do; the method was missing. The problem was what actually had to be computed to learn preferences from a person's behavior without asking in words, so that the next day the robot does only what suits that person.

## How I thought about it

### Don't force reactions into predefined reasons

In a claude.ai conversation, Claude suggested not guessing the reason behind each single reaction, but finding the preference hypothesis that best explains many scenes at once. This is inverse planning.

- **Planning** decides actions given a goal. If you want to drink water, you take a water bottle out of the fridge.
- **Inverse planning** works the other way: it infers the goal from the actions. Seeing someone take a water bottle out of the fridge, you infer they were thirsty.
- **Bayesian inverse planning** (Baker, Saxe, Tenenbaum) scores each hypothesis by "if this hypothesis were true, how likely is this action?" (the likelihood), multiplies these as scenes accumulate, and picks the hypothesis that explains them best. Hypotheses that one scene couldn't tell apart separate as scenes accumulate.

The initial proposal used the four factors from note 3 (proximity, territory, control, timing) as the starting point for hypotheses. I pointed out a problem here. When the robot does something, the person may be thinking about something that has nothing to do with proximity. If you force a person's reaction into predefined reasons, you learn the wrong reason when they acted for an entirely different one. So **I removed the factors from the center of the model.** I decided that hypotheses should be sentences formed freely from the scenes, not predefined slots.

I also looked at related work. BIP-ALM (MMToM-QA, ACL 2024) computed likelihoods with a language model further trained on human activity data, and its videos were of virtual homes rather than real footage. LIMP (MuMA-ToM, AAAI 2025) computed likelihoods with an off-the-shelf language model without additional training and handled multi-person situations. The main idea I took from LIMP was that rather than asking a language model directly "why did they do that?", it's better to ask, for each hypothesis, "with this state of mind, how would they act?" and combine the answers. I reviewed but didn't adopt the detailed proposal Claude made in the conversation (confirm a hypothesis when its probability is at least 70% and at least 3 scenes support it; judge actions never seen before by a weighted average over hypothesis probabilities). The formula also remained undecided in the later research documents.

### Where to put inverse planning

I considered two places to use inverse planning.

1. During self-reflection, analyzing the user's behavior to find what the robot should help with.
2. After the robot helps, continuing to watch the person's behavior and working backward to what that behavior originally aimed for.

Claude judged that place 1 offers little gain because it amounts to organizing the order of recurring habits, while place 2 fits the original form of inverse planning. It added that most behavior after help stems from what the person was already doing, not from preference, so the ongoing task (the goal) and preference must be weighed together, and how long to keep watching must be decided. It also suggested that using inverse planning to check "is this help really needed right now?" after a trigger (the signal for the robot to start helping) fires but just before acting could reduce PAM's problem of starting to help even when an object has only been touched briefly. I thought this direction was worth trying, but it was slow, because the model has to be called for each hypothesis at a point where a decision is needed every second.

The scope I settled on:

- Inverse planning would be considered for analyzing user observations, interpreting reactions after help, and creating and revising rules during self-reflection.
- **Adding inverse planning just before acting, after a trigger fires, was postponed for this round.** As before, actions are chosen by the decision model referring to the revised memory.
- Interpretations inferred by the language model are not mixed into the field for feedback the person stated directly.

### I lowered the goal

I kept the long-term goal of learning individual preferences, but narrowed the first experiment to **interpreting observable behavior to create and revise help rules**. Rather than pinning down a fixed disposition as a number, the approach compares goals and contexts that explain current behavior and revises rules on that basis. h and w were kept only as background perspectives.

- The actions the robot can perform are defined in advance; the rules for when to do what are built from observation.
- The rule "when studying, bring a drink" is not given as the answer from the start. The model builds the first rule by watching the person fetch a drink themselves.
- On November 3, I settled on a list of 10 actions: put a water bottle or can next to the person, throw an empty water bottle or can in the trash, put a book or laptop next to the person or in its storage spot, put a cup or tissues next to the person, and wait. From the 12 first proposed, I removed the two for putting a water bottle or can in its storage spot. As a result, the only correct answer for refusal scenes became wait.

### Comparison conditions

| Condition | Interpreting reactions after help | Self-reflection (creating and revising rules) |
|---|---|---|
| 1. Paper method | None | As in the paper |
| 2. Add general analysis | General analysis by a language model | Paper method plus the analysis text |
| 3. Inverse planning for reaction interpretation only | Inverse planning | Paper method |
| 4. Inverse planning for self-reflection only | General analysis | Inverse planning results added |
| 5. Both | Inverse planning | Inverse planning results added |

Condition 2 is there to separate improvements that come simply from more steps, more information, and more computation from the effect of inverse planning. The goal and environment information given to inverse planning is given equally to condition 2. Using the same observation in two steps is not counted as two independent pieces of evidence.

On November 3, I decided to settle how to compute inverse planning later and to run the baseline paper-method experiment without inverse planning first. The November 4 design draft compared three ways of computing it.

- **A. Language model probabilities.** The model generates goal candidates, and the probability of the actual behavior under each goal is measured with the model's token probabilities. This was the recommended option.
- **B. A small symbolic planning model.** States, actions, and costs are defined by hand, and the optimal plan is computed for each goal. When a person builds it, there is a high risk that the filming intentions known only to the evaluator leak into the model.
- **C. Having the model think about goals through the prompt alone.** Since this is not a separate planning computation, it would not be reported as an inverse planning result and would be used only as condition 2.

I estimated that running all planned conditions would cost about $23 (GPU server balance at the time: $33.61).

## How far it got

### Ten drink-handoff videos (November 2)

I settled on a situation of handing someone a drink while they study, and designed and filmed the videos myself.

- 2 videos of the user fetching a drink on their own: a canned drink while working on a laptop, and a water bottle while reading a book.
- 8 videos of a helper handing over the drink in place of the robot: four reactions for each of the two situations (drinks right away, keeps working and drinks later, refuses by shaking their head, refuses by putting it back where it was).
- There were 11 files, but one pair showed identical footage, so there are 10 distinct recordings. They run about 11–27 seconds, and most of the help videos are in portrait orientation with the camera following the helper.

I decided to keep the reaction types only as the answer key for evaluation and not to give them to the model as fixed options or per-video answers. I didn't check why the drink was put back, and since the task and the drink type changed together, nothing can be said about drink preference by task either. In the help videos, the user is visible only during the first 0–3.5 seconds, so there were few cues about the reaction.

### Comparing first on 15 text scenes (November 4–6)

Before running on the videos, I compared methods on scenes written as text.

First, I tested how to get scores from a language model. Reading the probabilities of the option letters made the values swing widely when the order of the options changed, or produced only 0 and 1. Asking "yes/no" also produced extreme values, and having the model answer with a number from 0 to 100 clustered answers on multiples of 5, causing ties. Using a 0–100 number but taking a weighted average by the probabilities of the numbers (G-Eval) gave the right direction with little fluctuation.

I had the same language model (gpt-6.1-terra) solve 15 scenes, which Claude wrote with the intentions decided in advance, once per method. The scene titles and the answer key were hidden from the model, and Claude also did the grading.

| Method | Correct | Partly correct | Wrong | Cost for 15 runs |
|---|---:|---:|---:|---:|
| Read the whole chronological observation log and answer directly | **10** | 4 | 1 | about $0.0043 |
| Organize the log into states and state changes, then answer | 8 | 7 | **0** | about $0.048 |
| Score how well each intent candidate explains the subsequent behavior (inverse planning) | 6 | 3 | 6 | about $0.261 |

In the scene where the robot put down a cup of water and the user took out a pill and swallowed it, the answer was "needed water to swallow a pill." The whole-log method and the state-change method got it right; inverse planning's top candidate stopped at "wanted to drink water," missing why water was needed.

The main reason inverse planning scored low was that the intent candidates were generated only from the log just before the robot's action. So it missed scenes where the cue came after the action (heat, a pill, glare, etc.). That was Claude's interpretation, and I identified the same cause when looking at the results. In addition, the mechanism for regenerating candidates never activated once, and the top candidate was usually at 15–25%, only 1–2 percentage points ahead of the second and third.

### Decision (November 6)

Inverse planning scored lowest, so I didn't go on to the video experiment. **I dropped inverse planning**, and in later experiments gave the model the whole observation log as plain prose and had it decide directly. I didn't use the approach of converting the log into state changes either.

## Open questions

- The scope of the results is narrow. The 15 scenes are synthetic text with clear cues, both writing and grading the scenes were done by AI, and each method was run only once. There is no record of a person checking the grading.
- Only inverse planning was given the robot's action rules, and the point at which candidates were generated also differed, so the cause of the differences between methods can't be pinned to a single factor.
- Performance at inferring intent from the recorded drink videos was not evaluated.
- The direction of using inverse planning just before acting to reduce wrong triggering was postponed and never tested.
- How to estimate each person's intervention preferences without asking became an open problem for the research as a whole.

## Related

- Experiment [2026-11-06_intent-inference-comparison](../2026-11-06_intent-inference-comparison/): per-scene answers and grading for the 15-text-scene comparison.
- Experiment [2026-11-04_four-day-routine-videos](../2026-11-04_four-day-routine-videos/): the experiment that first ran the baseline paper method on real videos, without inverse planning.
- For the drink-handoff videos, only the video list file is included; the videos were not uploaded.
- Note [3. Intrusiveness and personal preference](03_intrusiveness-and-personal-preference.md): where the four factors and h and w first appeared.
- Note 5 (appliance signals and triggers): the design of watching reactions for a set time after helping and classifying their strength comes up again.

## Sources

- Excerpt from the claude.ai conversation (saved November 2; the content is summarized rather than quoted): an excerpt of a claude.ai conversation (not in this repository)
- Research direction and comparison conditions: `seokjun/notes/sources/개인별선호모델_연구방향.md`; video list: `seokjun/2026-11-02_drink-handoff-videos/video_inventory_2026-11-02.json`
- Settled scope and action list: `seokjun/notes/sources/ai-collab/codex_to_claude_2026-11-03.md`, `seokjun/notes/sources/ai-collab/claude_discussion_2026-11-03.md`
- Comparison of computation methods and cost estimate: `seokjun/notes/sources/역계획_설계초안_2026-11-04.md`
- Scoring-method tests, the 15-scene results, and the decision to drop inverse planning: `seokjun/notes/sources/ai-collab/역계획실험_2026-11-06_결과_정리.md`, `seokjun/2026-11-06_intent-inference-comparison/README.md`
