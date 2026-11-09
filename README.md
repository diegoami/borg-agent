# borg-agent

**Frozen on 2026-11-09, deliberately, and it will be picked up again.** Read
"Why it is frozen" below before starting anything.

## What this is for

The purpose has never been to win Angband. It is to produce **knowledge a later
Rust Borg can be built from** — the "Borg reborn" of
[borg-rs](https://github.com/diegoami/borg-rs) — in a form a person can review,
an experiment can check, and a program can act on.

How that knowledge was to be produced changed twice, and the second change is
the one that stands:

| | How | Why it was left |
|---|---|---|
| **1. An agent plays** (milestones 1–4, built) | a language model plays the pinned C game through the Borg's own connection and writes down what it learns | it works, and it was the wrong economy: every *counted* claim it produced came from a probe, not from play. Model games are slow, expensive and thin |
| **2. The agent plays better** ([docs/PLAY-SPEC.md](docs/PLAY-SPEC.md), specified, never built) | the game's own words and the game's own router, with every judgement in the model | overtaken before it was built |
| **3. The death analyser** ([docs/DEATH-ANALYSIS-SPEC.md](docs/DEATH-ANALYSIS-SPEC.md), specified) | **a Borg death in, leads out.** No playing, no model keys: a deterministic extractor here, and a skill carrying the game's rules and manuals as fixed context | **this is the intent.** It needs a Borg worth analysing — see below |

The third is the pivot, in the owner's words:

> *"what we could build is a tool that using the knowledge of the game could
> analyze death replays and produce leads of what could be improved in a
> situation… the output would be leads, not certainty, of what a borg might
> want to improve. No more playing."*
>
> *"we do not need even external LLM keys, we would just build a skill, with
> fixed context containing the rules of game, strategic manual and so on, and
> we could evaluate a borg replay and return a diagnostic automatically, for
> the borg reborn to reuse."*

## Why it is frozen

**The deaths available to analyse are of a Borg that cheats.** The milestone 8
tree defaults `borg_munchkin_by_class = TRUE`, which — by the Borg's own source
comment — gives Warriors, Druids and Rangers a munchkin start whatever
`borg_munchkin_start` says: stair-scumming, conjured items, "Power Diving".
Every Borg run this repository made before the freeze was one of those, and the
curated death corpus and the zoo's cohort are run on the same defaults
(T34 in [PLAN.md](PLAN.md)).

Analysing those deaths would produce leads about a mode nobody wants to keep.
And with munchkin off, this Borg barely descends: twelve seeds reached **depth
2–3 in 30,000 turns** and none of them died, so there is nothing to analyse
either.

So the tool is specified and not built, because its input does not exist yet.

## When it becomes useful again

Any one of these makes the analyser worth building:

1. **A Borg reborn worth analysing.** borg-rs is the subject this knowledge is
   for. When it plays and dies, its deaths are the input, and the leads go
   straight to the thing being improved.
2. **A munchkin-free death corpus.** Either better-borg-c changes the default,
   or the zoo runs a profile with it off, or the thirteen curated cases are
   re-run without it. Then the existing corpus becomes usable and the 36
   hand-written leads in its `index.json` become the tool's validation set.
3. **A deeper cohort.** Deaths exist in the mode we care about at higher caps
   or at depth; nothing here has looked past 30,000 turns in normal mode.

## What is already built, and stays useful

None of this depends on how knowledge is produced:

- the pinned game **builds and plays reproducibly**, by the zoo's own recipe,
  with the observer and runner byte-identical to the zoo's at its pin;
- a **bridge** on the Borg's own `inkey_hack` hook: one observation out, one
  action in, with the game and the Borg otherwise untouched;
- **records and replay** — `verify`, `view`, `dump`, `branch`, `explain` — so a
  run is evidence and a *lead can be tested* by replaying from a turn with an
  alternative, which is what the analyser's `how_to_test` asks for;
- **mode C probes**: one question, counted trials, and the only promoter of a
  claim that is not another model;
- the **knowledge base**: claims in git with their evidence, and the lifecycle
  that keeps a model from promoting its own;
- a **report**: one run as a self-contained HTML page — timeline, model calls
  with their prompts and reasoning, maps;
- the **zoo import contract**, for when agent or probe runs are imported.

## Where to read

| | |
|---|---|
| [AGENTS.md](AGENTS.md) | for any session that opens this repository — **start here** |
| [docs/DEATH-ANALYSIS-SPEC.md](docs/DEATH-ANALYSIS-SPEC.md) | the intent: what to build when it thaws |
| [docs/HANDOVER.md](docs/HANDOVER.md) | the state at the freeze, and what was learned |
| [PLAN.md](PLAN.md) | the milestones and every task, with what each found |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | what the repository must do, and the owner's decisions D1–D14 |
| [RULES.md](RULES.md) | how a session works here |
| [docs/PLAY-SPEC.md](docs/PLAY-SPEC.md) | the playing design, kept as the record of why it was dropped |
| [docs/BUILD-AND-PLAY.md](docs/BUILD-AND-PLAY.md) · [docs/BRIDGE.md](docs/BRIDGE.md) · [docs/RECORDS.md](docs/RECORDS.md) · [docs/EXECUTOR.md](docs/EXECUTOR.md) · [docs/MINDS.md](docs/MINDS.md) · [docs/KNOWLEDGE.md](docs/KNOWLEDGE.md) · [docs/PROBE.md](docs/PROBE.md) · [docs/POST-MORTEM.md](docs/POST-MORTEM.md) · [docs/SCHEMAS.md](docs/SCHEMAS.md) · [docs/SOURCES.md](docs/SOURCES.md) · [docs/ZOO-IMPORT.md](docs/ZOO-IMPORT.md) | the parts, each as it stands |

Tests: `python -m pytest -q` (424, seconds) and `pytest -m slow` (20, which
build the game and play it — about half a minute now that the Borg no longer
stair-scums).
