# Monster claims

*Generated from `claims.jsonl` by `python -m borg_agent knowledge views`. Do not edit: a claim changes by being superseded, never by being rewritten.*

## A Human Warrior can kill a giant yellow centipede in melee on dungeon depth 1.

- **id** `giant-yellow-centipede-melee-kill-depth-1` · **status** hypothesis
- **basis** observed
- **scope** class Warrior, race Human, version 4.2.6, character level 1–2, depth 1–1
- **engine** c-4.2.6 · **phase** 1 · **sources** own-play
- **rests on** The combat message attributes the kill directly to the player's attack.
- **ruled out**: The centipede might have died from a trap or other cause; the messages show the player hitting it immediately before the slaying message.
- **how to test it** Find a giant yellow centipede on depth 1 with a Human Warrior and attack it in melee until it dies.
- **evidence**
  - run `api-first`, seed 1, turn 431 — The agent chose fight_nearest against a nearby giant centipede, and the log later says 'You hit the giant yellow centipede' and 'You have slain the giant yellow centipede'.

## A Human Warrior can kill a wild cat in melee on dungeon depth 1.

- **id** `wild-cat-melee-kill-depth-1` · **status** hypothesis
- **basis** observed
- **scope** class Warrior, race Human, version 4.2.6, character level 1–2, depth 1–1
- **engine** c-4.2.6 · **phase** 1 · **sources** own-play
- **rests on** The log records 'You hit the wild cat' followed by 'You have slain the wild cat'.
- **ruled out**: The wild cat might have died from a non-player cause; the slaying message is immediately preceded by player hit messages.
- **how to test it** Find a wild cat on depth 1 with a Human Warrior and attack it in melee until it dies.
- **evidence**
  - run `api-first`, seed 1, turn 479 — The final combat messages show the player hitting and slaying a wild cat before resting.

