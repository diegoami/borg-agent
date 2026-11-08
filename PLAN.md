# Plan

The requirements are in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md). Where
this plan and the requirements differ, the requirements win; say so in your
PR and propose a fix to whichever is wrong.

## Milestone 1: a first learner on C 4.2.6

Goal: the agent plays the pinned C game through the Borg's connection,
every run replays exactly without the model, and a pilot produces its first
claims with evidence. Stop after the pilot report (T10). Phase 2, the Neo
adapter and larger runs wait for the owner.

### Status

Each task's PR updates its row. Statuses: `todo`, `in progress` (with the
branch), `in review` (with the PR), `done` (merged).

| Task | Title | Needs | Runs in a cloud session | Status |
|---|---|---|---|---|
| T01 | Build and play the pinned game headless | none | yes | done (#3) |
| T02 | Schemas | none | yes | done (#5) |
| T03 | C bridge | T01, T02 | yes | in review (#8) |
| T04 | Recording and replay | T03 | yes | todo |
| T05 | Executor primitives | T03 | yes | todo |
| T06 | Mind and model calls | T02, T05 | yes, with the scripted and external minds | todo (documents done in #4; the loader and the minds are left) |
| T07 | Knowledge store | T02 | yes | todo |
| T08 | Post-mortem start from a Borg run | T04 | yes | todo |
| T09 | Model trial | T06, T07, T08 | with a profile whose key variables are set in the environment | todo |
| T10 | Pilot | T01–T09 | with a profile whose key variables are set in the environment | todo |
| T11 | Zoo import contract | T04 | yes | todo |
| T12 | Milestone-1 review findings | T01, T02 | yes | todo |

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
- `api`: a model over an OpenAI-compatible chat API, configured by the active
  profile in `models.yaml` (decision D7).

Also:
- a prompt pack, versioned, built only from the allowed sources
  ([docs/SOURCES.md](docs/SOURCES.md)), with a test that checks it;
- every call logged (R2.1);
- a budget cap per run (R2.3);
- **`models.yaml` at the root, and its loader.** The file holds the
  providers (base URL and the **name** of the environment variable that
  holds the key, each URL taken from the provider's own documentation and
  cited in the file), one model per job in each named profile (`play`,
  `consolidate`, `review`), and the model trial's candidates under `trial:`.
  It never holds a key. The active profile is the first of
  `BORG_AGENT_PROFILE`, `profile:` in the git-ignored `models.local.yaml`
  (which may also override single jobs) and `default_profile`.

  The loader:
  - validates the file against a JSON Schema in `schemas/`: the profile and
    its providers exist, every job is present, `review.family` differs from
    `consolidate.family` (R4.3), and the trial lists name known providers;
  - refuses any field whose name contains `key` other than `api_key_env`,
    in `models.yaml` and in `models.local.yaml`;
  - reads each key from the environment variable its provider names, and
    fails before play when the variable is unset, naming the variable and
    never its value;
  - gives each job its context size from `context_k`, with a default when
    it is missing (R2.2);
  - reports, per job, the profile, provider, model and family, how they were
    chosen (`profile`, `local override` or `environment`) and the SHA-256 of
    `models.yaml` and of `models.local.yaml` when it exists, for the run
    record. Never a key, a request header or a URL with credentials.

  Tests cover the schema, the three ways of choosing a profile, the job
  overrides, the family rule, the key-field refusal and the missing-variable
  failure.

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

### T09. Model trial

Which model should do which job is measured, not assumed. The jobs differ:

| Job | Calls | What matters |
|---|---|---|
| Player: choosing the next primitive or command | hundreds per game | a valid action every time, speed, cost |
| Consolidator: post-mortems and turning notes into claims | a few per game | careful reasoning, no invented facts |
| Reviewer: checking claims | a few | a different model family from the consolidator (R4.3) |

**Candidates** come from `trial:` in `models.yaml` (decision D7), per job,
the same way locally and in a cloud session; the owner adds or removes
candidates by editing that list. A candidate whose provider's key variable is
unset is skipped, and the report says so. Each candidate has a budget cap for
the whole trial.

**Three parts**, the same prompt pack for every candidate:
1. **Decision quiz** (players). At least 30 situations from Borg games on
   zoo seeds: windows a few turns before a death, and first sightings of a
   monster. For each situation, try every action the executor offers as a
   `branch`, let the stock Borg play on for 2,000 game turns, and record
   which branches survive. That is the answer key, made by the game, not by
   a person or a model. A candidate scores by how often its choice is among
   the surviving branches, against the best and the worst choice available.
   The quiz and its key never enter a prompt or the knowledge base.
2. **Short games** (players): 3 classes (Warrior, Mage, Priest) × 3 seeds ×
   5,000 game turns per candidate. Measure the share of valid actions, parse
   failures, calls and tokens per game turn, latency, depth, level and
   deaths.
3. **Post-mortems** (consolidators): both T08 floating-eye cases, the same
   replay windows for every candidate. Count the claims each produces and
   check each one: by a probe where one can be run, otherwise by a reviewer
   candidate of another family. The number that matters most is **false
   claims**, since the knowledge base is the product.

Report in `docs/reports/model-trial.md`: per candidate and part, the scores,
cost and failures, and a recommendation per job. The owner picks the models
per job; that choice is recorded in the requirements as decision D6 and
used by T10.

### T10. Pilot

Run on the owner's machine, or in a cloud session whose environment
provides a model (AGENTS.md), with the models the owner chose in T09.
Mode A: 9 runs, one
per class, Human, 20,000 game turns each. Mode B: both T08 cases, each with
at least two branches.

Report in `docs/reports/pilot-1.md`:
- for each run: the outcome, maximum depth and level, model calls, tokens
  and wall time;
- whether `verify` reproduced every run;
- the claims produced, with their evidence;
- the cost;
- anything that could not be done without changing play.

### T11. Zoo import contract

A document, `docs/ZOO-IMPORT.md`, for the zoo's own PR (R6): the run record
fields the zoo needs, how its CI replays an imported run without a model,
the build it needs for that, and how agent runs are marked
non-deterministic. The zoo itself is not changed here.

### T12. Milestone-1 review findings

A review of milestone 1 by a model of another family
([#7](https://github.com/diegoami/borg-agent/issues/7), 2026-11-08) found
thirteen things. The small ones were fixed in T03's PR; what is left is this
task. Each item keeps the review's own number.

**The game is not date-independent (1).** `get_mon_num` reads the clock and
admits seasonal monsters on 24-26 December, so the same seed plays a
different game on those days — proved with a fixed clock. T03's PR records a
`calendar` block in every run and the docs and the golden-hash test carry the
caveat. What is left: neutralize that one `time()` read in the instrumented
build, the way the runner's recording profile does, and record that it was
neutralized; or make replay set the recorded date. With a test that plays one
seed under two controlled dates. This blocks nothing today but it threatens
T08's post-mortem replay, T10's `verify` and the zoo's CI (R6.2).

**`run-record@1` under-requires what R5 names (3).** Birth rule and options,
settings and their hash, content identity, the repository commit and dirty
state, the birth input's hash, the calendar, and for an `api` mind the
budget, context size and knowledge hash. Also: `mind` is one block but R2.4
asks per job; `mode: consolidate` should not force a seed and a cap; the
runner's `saved` outcome is not representable. With a test that a minimal
record cannot validate.

**`claim@1` does not enforce the R4.3 promotion rule (4).** A model-produced
claim can reach `supported` with no review; a `corroborated` claim can rest
on a review by its producer's own family, or one with `verdict: disagree`;
`quantified` accepts more successes than trials; run evidence need not name a
seed. Require `produced_by.model` and `.family` for a model, require
`reviews[].family`, require an agreeing review or a probe basis above
`hypothesis`, and give a probe a way to corroborate. T07 checks what the
schema cannot.

**`observation@1` is a shape, not a knowledge guard (7).** Nothing ties
`true_state.fields` to the keys present, and `level_feeling.danger` and
`treasure` are integers in the ordinary map where the player sees a feeling.
Fix the schema, add a recorder-side check, and temper
[docs/SCHEMAS.md](docs/SCHEMAS.md).

**The recipe is a hand copy of the runner's (6).** Five of six sites are
byte-identical; `ui-game.c` differs by indentation. Derive the recipe from
`tools/measure-native.py` at the runner pin, or compare against it in a test,
so a runner change cannot leave this build silently stale.

**Keys in free text (5).** `endpoint_host` takes any string, including a URL
with credentials, and `notes` takes anything. Constrain the host, constrain
the model, provider and profile fields, scan free text when T04 writes a
record, and test that a fake key in the environment never reaches a record or
a log. The game's own environment was fixed in T03's PR.

**The examples carry game and zoo knowledge (9).** One claim example states
the zoo's Druid/Paladin finding with `sources: ["own-play"]`, which is false
provenance. Make the examples honest, label them as illustrative, and keep
them out of `knowledge/`, prompt packs and any ingestion path. Phase 1 also
has no source value for the seed, birth, cause and turn a mode B post-mortem
is given, which T08 needs.

**The build key does not cover every input (10).** The fixed include line,
the appended CMake lines, the `version` file and the compiler and platform are
outside it, so a changed build can be served from the cache. CI's cache key
should name the image too.

**Weak tests (the review's test section).** Among them: a test that asserts
nothing, the birth input compared by prefix instead of to the runner's own
`INPUT`, the zoo's outcome vocabulary copied rather than read at the pin, a
regex reader standing in for YAML, and no coverage of the death or checkpoint
paths, a slow mind, or the claim lifecycle's real cases.

Not in this task, because they are the owner's: which profile
`default_profile` should name, and whether the OpenRouter reviewer is the free
variant or the paid one (review finding 8).

## Later milestones (not started)

- Neo Angband adapter (R1.5).
- Mode C probes at scale, and repeat runs to measure how much the agent
  varies.
- Phase 2, the Borg archaeologist, and phase 3, the reconciler.
