# Monster claims

*Generated from `claims.jsonl` by `python -m borg_agent knowledge views`. Do not edit: a claim changes by being superseded, never by being rewritten.*

## A level-1 Human Warrior who melees an adjacent floating eye at depth 1 usually lives.

- **id** `floating-eye-melee-probe` · **status** supported
- **basis** quantified, 10 of 10 — probe floating-eye-melee, seeds [11, 12, 13, 14, 15, 16, 17, 18, 19, 20], cap 1200, an intervention (D4)
- **scope** class Warrior, race Human, version 4.2.6, character level 1–1, depth 1–1
- **engine** c-4.2.6 · **phase** 1 · **sources** own-play
- **rests on** 10 of 10 counted trials of probe floating-eye-melee, the control arm 9 of 10
- **ruled out**: A different situation: every trial checked that the situation the probe asked for was there before the action was tried.; NOT ruled out: the control arm ended the situation too (the monster died in 9 of its 10 trials), so these counts do not separate the action from simply being there.
- **evidence**
  - run `action-seed11`, seed 11, turn 109 — agent_stopped
  - run `action-seed12`, seed 12, turn 112 — agent_stopped
  - run `action-seed13`, seed 13, turn 112 — agent_stopped
  - run `action-seed14`, seed 14, turn 167 — agent_stopped
  - run `action-seed15`, seed 15, turn 109 — agent_stopped
  - run `action-seed16`, seed 16, turn 109 — agent_stopped
  - run `action-seed17`, seed 17, turn 109 — agent_stopped
  - run `action-seed18`, seed 18, turn 109 — agent_stopped
  - run `action-seed19`, seed 19, turn 112 — agent_stopped
  - run `action-seed20`, seed 20, turn 109 — agent_stopped
- **review** by action-seed11 (a probe): agree — counted by the probe itself: 10 of 10

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

