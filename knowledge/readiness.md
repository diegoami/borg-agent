# Readiness claims

*Generated from `claims.jsonl` by `python -m borg_agent knowledge views`. Do not edit: a claim changes by being superseded, never by being rewritten.*

## At turn 479 the agent chose rest_until_healed after a no_target stop with the warrior at 15/40 HP.

- **id** `post-combat-rest-at-low-hp` · **status** hypothesis
- **basis** observed
- **scope** class Warrior, race Human, version 4.2.6, character level 1–2, depth 1–1
- **engine** c-4.2.6 · **phase** 1 · **sources** own-play
- **rests on** The recorded stop reason and action explicitly describe a post-combat low-HP rest decision.
- **how to test it** Inspect the turn-479 decision record for stop reason no_target, HP 15/40, and action rest_until_healed, or reproduce that state and check whether rest is selected.
- **evidence**
  - run `api-first`, seed 1, turn 479 — The decision record shows stopped: no_target and rest_until_healed with the note that the warrior was at 15/40 HP.

