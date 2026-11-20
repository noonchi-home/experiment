# 1. Decision logic and choosing a paper (October 23)

## What was the problem

Our team's topic is a proactive home robot (one that helps before being asked). The robot had to look at what was happening in the home and decide on its own — for example, when a window is open while it is raining, when the gas is on but no one is cooking, when the gas must not be turned off because someone is cooking, or when the master bedroom is dusty enough that the robot vacuum should run.

There were two conditions.

- Almost no information should have to come from the user. Assume the data has already been collected, and let the AI make the decisions.
- In the middle of a decision, the AI must work out on its own whether it needs more information (for example, whether it should check if there is anything in the cup) or whether it can decide on an action now. We needed a structure in which the robot decides whether to "look more, or help now."

I planned to run the first experiments with the DeepSeek API and later switch to a local Qwen model. Also open were whether we needed a structure that splits roles among several AIs (multi-agent) or additional model training, and whether to borrow from established decision-making research. Rather than deciding right away, I chose to settle these as the discussion went on.

## How I thought about it

### Asking two AIs separately and having them review each other

I didn't settle the decision structure on one AI's answer.

1. Codex first wrote an independent opinion, which was kept unedited.
2. Claude (Opus 5.5, maximum reasoning setting) was sent only the problem and the conditions. Codex's opinion and paper recommendations were not included. The first call failed with a 600-second timeout; I called again with the same settings and got an answer.
3. I passed each opinion to the other, had them exchange counterexamples over two rounds, and then received both revised opinions in a single report.

Points both opinions considered important:

- **Partial observation.** Separate what can be seen (the gas valve is on) from states that can't be seen (is someone cooking right now?). This problem is close to a POMDP (a decision-making framework that chooses actions while estimating unseen states).
- **Time history.** Look not only at the current scene but also at how long things have been that way, whether the information is stale, and whether pieces of information conflict.
- **Value of observation.** Whether to look more depends on whether the result would change the action now or later, and on the cost of observing (time, disruption, privacy). As an example from the later cup design: if the person is holding the cup, it can't be moved now whatever is in it, so checking inside the cup may be a useless observation.
- **Separating state, activity, goal, and policy.** "Gas on" is an observation, "cooking" is an interpretation, "don't interfere with cooking" is the goal, and "leave it on, but reassess if conditions change" is the policy. Only by separating the four can you tell where things went wrong.
- **Execution checks outside the model.** Code checks conditions such as whether the target exists and whether the action is supported, and distinguishes between sending a command and the action actually finishing.

What actually changed through the feedback:

| Issue | After feedback |
|---|---|
| Probability and cost calculation | Claude withdrew its initial proposal that "the model writes probabilities and costs and code does the final calculation." Unfounded model probabilities don't become reliable just because code computes with them |
| Order of observations | Dropped fixed orders like "cheapest observation first" and decided to weigh relevance to the decision, the power to tell states apart, time constraints, the chance of failure, and cost together |
| Actions the user undid | Don't immediately learn them as misjudgments. The situation or preference may have changed. Not being undone isn't evidence of being right, either |
| Training a local model | Withdrew a fixed order like "if it's a local model, train it first" |

The remaining difference was one of emphasis. Codex stressed an evaluation that ties together time history, information selection, and outcomes; Claude stressed responsibility and policy checks outside the model. A proposal remained for the next step: in the same synthetic environment, separately measure the effects of "observation selection unavailable/available," "no time history/time history," and "no policy check/policy check."

### Whether to further train the model

After reading Claude's first opinion, I asked again whether choosing a local model meant no separate training. Codex drafted the answer and Claude (Opus 5.5, high reasoning setting) reviewed it. The verdict was "nothing incorrect; two places need supplementing." The supplemented conclusions:

- **Test without additional training at first.** This is not a final decision never to train.
- **Measure baseline performance before training.** Evaluate local model candidates on the same task in their untrained state. Don't assume that because DeepSeek did well, a small local model will too.
- **Train only once there is evidence.** If the same decision errors keep recurring even with enough information, and corrected cases accumulate, compare fine-tuning (training an already-trained model further on our cases). Evaluate on situations not used for training or prompt revisions, with the same inputs and tool conditions.
- **Logging and memory are different from training.** The home's latest history is information to record and feed into the model's input when needed. Training is a separate job that changes how the model reads that history and decides. Feeding in data continuously doesn't make a model learn on its own.
- Training can't reveal facts that were never observed, but it can teach the model which observations to request to confirm those facts.

From the review, I didn't use the sentence "facts about the home don't go into the model weights" as is, because fine-tuning can memorize facts. Instead I wrote: "In our design, history is supplied as external memory, and the model is not trained automatically during normal use."

### Choosing a paper

At first I surveyed long-established, award-winning decision-making research.

| Paper | What to borrow | Standing confirmed |
|---|---|---|
| POMDP (Kaelbling et al., 1998) | Separate visible observations from hidden states, and compare information-gathering actions as actions too | 2021 AIJ Classic Paper Award |
| Horvitz, principles of mixed-initiative interfaces, where the person and the system take turns leading (CHI 1999) | The benefits of intervening, not intervening, and asking, versus the cost of disruption | A PC assistant case. Not validated for home control |
| Options (Sutton et al., 1999) | Starting, continuing, and ending long-running actions such as cleaning | 2019 AIJ Classic Paper Award |
| Landmark-based goal recognition (Pereira et al., 2020) | Estimating a person's candidate goals from their action history | 2024 AIJ Prominent Paper Award. Evaluated on symbolic planning problems |
| KnowNo (CoRL 2023) | Criteria for asking for help when uncertain | Best Student Paper |
| Generative Agents (UIST 2023) | Retrieving relevant memories to revise plans | Best Paper. Evaluated with virtual characters |

I also read ReAct (a loop of observe → choose → tool result → decide again), CoALA, and SayCan. The awards are evidence of theoretical value, not validation from long-term use in homes.

These classics didn't show concretely that, given this data, the AI reaches this conclusion. Among recent work, I thought ContextAgent (2025) came closest, but even that wasn't enough. Claude's initial layered structure (layers 0–4: safety rules → interpretation → proposal → code approval → feedback) also had only layer names, with the decision logic inside each layer left empty. So instead of tackling the whole home at once, **I narrowed the first situation to a single question — "clear the cup or not" — and decided to build all inputs as synthetic data.**

I then searched again for papers that dealt directly with the cup problem.

| Paper | What it covers | Stated limitations |
|---|---|---|
| PAM (KAIST, 2026) | Reads recent photos and a memory of activity stages, then picks one task number or NO_ACT (do nothing). The decision model is not trained; only the memory is revised | Summarized separately below |
| Proactive Physical AI (2026) | Separately trains a model that chooses when to intervene. Under a condition where it is given only its role and not told the target event, F1 28.72% → 33.45% | Did not validate cup clearing. A recent preprint |
| Spatio-temporal object modeling (Patel & Chernova, CoRL 2022) | Predicts future object locations from object-placement history and moves objects in advance. Trained on synthetic household data | May clear too early if a meal runs longer than usual. Does not address human activity or object cleanliness |
| ContextAgent (2025) | Decides on proactive services and tool calls from context. The main method is additional training | The approach that only adds examples is merely a comparison baseline |

I excluded LIT, which starts only after receiving a command, and set aside Housekeep and TidyBot, where the tidying goal is already given.

**Why I chose PAM.** The paper (§3.2) directly addresses the same concern as the cup problem. The same empty bowl is a cue to bring cereal before a meal and something to clear after it. Its approach asks not what object is visible now but what role that object plays in the current activity. The fact that it doesn't train the decision model and only revises memory from the day's log also matched the conclusion to test without training at first. During the survey, Codex put PAM forward as the top reference candidate for representing activity context, and I started reproducing PAM the next day.

**Limitations noted for PAM.**

- The main decision evaluation used 1,146 photos taken over 5 days of one person's desk routine (3.5–4.5 minutes a day). It is not a long-term validation across a whole home.
- The last-day F1 (accuracy score, 1 is perfect) for bowl clearing was 0.60±0.09.
- The action list has only 6 actions plus NO_ACT, and the ability to choose what to look at more was not evaluated. It relies on photos taken at fixed intervals.
- The decision model isn't trained, but the model that moves the robot arm (π0.5) was fine-tuned separately for each action. No training in the decision model is not the same as no training in the whole system.
- The authors themselves list as out of scope the problem of misreading a brief touch on an object as intent, generalization to new users, layouts, and objects, and the ability to ask the user.
- I confirmed the CoRL 2026 label only on the authors' page and arXiv.

### Principles for the cup experiment (Codex's proposal)

From the cup experiment design Codex wrote, I adopted the following principles. They have not been finalized as the final spec.

- "Empty" is an observation; "finished using" is an inference. Putting "use finished" into the input in advance would amount to giving away the answer being tested.
- The same "empty cup on the desk" should lead to different decisions depending on whether it was just taken out, is about to be refilled, was finished while the person moved on to something else, or nobody knows who used it or when. If observation can't tell them apart, waiting can also be the right answer.
- The proposed comparison conditions were four stages: "current state only → add chronological usage history → add memory of past activities → add extra observation tools."

## How far it got

- I left a two-model meeting report, the answer on whether to train, paper survey memos, and a cup decision design document.
- I didn't run DeepSeek experiments, train models, or control a robot. The inputs and outputs in the documents are illustrative examples.
- From the next day (October 24), I moved on to reproducing PAM.

## Open questions

- Not decided: what each device can actually do and at what permission level, whether to use probabilities, whether to include predicting and preventing problems that haven't happened yet, and the final model, number of agents, and whether to train.
- PAM doesn't cover the ability to choose what to look at more. It needs separate validation.
- How to distinguish "leave it as is" from "observe more" in outputs and evaluation remains open.
- How to interpret actions the user undid led on to the later work on personal preference and inverse planning.

## Related

- Note [2. PAM reproduction](02_pam-reproduction.md): the process of porting the chosen PAM as is. The question of layering a POMDP on top of PAM also continued there.
- Notes [3. Intrusiveness and personal preference](03_intrusiveness-and-personal-preference.md) and [4. Inverse planning](04_inverse-planning.md): the principle of not treating user reactions directly as marks of a misjudgment carried over.
- Experiment [2026-11-04_four-day-routine-videos](../2026-11-04_four-day-routine-videos/): the first comparison of with and without memory, on videos I recorded myself.

## Sources

- Initial problem and conditions: `seokjun/notes/sources/의사결정_설계회의_2026-10-23/00_사용자문제_독립입력.md`
- The two AIs' opinions and the results of their cross-feedback: `seokjun/notes/sources/의사결정_설계회의_2026-10-23/09_두모델_회의보고서.md` (the original independent opinions are 01 and 05 in the same folder; the cross-reviews are 06–08)
- Whether to train: `seokjun/notes/sources/학습여부_검토_2026-10-23/answer.md`, `claude_review.md`, `review_evidence.json`
- Paper survey: `seokjun/notes/sources/research/선제판단_기초연구_20261023.md`, `seokjun/notes/sources/research/선제판단_최근연구_20261023.md`, `seokjun/notes/sources/research/선제판단_목표인식_20261023.md`, `seokjun/notes/sources/research/논문검증_KnowNo_SayCan.md`, `seokjun/notes/sources/research/컵_선제행동_직접관련논문_20261023.md`
- Cup decision design and review changes: `seokjun/notes/sources/컵_선제판단_논문과실험설계.md`, `seokjun/notes/sources/설계문서/2026-10-23_컵_선제행동_판단설계.md`, `seokjun/notes/sources/research/컵_선제판단_검토_20261023/`
