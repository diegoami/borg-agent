# Mechanic claims

*Generated from `claims.jsonl` by `python -m borg_agent knowledge views`. Do not edit: a claim changes by being superseded, never by being rewritten.*

## The run ended because it reached the 1000-game-turn cap.

- **id** `run-ended-by-turn-cap` · **status** hypothesis
- **basis** observed
- **scope** class Warrior, race Human, version 4.2.6, character level 1–2, depth 1–1
- **engine** c-4.2.6 · **phase** 1 · **sources** own-play
- **rests on** The recorded outcome field is turn_cap and the reported duration is exactly 1000 game turns.
- **ruled out**: The run might have ended by death; the recorded outcome is turn_cap rather than death.
- **how to test it** Inspect the run metadata or replay the measurement with the same turn limit and verify that termination occurs at 1000 game turns.
- **evidence**
  - run `api-first`, seed 1, turn 1000 — The run outcome is turn_cap and the summary says the run lasted 1000 game turns.

## The Human Warrior reached character level 2 while on dungeon depth 1.

- **id** `warrior-reached-level-2-on-depth-1` · **status** hypothesis
- **basis** observed
- **scope** class Warrior, race Human, version 4.2.6, character level 1–2, depth 1–1
- **engine** c-4.2.6 · **phase** 1 · **sources** own-play
- **rests on** The level-up message appears while the run summary still records depth 1 and character level 2.
- **ruled out**: 'Welcome to level 2' might refer to dungeon depth; the run summary separately records depth 1 and character level 2, so the message is best read as character level.
- **how to test it** Play a Human Warrior to dungeon depth 1, gain comparable experience from depth-1 monsters, and check whether character level becomes 2.
- **evidence**
  - run `api-first`, seed 1, turn 479 — After the wild cat kill the log prints 'Welcome to level 2', and the run summary records character level 2 at depth 1.

