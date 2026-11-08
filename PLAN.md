# Plan

The requirements are in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md). Where
this plan and the requirements differ, the requirements win; say so in your
PR and propose a fix to whichever is wrong.

## Milestone 1: a first learner on C 4.2.6

Goal: the agent plays the pinned C game through the Borg's connection,
every run replays exactly without the model, and a pilot produces its first
claims with evidence. Stop after the pilot report (T09). Phase 2, the Neo
adapter and larger runs wait for the owner.

### Status

Each task's PR updates its row. Statuses: `todo`, `in progress` (with the
branch), `in review` (with the PR), `done` (merged).

| Task | Title | Needs | Runs in a cloud session | Status |
|---|---|---|---|---|
| T01 | Build and play the pinned game headless | none | yes | todo |
| T02 | Schemas | none | yes | todo |
| T03 | C bridge | T01, T02 | yes | todo |
| T04 | Recording and replay | T03 | yes | todo |
| T05 | Executor primitives | T03 | yes | todo |
| T06 | Mind and model calls | T02, T05 | yes, with the scripted and external minds | todo |
| T07 | Knowledge store | T02 | yes | todo |
| T08 | Post-mortem start from a Borg run | T04 | yes | todo |
| T09 | Pilot | T01–T08 | only with a model key in the environment (AGENTS.md) | todo |
| T10 | Zoo import contract | T04 | yes | todo |

### T01. Build and play the pinned game headless

Build the `better-borg-c` pin (see [pins.json](pins.json)) the way the zoo's
runner does (`tools/measure-native.py` at the `runner` pin): extract the tree
with `git archive`, instrument it by text replacement, configure with CMake
(`-DSUPPORT_BORG=ON -DSUPPORT_TEST_FRONTEND=ON -DSUPPORT_X11_FRONTEND=ON`),
and play through the test frontend with a scripted birth input.

Done when:
- `scripts/setup.sh` and one build command produce the game binary in a
  fresh cloud session and in CI (Ubuntu 24.04, `libx11-dev`);
- the stock Borg plays seed 7, an assigned Human Warrior, to a 5,000-turn
  cap twice, with byte-identical traces;
- the build is cached by source and patch hash, and build output stays out
  of git.

### T02. Schemas

The observation, action, run record and claim (R1, R4, R5), each versioned,
as JSON Schema files under `schemas/`, with valid and invalid examples and
tests. The run record uses the zoo's outcome vocabulary plus `budget_cap`
(R5). The claim follows the lifecycle in R4.

### T03. C bridge

A patch, applied like the runner's instrumentation, that gives the game's
input to an outside process instead of the Borg's thinking:
- at the Borg's `inkey_hack` entry, with the agent mode on, write one
  observation (R1) to the agent and wait for one action;
- fill the observation from the Borg's own state-reading code where it fits
  (the map from the player's knowledge, the character state, messages, the
  screen for prompts and menus); name any true-state field as such and keep
  it off by default;
- translate actions to keys inside the bridge; log raw keys as raw;
- with the agent mode off, the game and the Borg behave exactly as without
  the patch: the T01 trace is unchanged.

Done when a scripted Python mind plays a level-1 character from birth for
1,000 game turns, twice, with identical recorded action streams and
outcomes.

### T04. Recording and replay

`verify`, `view`, `dump`, `branch` and `explain` (R5). A run record holds
the seed, birth, settings, pins, patch hashes and the action stream with its
SHA-256. Replay feeds the action stream back without the mind.

Done when, for runs from T03 and T05:
- play, then `verify`, gives the same outcome and the same state hashes at
  every observation;
- `branch` at turn T continues with another mind, and its record names the
  parent run and T.

### T05. Executor primitives

The primitives in R2: walk to, explore the floor, fight the nearest
monster, rest until healed, take the stairs, flee by stairs or Phase Door,
read an unknown scroll, shop a list. Each runs until something changes and
reports why it stopped.

They are mechanical (see [docs/SOURCES.md](docs/SOURCES.md)): no Borg
tactics, thresholds or valuations. Tests use fixed seeds and fixtures.

### T06. Mind and model calls

The mind chooses the next primitive or command at the moments in R2, with a
one-line reason. Three backends behind one interface:
- `scripted`: deterministic rules, for tests only;
- `external`: each decision is written to a file and the answer read back,
  so a person or a coding session can play a few decisions for debugging;
- `api`: a model over an OpenAI-compatible chat API, configured by
  `BORG_AGENT_BASE_URL`, `BORG_AGENT_API_KEY` and `BORG_AGENT_MODEL`.

Also:
- a prompt pack, versioned, built only from the allowed sources
  ([docs/SOURCES.md](docs/SOURCES.md)), with a test that checks it;
- every call logged (R2.1);
- a budget cap per run (R2.3);
- the `api` backend's model chosen per run by the owner's model rule on
  the owner's machine, or taken from the environment in a cloud session
  (AGENTS.md), and recorded either way.

### T07. Knowledge store

Claims in JSON Lines under `knowledge/`, a generated Markdown view per area,
and consolidation (mode D) that turns notes into `hypothesis` claims with
evidence pointers. The model never sets a status above `hypothesis` (R4.3).
Tests cover the lifecycle rules and the views.

### T08. Post-mortem start from a Borg run

Mode B (R3) needs a game the Borg played up to some turns before its death.
Play the `better-borg-c` pin's Borg on a zoo seed and birth, record its
action stream with the bridge watching (the Borg still decides), stop k
turns before the recorded death, and hand over to the agent with `branch`.

The first cases, from the zoo's `classes-m6` results (cause "a floating
eye", specimen `4.2.6-bbc-m6`, cap 100,000):
- seed 1865911738, Half-Troll Mage;
- seed 1375157069, Dunadan Priest.

Done when replaying the Borg's prefix reproduces the zoo's death when left
to the Borg, and a branch k turns before it hands over to another mind.

### T09. Pilot

Run on the owner's machine, or in a cloud session whose environment
provides a model (AGENTS.md). Mode A: 9 runs, one
per class, Human, 20,000 game turns each. Mode B: both T08 cases, each with
at least two branches.

Report in `docs/reports/pilot-1.md`:
- for each run: the outcome, maximum depth and level, model calls, tokens
  and wall time;
- whether `verify` reproduced every run;
- the claims produced, with their evidence;
- the cost;
- anything that could not be done without changing play.

### T10. Zoo import contract

A document, `docs/ZOO-IMPORT.md`, for the zoo's own PR (R6): the run record
fields the zoo needs, how its CI replays an imported run without a model,
the build it needs for that, and how agent runs are marked
non-deterministic. The zoo itself is not changed here.

## Later milestones (not started)

- Neo Angband adapter (R1.5).
- Mode C probes at scale, and repeat runs to measure how much the agent
  varies.
- Phase 2, the Borg archaeologist, and phase 3, the reconciler.
