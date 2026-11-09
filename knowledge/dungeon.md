# Dungeon claims

*Generated from `claims.jsonl` by `python -m borg_agent knowledge views`. Do not edit: a claim changes by being superseded, never by being rewritten.*

## On turn 1, taking the down stairs in the town moved the Human Warrior to dungeon depth 1.

- **id** `town-down-stairs-enter-depth-1` · **status** hypothesis
- **basis** observed
- **scope** class Warrior, race Human, version 4.2.6, character level 1–1, depth 1–1
- **engine** c-4.2.6 · **phase** 1 · **sources** own-play
- **rests on** The turn-1 take_stairs action is followed by a level change, and the run's recorded depth is 1.
- **ruled out**: The level change might have been within town; ruled out because the run summary identifies the reached depth as dungeon depth 1.
- **how to test it** Start a Human Warrior in town, move to the down staircase, issue take_stairs, and check that the current depth becomes 1.
- **evidence**
  - run `api-first`, seed 1, turn 1 — The decision log records explore_floor, then take_stairs with stopped: changed_level; the run summary records depth 1.

