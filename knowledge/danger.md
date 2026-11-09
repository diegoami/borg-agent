# Danger claims

*Generated from `claims.jsonl` by `python -m borg_agent knowledge views`. Do not edit: a claim changes by being superseded, never by being rewritten.*

## A wild cat can hit the Human Warrior with a claw attack on dungeon depth 1.

- **id** `wild-cat-claw-hit` · **status** hypothesis
- **basis** observed
- **scope** class Warrior, race Human, version 4.2.6, character level 1–2, depth 1–1
- **engine** c-4.2.6 · **phase** 1 · **sources** own-play
- **rests on** The message 'The wild cat claws you' is a hit message, distinct from 'The wild cat misses you'.
- **ruled out**: The claw attack might have missed; the log explicitly records both a miss and a successful claw hit.
- **how to test it** Engage a wild cat on depth 1 and observe whether the combat log records a successful claw attack against the player.
- **evidence**
  - run `api-first`, seed 1, turn 479 — During the wild cat fight the log contains 'The wild cat claws you' as well as a separate miss message.

