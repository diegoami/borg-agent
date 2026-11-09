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
| **1. Foundation** | the pinned game builds and plays reproducibly, the four schemas, and the model rule | T01, T02, T06's documents (D7) | **reviewed** on 2026-11-08 at `11c8303` ([#7](https://github.com/diegoami/borg-agent/issues/7)) |
| **2. The connection** | an agent plays through the Borg's connection, every run replays exactly, and the executor's primitives exist | T03, T13 (D8), T04, T05, T12, T14, T15, T16 | **reviewed and merged** on 2026-11-09 ([#15](https://github.com/diegoami/borg-agent/pull/15), reviewed twice); `reviewed` stands at that merge |
| **3. The mind and the knowledge base** | a model plays, and what it learns becomes claims with evidence | T06, T07, T08; the pins T17 and T18 and the sources T19 and T20 landed here too | **in progress**: T17–T20 done, T06 next |
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
| T12 | Milestone-1 review findings | 2 | T01, T02 | yes | done (#13) |
| T13 | Open the playing agent's sources (D8) | 2 | T02 | yes | done (#9) |
| T14 | The heavy-run lock under an outer flock | 2 | T03 | yes | done (#16) |
| T15 | Milestone-2 review findings | 2 | T04, T05 | yes | done (#18) |
| T16 | Milestone-2 re-review findings | 2 | T15 | yes | done (#20) |
| T17 | Pin better-borg-c milestone 8 | 3 | T03 | yes | done (#24) |
| T18 | Pin the Rust remake (borg-rs milestone 7) | 3 | T13 | yes | done (#26) |
| T19 | The strategy manual and the online command reference as sources | 3 | T13 | yes | done (#30) |
| T20 | The user manual as a source | 3 | T19 | yes | done (branch `claude/elegant-volta-r5qdic`) |

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

The first cases were the zoo's `classes-m6` results (cause "a floating eye",
specimen `4.2.6-bbc-m6`, cap 100,000): seed 1865911738, Half-Troll Mage, and
seed 1375157069, Dunadan Priest. **They are deaths of a build we no longer
play**: T17 moved the pin to milestone 8, and the zoo has no m8 results (its
newest bbc specimen is m7). So this task first says where its cases come
from — `docs/deaths/` at the pin (19 recorded deaths), deaths our own build
produces, or a zoo run of m8 the owner commissions — and records the choice.
The floating-eye question itself still stands: it killed 4 of 13 Mandos
characters in `mandos-classes-18`.

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

### T20. The user manual as a source

The owner, 2026-11-09, after T19: add `docs/user-manual.md` from the same
branch too.

- The pin is renamed **`c-borg-reference`**, after the branch, since it now
  serves two documents; nothing had read it under its first name. `sources`
  gains `user_manual` at that pin.
- `claim@1` gains the source `user-manual` and the basis `static:user-manual`
  (additive; never `documented`).
- A test reads the file at the pin and finds its command reference and its Borg
  chapter. Its tables come from `lib/gamedata/`, which T19's test keeps equal
  to the game pin's.
- A spot-check of its key table (original and roguelike) against
  `docs/command.rst` agreed, including the `autoexplore_commands` key. Nothing
  else in its 3,700 lines was checked.

### T19. The strategy manual and the online command reference as sources

The owner, 2026-11-09: include
[docs/strategy on neo-angband-tracker's `c-borg-reference` branch](https://github.com/diegoami/neo-angband-tracker/tree/c-borg-reference/docs/strategy)
and [the online command reference](https://angband.readthedocs.io/en/latest/command.html)
in the sources.

- **The strategy manual** is a new pin at `471e1214` (named `strategy-manual`
  here, renamed `c-borg-reference` in T20)
  (the branch's head that day), and a `strategy_manual` entry in `pins.json`'s
  `sources`. The branch is angband/angband `e473720` (our `original` pin) plus
  three documentation commits, and its `lib/gamedata/` is byte-identical to the
  game pin — a test keeps that true, since the appendices are generated from
  it. Its README links to eight chapters that are not in the tree, and its
  prose was written by a model, so docs/SOURCES.md says how far to trust it.
- `claim@1` gains the source `strategy-manual` and the basis
  `static:strategy-manual` (additive; a claim read there is never
  `documented`), with a valid example.
- **The online page** is `manual_online`, unpinned, with `pinned_as`
  `docs/command.rst` at the `better-borg-c` pin: angband/angband's `master` was
  at `e473720` that day and the file is byte-identical there and at the game
  pin. The page itself could not be fetched from the cloud session (the
  network does not allow readthedocs), so it was compared through its source
  file, not its rendering.

### T18. Pin the Rust remake (borg-rs milestone 7)

The owner, 2026-11-09: borg-rs is at milestone 7. That is the Borg reborn this
repository's knowledge is for, so it is pinned and readable like any other
source (decision D8): `ce27f5ed`, "Impact v7: carry better-borg-c milestone 7".

Why it belongs here:
- **Phase 3 reconciles against it.** A recommendation the remake has already
  taken is worth knowing as such, and a claim that contradicts it is worth
  knowing even more. Pinning fixes which version a claim argued with.
- **It has the same connection.** `borg-rs/src/borg.rs` holds the
  `inkey_hack` callback the bridge attaches to on the C side, so a claim about
  the connection carries over rather than being C-specific.
- 59 Borg modules under `borg-rs/src/`, one per original `src/borg/<x>.c`,
  with no `unsafe` outside the FFI boundary.

**The pin will move, and often.** When this was written the game pin was
better-borg-c milestone 8 and borg-rs carried milestone 7, with the owner
building milestone 8 the same day. So the number is not the point: a claim
says which side of the port and which milestone it is about, both roles name
a milestone, and the test checks that they name one rather than which one.

### T17. Pin better-borg-c milestone 8

The owner, 2026-11-09: pin better-borg-c at **milestone 8**
(`4.2.6-impact-v8`, `017e038e`), which carries 88 fixes where milestone 6
carried 63.

What it took, and what it changed:
- the six observer sites and every game and Borg function the bridge calls are
  still there, so the recipe needed no change;
- `borg_what_text` gained a buffer-size argument between the two milestones;
  the bridge passes it;
- the tree now has its own `measure_activate_borg`, so the runner's "add it if
  missing" is a no-op there. The test that asserted it was absent now asserts
  the instrumented tree ends up with exactly one, either way;
- `tools/measure-native.py` and the observer are **byte-identical** at the
  runner pin and at milestone 8, so the parity tests are untouched;
- the manual, the deaths (19 entries, up from 15) and the spec all read at the
  new pin.

Facts about milestone 8 itself, measured on seed 7 at cap 5,000: the trace is
`a6ffbae0…` and 542,917 bytes where milestone 6 gave `2242a3f5…` and 53,040,
and a run takes about 15 seconds where it took 1.9. **It also survives seed 7
to 100,000 turns, where milestone 6 died to a green naga at 27,808** — which
is what a better Borg looks like, and what cost the death gate its old shape:
that gate now takes its death from an agent run, which also gave agent runs
the runner's `--checkpoint-saves` option that T08 wanted anyway.

**What this costs T08** (and the owner may want to decide): its two
floating-eye cases — seed 1865911738 Half-Troll Mage, seed 1375157069 Dunadan
Priest — are deaths of the zoo's `4.2.6-bbc-m6` specimen. The zoo's newest
bbc specimen is `4.2.6-bbc-m7`; there are **no m8 results at all**. So those
two deaths are no longer deaths of the build we play. T08 can take its cases
from `docs/deaths/` at the new pin (19 recorded deaths), from deaths our own
build produces, or from a zoo run of m8 if the owner wants one; the task says
which when it starts.

### T16. Milestone-2 re-review findings

The same reviewer (Kimi K3) read T15's fixes and found **two new issues, both
in the new code** — one of them a hole the fix itself opened. Both are closed
here, and the reviewer confirmed all four original findings closed in
substance.

- **(1) `prefix` accepted a run cut short at the end.** With both logs
  truncated by three decisions and the record left intact, `verify` said
  `verified: true` — the replay reproduced the states that remained, and the
  new tolerance (`len(after) in (N, N+1)`) left room for a stream that ends
  early. The old exact-length comparison had caught this by accident. Now
  `check_record_against_run` compares **every** count and hash the record
  published — the action stream's count and hash, the observations, the state
  hashes, the journal — against the files the replay actually read, and names
  the first that disagrees. The reviewer's own experiment is a slow test, and
  five fast ones cover each stream and a missing file.
- **(2) A branch lost its journal.** The run drains the journal from the mind
  it was given, which for a branch is the `replay` mind; the mind that took
  over kept its entries to itself. Since mode B *is* "replay, then try
  something else", the journal was missing exactly where it was added to help.
  `ReplayMind.drain_journal` now passes through to the mind that took over, and
  a slow test branches with a primitive chooser and checks the entries are
  there and all after the handover.
- **Also from the re-review:** journal entries buffered during a decision were
  lost when the mind raised, so the stops that led to `agent_stopped` never
  reached the log — they are written now; and the **Home** is described the way
  its own screen describes it (in full, no prices), which was the one
  remaining fidelity gap in the shop block.
- Documented: that `prefix` compares no part of the trace by construction;
  that a replay's own outcome reads `agent_stopped` because the vocabulary has
  no word for "the recording ended"; and that run directories made before T15
  cannot be recorded, which is deliberate.

### T15. Milestone-2 review findings

A review of milestone 2 by a model of another family (Kimi K3) on
[#15](https://github.com/diegoami/borg-agent/pull/15), 2026-11-09. Four
findings, with notes and doc drift. All four are done here, and two of the
notes turned out to matter more than they looked.

- **(1) `verify` could not confirm any run the harness ended**, and said "the
  states differ" while naming no difference. Reproduced exactly as reported: a
  run capped at 20 decisions verified `false` although all 20 states
  reproduced. `verify` now has a **scope**: `full` for a run the game ended
  (every state, the outcome, the cause, the turn and the trace must match) and
  `prefix` for one the harness ended (every recorded state must match, and the
  stream must run out where the recording stops). A replay that runs out of
  actions raises `StreamEnded`, which the run records as `agent_stopped` with
  the decision and turn, and `verify` reads it as the stream's end. A test
  verifies a capped run, and another alters one recorded action to prove the
  prefix rule still catches a real divergence (it names decision 2).
- **(2) The chooser's decisions and the stop reasons were in memory only.** A
  run with a chooser now writes `decisions.jsonl`: one line per choice (the
  primitive, the chooser's own reason, the stop it answered) and one per stop.
  `explain` reads it, its hash joins the record's evidence as
  `journal_sha256`, and the T05 gate asserts it.
- **(3) Provenance was sampled when a record was written**, so a run played on
  a dirty tree and committed before recording claimed the new commit. The
  commit, dirty state, compiler, platform and content hashes are now captured
  into `result.json` at play time (`build.provenance`), and the recorder uses
  them.
- **(4) The recorder invented settings and birth options** when the observer's
  lines were missing. It now refuses to write a record at all, and says to
  look at the trace.
- **The notes, acted on:** `explore_floor` distinguishes `unreachable` from
  `explored`; the stat strings are `cnv_stat`'s exactly (` 18/09`, `18/***`);
  `verify` checks the record's published `state_hashes_sha256` against the run;
  `WalkTo`'s unreachable `blocked` is marked as the defensive branch it is; and
  the three stale passages in docs/BRIDGE.md and docs/RECORDS.md are corrected.
- **The tests the review said would pass over a broken thing:** the T05 gate
  now asserts fighting, resting and the stop reasons; the seasonal days are
  read out of `mon-make.c` at the pin rather than copied; a **death is branched
  before it happens** (T08's own shape, and it needs no save because replay
  starts from birth); and a **live shop purchase of a label that is not the
  first** was added.

  That last test earned the whole exercise: buying label `c` bought a **Ration
  of Food when the agent asked for wine**. The observation listed the stock in
  `store->stock` order, while the store's menu uses `store_stock_list`'s
  order, so the labels pointed at the wrong items. The bridge now reads the
  stock exactly as `ui-store.c` does. Buying label `a` had worked by luck,
  which is why the first live check passed.

**Left where the reviewer suggested:** the `mind` block is still one model per
run (T06, when a run may call several); the secret guard does not scan the
observation and action logs, which only matters once a model's replies land
there (T06); the build subprocess still inherits the full environment; and the
`seasonal` flag is sampled at run start, so a run spanning midnight into 24
December is described by neither value — a footnote while runs last minutes,
and another argument for the owner's open question.

### T14. The heavy-run lock under an outer flock

Found by the milestone 2 reviewer, who ran the documented command

```sh
flock /tmp/angband-validation.lock .venv/bin/python -m pytest -q -m slow
```

and waited an hour and three quarters. The outer `flock` holds the lock; the
suite's own runs then open the same file and wait for a lock their own parent
holds. Nothing could ever release it.

`heavy_lock` now skips the lock when a process we are a child of already
holds it — the work is serialized by that ancestor, which is the point of the
lock — acquires without blocking so a wait can be reported and given up on
(ten minutes, naming the holder, pointing at `BORG_AGENT_NO_LOCK`), and
honours `BORG_AGENT_NO_LOCK` everywhere rather than only in tests. AGENTS.md
and docs/BUILD-AND-PLAY.md say so, and a test builds a small `/proc` to check
the ancestor case without a real deadlock.

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
