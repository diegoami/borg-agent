# Sources: what each role may read

Phase 1's knowledge has to be what a player can learn (requirements,
"Phases"). That rule is about **what reaches the playing agent**: its
prompts, its retrieved knowledge and its notes. It is not a rule about what
the developer of this repository may read.

## The playing agent (phase 1)

May receive:
- the manual: the files listed under `manual` in [pins.json](../pins.json),
  at the `better-borg-c` pin. These are the game's own "Getting Started" and
  "The Manual" pages, and the in-game help;
- what the game shows during play: the observation (R1), monster recall and
  object descriptions as the game prints them to the player;
- its own knowledge base: claims and notes produced by phase 1.

Must not receive:
- game source, the gamedata files under `lib/gamedata/`, or the developer
  pages under `docs/hacking/` (including `docs/hacking/borg.rst`);
- the Borg source or its documentation;
- spoilers, wiki pages or forum posts;
- zoo results, beyond the facts a mode B post-mortem is given: the seed, the
  birth, the cause of death the game printed and the turn.

Prompt packs are checked by a test: no file outside the allowed list is
read into a prompt.

## The developer (any session working on this repository)

May read everything public, including the C game and Borg source, because the
bridge (R1) has to attach to it. The care needed is the other way round:
- the **executor** primitives (R2) are mechanical: pathing, resting until a
  condition, taking stairs, following a shop list. They contain no tactics
  taken from the Borg, such as its danger estimates, flee thresholds or
  item valuations. Choosing between primitives is the model's job;
- the **prompt packs** contain no game knowledge the developer brought from
  the source, spoilers or experience. If a prompt needs a fact, the fact
  comes from the manual or from a claim with evidence.

A review of an executor or prompt-pack PR checks both points.

## Phases 2 and 3

The Borg archaeologist and the reconciler may read everything, and record
for each claim which sources it used (requirements, R4).
