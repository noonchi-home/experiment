# Drink Handoff Videos — Footage for an Inverse Planning Experiment (2026-11-02)

## Summary

To test inverse planning (inferring what a person originally wanted by working backward from how they act after being helped), I designed and filmed 10 scenes of someone being handed a drink while studying. Before running models on the videos, I first compared methods on text scenes. Inverse planning scored lowest there, so I never went on to the experiment with these videos.

## Why I filmed these videos

- I wanted to see whether help rules could be revised based on how a person reacts after the robot helps. I was considering inverse planning as the way to read those reactions.
- Instead of a robot actually carrying the object, another person played the robot and handed over the drink. The plan was to compare the judgments of an AI that watched these videos.
- I did not want to put in a rule like "bring a drink when the person studies" as the answer from the start. The plan was to build the first rule from scenes where the person fetches a drink and drinks it on their own, and then have the rule revised based on the reactions to being handed a drink.

## What I filmed

There are 11 files. One pair are separate files but show exactly the same footage, so there are 10 distinct videos.

- **Two situations:** reading a book + water bottle, working on a laptop + canned drink
- **Two self-serve scenes:** one per situation. The person fetches the drink, drinks it, and goes back to what they were doing.
- **Eight reaction scenes after a handoff:** after another person handed over the drink in place of the robot, I filmed four reactions, one per situation each.
  1. Drinks right away
  2. Drinks after a delay (keeps working and drinks later)
  3. Refuses by shaking their head
  4. Refuses by putting it back where it was

Video length (seconds)

| Situation | Drinks alone | Drinks right away | Drinks after a delay | Refuses, shakes head | Refuses, puts it back |
|---|---|---|---|---|---|
| Reading + water bottle | 16.5 | 22.3 | 27.4 | 11.1 | 15.1 (plus 1 more file with identical footage) |
| Laptop work + canned drink | 13.5 | 16.2 | 22.4 | 14.4 | 19.0 |

- Every file is stored at 1920×1080.
- The two self-serve videos are fixed landscape shots. With the rotation metadata applied, the eight handoff videos are portrait, and the camera moves to follow the person handing over the drink. This differs from the fixed landscape setup I originally planned.

## How I checked the videos

- For each video I looked at 12 frames picked in time order. For the water bottle video where the person drinks after a delay, I sampled 18–23.5 s more densely and confirmed the drinking happens at 20.5–22 s.
- I confirmed that the head shake meant refusal from the filmer's description. I did not analyze the audio.
- I checked whether two files had identical footage by decoding both videos and comparing them frame by frame.

## How I decided to handle the answer key

- The four reactions are the staging intent described by the person who filmed them. I decided to keep them only as an answer key for evaluation and not give them to the model.
- I also decided not to give the model a choice such as "pick one of the four." The model writes down what it saw in the video and its own interpretation.
- I decided that files with identical footage, or scenes that directly follow each other, would not be split across the rule-building and test sets.

## Afterward

- Before running models on the videos, I first compared three ways of reading reactions on 15 text scenes (the 2026-11-06 experiment). Of the 15, the method that reads the whole observation log and answers directly fully matched the answer key on 10 scenes; inverse planning did so on 6. Inverse planning was the lowest of the three.
- So I dropped inverse planning and did not go on to run models on these videos.

## Limitations

- These are 10 short, staged videos. They do not show preferences built up over a long time in natural daily life.
- Reading always comes with the water bottle and laptop work always with the canned drink, so the effect of the activity cannot be separated from the effect of the drink type.
- Recognizing that someone refused is different from knowing why they refused. I did not check why the drink was put back.
- The drink was handed over by a person playing the robot. This is not a record of actual robot behavior.

## Files

| File | Contents |
|---|---|
| `video_inventory_2026-11-02.json` | Video list. For each file: length, resolution, rotation, activity, drink, scene description, whether it duplicates another file's footage, and the staging intent used for evaluation |

The videos and preview frames are not uploaded.
