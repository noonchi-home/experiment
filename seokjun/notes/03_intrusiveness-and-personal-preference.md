# 3. Intrusiveness and personal preference (October 31–November 1)

## What was the problem

After reproducing PAM, I looked for ways to reduce unnecessary interventions in the decisions built by following the paper.

- **The discomfort caused by wrong help differs by action.** Bringing milk that isn't needed and clearing away something still in use carry different weight. Bringing, clearing, and throwing away also differ in the cost of undoing them when they're wrong.
- **PAM doesn't deal with this difference.** There are only two options, "act / do nothing," and it assumes that acting doesn't disturb the person. Asking when uncertain is out of scope, and because it leans toward adding rules, over-intervention can arise. It handles only one person.
- **Reactions are hard to read.** No reaction doesn't mean satisfaction. A person doing a task themselves when the robot didn't help isn't evidence that they wanted that help, either. They may simply prefer doing it themselves.

## How I thought about it

### Separating desire for help (h) from the discomfort a way of helping causes (w)

- **h (desire for help):** How much the person welcomes help itself. One value per person, plus adjustments by stage type (preparing, eating, working, tidying).
- **w (intrusion sensitivity):** How sensitive the person is to the four things a way of helping touches on: proximity (coming close), territory intrusion (other people's things or spots), loss of control (clearing away something I'm using), and timing (interrupting in the middle of a task).

The reason for separating the two is to represent "a person who wants help but doesn't like the robot coming close." The spec's simulated-user test was also set up around the hypothesis that, for a person who complains but still wants help, learning w and h together would fluctuate less and settle faster than learning w alone.

Of the four factors, proximity, timing, and loss of control were taken from the questionnaire items of HRI (human–robot interaction) studies that measured the intrusiveness of robot interventions (Hriscu et al.; Bo et al., 2026), and territory intrusion was added with multi-person homes in mind. The two papers are companion papers from the same 32-person experiment, so I counted them as one independent source. Territory intrusion still needed more support from HRI research.

### PAM decides when and what; the way of helping is set in advance at night

PAM's memory decides when and what to help with, and how to help is decided in advance at night using h and w. During the day, the robot carries out the preset way, and steps it down one level as a defined exception only when confidence is low, when it has already been refused that day, or when someone else is present. Computing scores every time during the day would be slow, and wouldn't fit PAM's design of fixing memory for the day.

The way of helping is chosen from a predefined menu.

- When: when no one is around / now / wait until the next stage begins
- Where: close / at the edge of arm's reach (only when bringing something)
- Start: quietly / ask first
- Or skip this time

The formula for choosing a way:

```text
x                     = how much doing this rule this way touches each of the four factors (each 0–1)
complaint probability = σ(w · x + b),  b = −3   (about 5% if nothing is touched)
score                 = h × help value(way) − complaint probability
```

σ is a function that maps any number to a value between 0 and 1. The help value is the amount of help set for each way (e.g., bringing it close right now 1.00, waiting and placing it farther away 0.70, ways that ask first ×0.8). If every way scores 0 or below, the robot skips. When several people are present, it chooses conservatively, using the lowest desire for help and the highest complaint probability among them. Some rules are fixed regardless of learning: always ask before throwing something away, hold off on other people's things when the owner isn't there, and don't touch objects a person is holding.

At night, reactions are extracted from that day's video to update w and h.

| Reaction | What gets updated |
|---|---|
| Brings back something the robot cleared away | Update w as a complaint about loss of control |
| Pushes aside something the robot brought, then uses it | Update w as a complaint about proximity; raise h since it was used |
| Puts away something the robot brought without using it | Lower h |
| Asked, then refuses / accepts | Lower h (−1) / raise h (+0.5) |
| The robot didn't act and the person did it themselves | Raise h |
| No noticeable reaction | Treat as "no complaint," but give it only a weak weight (0.3) |

No reaction is not approval, so it gets only a weak weight. Asking is the least intrusive way, so a refusal after being asked was treated as the cleanest signal that the person doesn't want the help itself. w is updated by online logistic regression (a probability model adjusted a little each time a reaction comes in) with a term that pulls it gradually toward the default, and the amount it can change in one night is capped. A rule skipped three or more days in a row is retried the next day, with some probability, in the "ask" way. This keeps a switched-off rule from never being observed again.

**Considered but not chosen.** I left out a frequency factor (its only support is one 32-person study, and it overlaps with the other factors), a task-relevance factor, estimating disposition from MBTI (low test–retest reliability, accumulating error, and ethical issues), neural networks such as multi-head attention (tens to hundreds of reactions from one person can't train thousands of values), and an "announce, then act" way.

### Weaknesses I found myself

- **The same reaction can have several reasons.** When a person moves an object the robot brought, the spot might have been inconvenient, they might have needed workspace, or they might have moved it somewhere easier to use. "Moved the object" doesn't mean "dislikes the robot coming close." Nor can you conclude they liked the help just because they used the object.
- **A wrongly learned trait spreads to other help.** Reading one refusal as "dislikes help itself" cuts back even needed help. Conversely, reading it as only a problem with the way of helping leads to repeating unwanted interventions in other ways.
- **Missed help can't be told apart from a preference for doing things oneself.** The spec's simulated-user test deliberately kept this ambiguity to see whether learning could withstand it.
- **The ratio of signal sizes determines the outcome.** With the spec's values (+0.5 for accepting when asked, −1 for refusing), even a person who accepts half the time has h drift downward. The spec also notes that the ratio of positive to negative signal sizes sets the equilibrium (e.g., +0.01 and −0.1 balance at about 9% complaints), and leaves open the task of first deciding how often complaints are acceptable and then tuning the values.
- **If an action's properties are defined only by its destination,** several properties change together, making it hard to separate the causes of discomfort. There is also little reaction data, and with the current camera setup it's hard to see facial expressions.

Asking for the reason every time burdens the user, while judging from observation alone can misestimate preferences. The remaining problem was **how to estimate individual traits without asking often**.

### Directions I kept anyway

- **Judge by the person's traits.** If you only pile up per-action rules, you can't judge help you've never seen. For example, from reactions to document tidying and tool tidying, find the common property "rearranging things while the person is working," estimate how much this person dislikes it, and apply that to cable tidying, which hasn't been seen before. Cable tidying is excluded from learning and used only for evaluation.
- **Keep questions to a minimum.** Since helping first is the core idea, the process of getting feedback from the user is kept to a minimum. Traits without enough evidence are left as "unknown," and if the person explicitly says not to do something, that is applied right away without waiting for the night.
- **Helping less isn't success by itself.** Look at whether unwanted interventions went down together with whether useful help was maintained.

### A question I left for myself

How is this different from PAM with just an added prompt? In the presentation, I said I would compare per-action memory, a method where a language model reads the log and decides directly, and a personal model that uses common traits, all on the same logs and with the same action options. The spec's comparison set also included "a language model choosing the way of helping from the log alone, with no numbers." For the question "doesn't the language model end up deciding everything anyway?", I prepared only this answer: I would not take the model's stated interpretation directly as a fixed disposition, and would check whether there is any advantage over having the model decide directly.

## How far it got

- **October 31.** I organized the discussion I'd had on claude.ai into design spec v0.1, to hand to an implementation agent. As a first step, I designed a simulated household: give 2–4 virtual people true w and h values, and compare PAM default (always now, close, quietly) / no learning / learning w only / learning w and h / deciding with a language model alone, on complaint rate, help rate, value error, and days to converge. I also wrote plans for human experiments (a pilot study to validate the factors, and a multi-day experiment with a real robot).
- **November 1.** I made research-direction presentation slides and a script and linked them to a team ticket (S01-PSJ-01). The presentation is a proposal for a research direction, not an implementation or a validation of effects.
- **No experiment was run.** No code implementation, real model comparison, or user experiment. The numbers in the documents are illustrative initial values.
- On November 2, I narrowed the first experiment to interpreting observable behavior and updating help rules, and kept h and w only as background perspectives. The numerical model and the learning equations were not finalized.

## Open questions

- In a multi-person home, how to tell who is there right now; the actual distance for "farther away"; how often complaints are acceptable.
- How to tell missed help apart from a preference for doing things oneself.
- Whether the four intrusiveness factors actually separate; the support for territory intrusion.
- How to estimate each person's intervention preferences without asking. I revisited this with inverse planning but didn't solve it, and it became an open problem for the research as a whole.

## Related

- Note [4. Inverse planning](04_inverse-planning.md): revisited the problem of forcing people's reactions into four predefined factors.
- Note [1. Decision logic and choosing a paper](01_decision-logic-and-paper-choice.md): the costs of intervening, not intervening, and asking (Horvitz); the principle of not treating an undone action directly as a misjudgment.
- Note [2. PAM reproduction](02_pam-reproduction.md): "asking," which the paper left out of scope. The spec framed the problem as a POMDP and noted that it would actually be solved by stage tracking with an approximation that looks only one step ahead.
- Note 5 (appliance signals and triggers): the design of watching reactions after helping and classifying their strength (undoing, blocking, refusing verbally) comes up again.

## Sources

- Design spec v0.1: `seokjun/notes/sources/proactive_robot_intrusiveness_spec.md`
- Research direction (written November 1, updated November 2): `seokjun/notes/sources/개인별선호모델_연구방향.md`
- Presentation: `PAM_개인별선호모델_발표자료.md`, `PAM_개인별선호모델_발표대본.md`
- Team docs repository (docs): `03_Sprints/Sprint-01/Tickets/S01-PSJ-01_선제적-도움의-간섭도와-개인화-방식-검토.md`, and the October 31 and November 1 entries in `03_Sprints/Sprint-01/Daily/PSJ.md`
