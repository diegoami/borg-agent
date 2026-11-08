# Plan

The requirements are in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md). Where
this plan and the requirements differ, the requirements win; say so in your
PR and propose a fix to whichever is wrong.

## Milestones, and when we stop for a review

A **milestone** is a named set of tasks. Inside a milestone a session works
normally: one task per branch and PR, and **it merges its own PR into `main`
once CI is green** — no approval needed, nothing waits for the owner.

**When the last task of a milestone is merged, the session stops.** It does
not start the next milestone's work. Instead it opens the **review PR**:

```sh
gh pr create --base reviewed --head main --title "Milestone N review: <what it delivers>"
```

- `reviewed` is a long-lived branch that stands at the last reviewed state of
  `main`. So the review PR's diff is **exactly everything delivered since the
  previous milestone**, with every task's commits in it.
- Its body lists the tasks in the milestone, what each one verified, what was
  not checked, and the open questions. The prompt a reviewer needs goes in the
  body or in a comment.
- The owner's reviewer — a model of another family, or the owner — goes
  through that PR and posts findings on it. Findings that span tasks may also
  be gathered in an issue; milestone 1's are in
  [#7](https://github.com/diegoami/borg-agent/issues/7).
- The **owner merges the review PR**, which advances `reviewed`. That is the
  only merge a session never makes (RULES 1).
- A session then turns the findings into a task of its own, as T12 does for
  milestone 1, and the next milestone begins.

| Milestone | What it delivers | Tasks | State |
|---|---|---|---|
| **1. Foundation** | the pinned game builds and plays reproducibly, the four schemas, and the model rule | T01, T02, T06's documents (D7) | **reviewed** on 2026-11-08 at `11c8303` ([#7](https://github.com/diegoami/borg-agent/issues/7)); `reviewed` stands there |
| **2. The connection** | an agent plays through the Borg's connection, every run replays exactly, and the executor's primitives exist | T03, T13 (D8), T04, T05, T12 | **complete; in review** ([#15](https://github.com/diegoami/borg-agent/pull/15)) |
| **3. The mind and the knowledge base** | a model plays, and what it learns becomes claims with evidence | T06, T07, T08 | not started |
| **4. Trial and pilot** | which model does which job is measured, the pilot runs, and the zoo can import a run | T09, T10, T11 | not started |
| later | the Neo adapter, mode C probes at scale, phase 2 (the Borg archaeologist) and phase 3 (the reconciler) | — | not started |

Milestones 1 to 4 together are the goal the requirements set for this stage:
**the agent plays the pinned C game through the Borg's connection, every run
replays exactly without the model, and a pilot produces its first claims with
evidence.** Phase 2, the Neo adapter and larger runs wait for the owner.

## The tasks

### Status

Each task's PR updates its row. Statuses: `todo`, `in progress` (with the
branch), `in review` (with the PR), `done` (merged).

| Task | Title | Milestone | Needs | Runs in a cloud session | Status |
|---|---|---|---|---|---|
| T01 | Build and play the pinned game headless | 1 | none | yes | done (#3) |
| T02 | Schemas | 1 | none | yes | done (#5) |
| T03 | C bridge | 2 | T01, T02 | yes | done (#8) |
| T04 | Recording and replay | 2 | T03 | yes | done (#11) |
| T05 | Executor primitives | 2 | T03 | yes | done (#12) |
| T06 | Mind and model calls | 3 | T02, T05 | yes, with the scripted and external minds | todo (documents done in #4; the loader and the minds are left) |
| T07 | Knowledge store | 3 | T02 | yes | todo |
| T08 | Post-mortem start from a Borg run | 3 | T04 | yes | todo |
| T09 | Model trial | 4 | T06, T07, T08 | with a profile whose key variables are set in the environment | todo |
| T10 | Pilot | 4 | T01–T09 | with a profile whose key variables are set in the environment | todo |
| T11 | Zoo import contract | 4 | T04 | yes | todo |
| T12 | Milestone-1 review findings | 2 | T01, T02 | yes | in review (#13) |
| T13 | Open the playing agent's sources (D8) | 2 | T02 | yes | done (#9) |

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
- a prompt pack, versioned, built from the sources of
  [docs/SOURCES.md](docs/SOURCES.md) — the manual is required, and decision D8
  allows the game source, the Borg source, the specification, the deaths, the
  issues and the zoo's results. The test that checks it is about **provenance,
  not permission**: every file a prompt draws on is named in `pins.json`'s
  `sources` (or recorded with its issue number and date), and the pack records
  which, so a claim made from that prompt can cite it;
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
1. **Decision quiz** (players). The quiz and its answer key never enter a
   prompt or the knowledge base: a candidate must not be able to read the
   answers (test hygiene, not a source rule — see decision D8). At least 30
   situations from Borg games on
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

### T13. Open the playing agent's sources (D8)

The owner's decision of 2026-11-08: the playing agent may read whatever helps
it build the knowledge base — the manual and the in-game help (required), its
own play, the game source, the Borg source and its documentation, the Borg
specification, the recorded deaths, the open issues and the zoo's results. The
earlier rule, that phase 1 saw only the manual, was not the owner's intent.

Done in this task:
- [docs/SOURCES.md](docs/SOURCES.md) rewritten: what may be read, where each
  source is pinned, and the two things still asked — provenance, and honesty
  about what was read rather than seen;
- the requirements: the phases table, the paragraph that made the phases a
  reading rule, D2 marked superseded, and **D8** recorded;
- `pins.json`: a `borg-spec` pin (diegoami/neo-angband-tracker) and a
  `sources` block naming each source with the pin it is read at; the issues
  are listed as unpinned, to be cited by number and date;
- `claim@1`: a basis for each source (`static:borg-spec`, `static:deaths`,
  `static:issue` beside the two that existed), the matching `sources` values,
  the phase-1 restriction removed, and a new rule that a `static:` basis must
  name its reference;
- the examples and the tests that encoded the old rule.

Left for later tasks, not this one:
- the prompt pack and its provenance test (T06);
- reading the deaths and the specification into actual claims — that is what
  T07's store and T08's post-mortems are for;
- `knowledge/` keeping fixtures out of the ingestion path (T12).

### T12. Milestone-1 review findings

A review of milestone 1 by a model of another family
([#7](https://github.com/diegoami/borg-agent/issues/7), 2026-11-08) found
thirteen things. Six were fixed in T03's PR, one in T04's, one in T13's; the
rest are done here. Each item keeps the review's own number.

**Done in this task:**

- **(1) The game is not date-independent.** `get_mon_num` reads the clock and
  admits seasonal monsters on 24-26 December, so the same seed plays a
  different game on those days. Every run now records `calendar.seasonal`, and
  `verify` **refuses to compare** a run and a replay that fall on different
  sides of that window: it reports `comparable: false` with the reason instead
  of calling it a failure to reproduce. Neutralizing that clock read, as the
  zoo's recording profile does, would make the build differ from the unpatched
  game on three days a year, which RULES 9 forbids without the owner's
  say-so — see "For the owner" below.
- **(4) The claim lifecycle.** `produced_by` is required and a model names
  itself and its family; every review names a family (null for a probe); run
  evidence names its seed; anything above `hypothesis` rests on counted trials
  or on a review. The two rules that compare fields — a review by the
  producer's own family does not promote, and a `quantified` basis may not
  claim more successes than trials — are in `borg_agent.checks`, with tests
  for the same-family, disagreeing, probe and model-promotes-itself cases.
- **(7) The observation's knowledge rule.** `true_state.fields` must name
  exactly the fields it carries, checked by `borg_agent.checks` on every
  observation the bridge writes; the level feeling's danger and treasure
  numbers are gone from the ordinary map, since the player sees words.
  `docs/SCHEMAS.md` no longer claims the schema enforces what it cannot.
- **(6) Runner parity.** The recipe's `ui-game.c` replacement regained the
  indentation it had lost, so all six sites are byte-identical to the
  runner's, and four tests now parse `tools/measure-native.py` at the runner
  pin and compare the replacements, the include list, the CMake arguments and
  the activation block.
- **(5) Keys.** `record.validate` refuses a record with a key-shaped field
  name or a credential-shaped value anywhere in it, not only in the mind
  block, with tests for a key in a note, in `endpoint_host` and in a URI.
- **(10) The build key** now covers the include line, the CMake lines, the
  version suffix, the compiler and the platform, so none of them can be served
  from the cache; `--output` already refused to delete what is not a build.
- **(9) The examples** carry a README saying they are fixtures, not knowledge,
  and must not enter `knowledge/`, a prompt pack or any ingestion path. The
  run-record examples are generated by `scripts/refresh-examples.py`.
- **The weak tests.** The assertion-free one now checks that the build key is
  order-independent and stable; the birth input is compared with the runner's
  own `INPUT` at the pin, character for character; the outcome vocabulary is
  read from the zoo's `docs/DESIGN.md` at its pin; `models.yaml`'s trial lists
  are checked so T09 can always pair a reviewer of another family (finding 8);
  and three paths that were untested now have slow tests — a **death with the
  checkpoint saves** (the fork-and-save path T08 needs), and a **slow mind**,
  which found that the stall clock still spanned the mind's thinking. It now
  starts when the action goes out, so model latency cannot become an outcome
  (finding 2 again).

**For the owner**, from finding 1: neutralizing the game's one `time()` read
would make replay independent of the date, at the price of play differing from
the unpatched build on 24-26 December. That is a RULES 9 exception, so it is
the owner's call. Until then, a run made in that window can only be replayed
in it, and `verify` says so.

**Left for later tasks, not this one:** `mind` is still one block where R2.4
speaks of three jobs (finding 3's remainder) — that becomes real in T06, when
one run may call more than one model; and the regex reader standing in for
YAML in `tests/test_models_file.py` goes when T06's loader lands.

## After milestone 4 (not started)

- Neo Angband adapter (R1.5).
- Mode C probes at scale, and repeat runs to measure how much the agent
  varies.
- Phase 2, the Borg archaeologist, and phase 3, the reconciler.

Each of these becomes a milestone of its own, reviewed the same way.
