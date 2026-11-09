# Monster claims

*Generated from `claims.jsonl` by `python -m borg_agent knowledge views`. Do not edit: a claim changes by being superseded, never by being rewritten.*

## Can a level-1 Human Mage melee an adjacent floating eye and live? Counted: lived in 5 of 10 trials, died in 5.

- **id** `floating-eye-melee-mage-probe` · **status** supported · **superseded by** `floating-eye-melee-mage-probe-melee-only`
- **basis** quantified, 5 of 10 — probe floating-eye-melee-mage, Human Mage, seeds [11, 12, 13, 14, 15, 16, 17, 18, 19, 20], cap 1200, an intervention (D4)
- **scope** class Mage, race Human, version 4.2.6, character level 1–1, depth 1–1
- **engine** c-4.2.6 · **phase** 1 · **sources** own-play
- **rests on** 5 of 10 counted trials of probe floating-eye-melee-mage, the control arm 5 of 10
- **ruled out**: A different situation: every trial checked that the situation the probe asked for was there before the action was tried.; NOT ruled out: the control arm ended the situation too (the monster died in 4 of its 10 trials), so these counts do not separate the action from simply being there.
- **evidence**
  - run `action-seed11`, seed 11, turn 171 — agent_stopped
  - run `action-seed12`, seed 12, turn 251 — agent_stopped
  - run `action-seed13`, seed 13, turn 161 — agent_stopped
  - run `action-seed14`, seed 14, turn 191 — death: a floating eye
  - run `action-seed15`, seed 15, turn 201 — agent_stopped
  - run `action-seed16`, seed 16, turn 241 — death: a floating eye
  - run `action-seed17`, seed 17, turn 161 — death: a floating eye
  - run `action-seed18`, seed 18, turn 161 — agent_stopped
  - run `action-seed19`, seed 19, turn 193 — death: a floating eye
  - run `action-seed20`, seed 20, turn 231 — death: a wild cat
- **review** by action-seed11 (a probe): agree — counted by the probe itself: 5 of 10

## With melee the only attack the harness offered, a level-1 Human Mage who melees an adjacent floating eye at depth 1 lived in 5 of 10 trials and died to it in 4.

- **id** `floating-eye-melee-mage-probe-melee-only` · **status** supported
- **basis** quantified, 5 of 10 — probe floating-eye-melee-mage, Human Mage, seeds [11, 12, 13, 14, 15, 16, 17, 18, 19, 20], cap 1200, an intervention (D4)
- **scope** class Mage, race Human, gear melee only: the harness offered no spells, wands or thrown weapons at the time, version 4.2.6, character level 1–1, depth 1–1
- **engine** c-4.2.6 · **phase** 1 · **sources** own-play
- **rests on** 5 of 10 counted trials of probe floating-eye-melee-mage, the control arm 5 of 10
- **ruled out**: A different situation: every trial checked that the situation the probe asked for was there before the action was tried.; NOT ruled out: the control arm ended the situation too (the monster died in 4 of its 10 trials), so these counts do not separate the action from simply being there.
- **evidence**
  - run `action-seed11`, seed 11, turn 171 — agent_stopped
  - run `action-seed12`, seed 12, turn 251 — agent_stopped
  - run `action-seed13`, seed 13, turn 161 — agent_stopped
  - run `action-seed14`, seed 14, turn 191 — death: a floating eye
  - run `action-seed15`, seed 15, turn 201 — agent_stopped
  - run `action-seed16`, seed 16, turn 241 — death: a floating eye
  - run `action-seed17`, seed 17, turn 161 — death: a floating eye
  - run `action-seed18`, seed 18, turn 161 — agent_stopped
  - run `action-seed19`, seed 19, turn 193 — death: a floating eye
  - run `action-seed20`, seed 20, turn 231 — death: a wild cat
- **review** by action-seed11 (a probe): agree — counted by the probe itself: 5 of 10
- **note** Supersedes floating-eye-melee-mage-probe: the counts are unchanged, the scope is not. When the probe ran, the only attack the action surface offered was melee -- T29 added casting, wands, rods, throwing and the rest afterwards -- so this is a fact about a character fighting barehanded, not about the class. A Mage that can cast must be probed again.

## A level-1 Human Warrior who melees an adjacent floating eye at depth 1 usually lives.

- **id** `floating-eye-melee-probe` · **status** supported · **superseded by** `floating-eye-melee-probe-melee-only`
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

## With melee the only attack the harness offered, a level-1 Human Warrior who melees an adjacent floating eye at depth 1 lived in 10 of 10 trials.

- **id** `floating-eye-melee-probe-melee-only` · **status** supported
- **basis** quantified, 10 of 10 — probe floating-eye-melee, seeds [11, 12, 13, 14, 15, 16, 17, 18, 19, 20], cap 1200, an intervention (D4)
- **scope** class Warrior, race Human, gear melee only: the harness offered no spells, wands or thrown weapons at the time, version 4.2.6, character level 1–1, depth 1–1
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
- **note** Supersedes floating-eye-melee-probe: the counts are unchanged, the scope is not. When the probe ran, the only attack the action surface offered was melee -- T29 added casting, wands, rods, throwing and the rest afterwards -- so this is a fact about a character fighting barehanded, not about the class. A Mage that can cast must be probed again.

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

