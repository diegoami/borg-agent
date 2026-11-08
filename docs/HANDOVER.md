# Handover

The newest entry is first. Each session adds one entry at the end of its
work and updates "Current state".

## Current state

- **Milestone 2 is complete and waiting for the owner's review.** Its review
  PR is `main` into `reviewed` ([#15](https://github.com/diegoami/borg-agent/pull/15)); the owner merges it, which advances
  `reviewed`. **A session does not start milestone 3 until then** (RULES 7).
- Milestone 2 delivered, all merged: **T03** the bridge (#8), **T13** the open
  sources, decision D8 (#9), **T04** records and replay (#11), **T05** the
  executor's primitives (#12), **T12** the milestone-1 review findings (#13).
- Milestone 1 (foundation) was reviewed at `11c8303`, issue
  [#7](https://github.com/diegoami/borg-agent/issues/7). All thirteen of its
  findings are now answered: eleven fixed, one (the mind block versus R2.4's
  three jobs) carried into T06, and one left to the owner — see below.
- **What works end to end today:** the pinned game builds; the stock Borg
  plays it reproducibly; an agent plays through the Borg's own connection with
  the eight primitives of R2; every run can be recorded, replayed with
  `verify`, branched at a turn, and read with `view`, `dump` and `explain`.
  No model has played yet: that is milestone 3.
- Open owner questions:
  - **the seasonal window** (review finding 1): neutralizing the game's one
    `time()` read would make replay independent of the calendar, at the price
    of play differing from the unpatched build on 24-26 December. That is a
    RULES 9 exception, so it is the owner's call. Today every run records
    `calendar.seasonal` and `verify` refuses to compare across the window;
  - which models do which job (T09 measures the `trial:` candidates, then
    decision D6);
  - whether the OpenRouter reviewer is `nvidia/nemotron-3-ultra-550b-a55b` or
    the `:free` variant — the owner will decide later;
  - whether `claim@1` should carry `superseded` as a status as well as the
    `superseded_by` field.
- Settled: `default_profile: alibaba` stays (the owner, 2026-11-08 — the
  general notes about that provider do not apply here, since D7 makes the
  profile the only model rule).

## 2026-11-08: T12, the milestone-1 review findings

Branch `task/T12-review-findings`, PR
[#13](https://github.com/diegoami/borg-agent/pull/13).

What changed: the calendar's `seasonal` flag and `verify`'s refusal to compare
across the window; the claim lifecycle in the schema plus
`src/borg_agent/checks.py` for the two rules that are comparisons; the
observation's true-state naming rule, checked on every observation the bridge
writes; runner parity (the recipe is now byte-identical to
`tools/measure-native.py` at the pin, with four tests that read it there); a
key guard over the whole run record; the build key covering the include line,
the CMake lines, the version suffix, the compiler and the platform;
`schemas/examples/README.md`; `scripts/refresh-examples.py`; and the weak or
missing tests the review listed.

Facts the next sessions will need:
- **`borg_agent.checks` is where a rule goes when it compares two fields.** A
  JSON Schema cannot say "the reviewer is of another family" or "`fields` names
  exactly these keys". T07 must run both checks when a claim enters the store;
  the agent already runs the observation one.
- **The stall clock starts when the action goes out**, not when the
  observation came in. The slow-mind test found the earlier version still
  spanned the mind's thinking, which would have killed real model runs.
- **The recipe is the runner's, byte for byte**, and tests parse the runner at
  its pin to prove it. If the runner pin moves, those tests fail first and
  tell you what changed.
- The build key now includes the **compiler and platform**, so a build
  directory is per machine and a record from another machine cannot be
  `verify`-ed locally. That is honest: the binary differs.
- `scripts/refresh-examples.py` regenerates the run-record examples from real
  runs. Never hand-edit them.

Left for the owner: the seasonal-window decision above.

## 2026-11-08: T05, the executor's primitives

Branch `task/T05-executor-primitives`, PR #TBD.

What exists now:
- `src/borg_agent/executor.py`: the eight primitives of R2 (`walk_to`,
  `explore_floor`, `fight_nearest`, `rest_until_healed`, `take_stairs`,
  `flee`, `read_unknown_scroll`, `shop_list`), breadth-first pathing over the
  player's known map, and `ExecutingMind`, which runs a primitive until it
  stops and then asks the chooser again with the stop reason.
- `mind.PrimitiveMind`: a chooser fixture; `--mind scripted-primitives`.
- The bridge gained the shop's stock in the observation and the `read`,
  `quaff`, `buy` and `sell` commands.
- `docs/EXECUTOR.md`, `tests/test_executor.py` (44 tests), and a live gate.

**The gates.** The same fixture played twice on seed 1 to 10,000 turns:
identical action streams (876 decisions, `01aeca55…`), and `verify`
reproduced the run with the same state hash at every observation. T01's gate
still gives `2242a3f5…`, so the bridge changes did not touch play.

Facts the next sessions will need:
- **The observation now carries the whole known map**, trimmed to its bounding
  box, not a 41×21 window. The window made exploration blind: the frontier was
  always the window's edge, so the agent re-walked corridors it already knew
  and never finished a floor. About 4 KB per observation after 10,000 turns.
  T06 will have to summarise it for a prompt rather than paste it.
- **A primitive holds no threshold.** `stop_if_hp_below` and `max_decisions`
  come from the mind, in the action. A test checks that a primitive keeps
  going at one hit point when nothing was asked for. Keep it that way: if the
  executor decided when to flee, T09 would be measuring the plumbing.
- **Two new ways a run can end**, both in the vocabulary already:
  `agent_stopped` when six primitives in a row stop without acting
  (`executor.CannotAct`), and `stalled` when the game answers 500 decisions
  without its turn advancing. The second one matters: a shop doorway burned
  31,681 decisions at one turn before it existed, and a turn cap cannot catch
  that because entering a shop costs no game time.
- **The shop path is live-verified**: the stock is read from `store->stock`
  with `ODESC_STORE`, exactly as `ui-store.c` describes it, and the labels come
  from the Borg's own `SHOP_MENU_ITEMS` table, which is what the store menu
  offers. Buying sends the label, `p`, then two returns — the Borg's own
  sequence. Checked in the General Store: 140 gold to 80, mushroom in the
  inventory.
- `stock_k` (the store's "known" stock) describes as `(nothing)`; use
  `store->stock` with `ODESC_STORE`.
- The fixture chooser waits out the cap on a floor whose stairs it never
  finds. It is a fixture, deliberately not a strategy.

Left for the owner:
- nothing new; **T12 is the last task of milestone 2**, and then the review PR.

## 2026-11-08: T04, run records and replay

Branch `task/T04-record-and-replay`, PR #TBD.

What exists now:
- `src/borg_agent/record.py`: builds a run record from a finished run and
  validates it. A record is immutable — `write_record` refuses to overwrite
  one (R4.1).
- `src/borg_agent/replay.py`: the `replay` mind, `verify`, `branch`, and the
  readers behind `view`, `dump` and `explain`.
- `python -m borg_agent record | verify | branch | view | dump | explain`.
- `docs/RECORDS.md`, `tests/test_record_and_replay.py`, and the run-record
  examples **generated from real runs** so they cannot drift from the
  recorder.

**The gates.** A 101-decision scripted run on seed 1 at cap 1,000: `verify`
replayed it with no mind and matched the state hash at **all 101
observations**, the decisions, the outcome, the cause, the final turn and the
trace hash. `branch` at turn 500 replayed 51 actions, handed over at turn 501
to a differently-headed mind, played on to the cap, and its record names
`parent: {run_id, turn}`.

Facts the next sessions will need:
- **The state hash leaves out `run_id` and nothing else.** That is what lets a
  replay in another directory match; it was the first thing that went wrong
  here (every hash differed at decision 0). Key order cannot change it.
  `record.state_hash` is the only place that decides what counts as state, so
  anything added to an observation becomes part of it automatically.
- **A branch hands over at the first observation at or after the turn asked
  for**, because turns advance in steps of ten; the record stores both the
  requested turn and `handed_over_at`.
- **`verify` needs the build the run used.** It looks for `build/<build_key>`
  and refuses if the recipe does not match, rather than verifying against a
  different binary.
- A replay that runs out of recorded actions raises and names the decision; it
  never invents one.
- `verify` does not apply to a stock-Borg run (T01): there is no action stream.
  That determinism is checked by replaying the seed.
- The run-record schema is now strict (review finding 3). If a field is
  missing from a record, the recorder is what has to learn it — the examples
  are generated from real runs, so regenerate them rather than hand-editing.

Left for the owner:
- nothing new; the milestone 2 review PR comes when T05 and T12 are merged.

## 2026-11-08: the milestone process

Not a plan task; the owner's process, written down.

- **RULES 1** now says a session merges its own task PRs once CI is green.
- **RULES 7** says reviews happen at milestones: PLAN.md's table says which
  tasks make up each one, a session stops when the last of them is merged,
  and the review PR is `main` into `reviewed`.
- The **`reviewed`** branch was created at `11c8303`, the commit milestone 1
  was reviewed at. Never commit to it; it moves only when the owner merges a
  review PR.
- PLAN.md gained the milestone table and a `Milestone` column in the status
  table; `tests/test_repository.py` checks that every task belongs to a
  milestone, that no task needs work from a later one, and that the process
  is written down.
- AGENTS.md's "Choosing the work" now says: work only inside the milestone in
  progress, merge your own PRs, and stop at the milestone's end.

## 2026-11-08: T13, the playing agent's sources are open (D8)

Branch `task/T13-open-sources`, PR [#9](https://github.com/diegoami/borg-agent/pull/9), stacked on #8. Documents, pins and
the claim schema.

The owner, on 2026-11-08: the rule in docs/SOURCES.md that phase 1 could read
only the manual **was not their intent**. The playing agent may read whatever
helps it build the knowledge base — the game source, the Borg source and its
documentation, the Borg specification, the open issues, the recorded deaths
and the zoo's results. The manual stays required, so the agent knows the keys
and the commands. The purpose of the repository is to play and to grow the
knowledge base the Borg reborn is built from. Recorded as **D8**, superseding
D2.

What changed:
- `docs/SOURCES.md` rewritten around what may be read and where it is pinned.
- The requirements: the phases now say what each phase *produces*, not what it
  may read; D2 is marked superseded; D8 is recorded; the claim basis list
  grew.
- `pins.json`: a new **`borg-spec`** pin (diegoami/neo-angband-tracker
  `eefc5500`, `docs/c-borg/BORG_SPEC.md`, 107 KB) and a **`sources`** block
  naming each source with the pin it is read at. `scripts/setup.sh` clones the
  new repository without any change — it reads `pins.json`.
- `claim@1`: `static:borg-spec`, `static:deaths` and `static:issue` beside the
  two static bases that existed, the matching `sources` values, the phase-1
  restriction gone, and a **new rule that a `static:` basis must name its
  reference**.
- The example that existed to be rejected for citing the Borg's source is now
  a valid claim with a `static:borg-source` basis; an example that omits the
  reference took its place.

Facts the next sessions will need:
- **The deaths are at our pin**: `docs/deaths/` at better-borg-c `b3c825c9`
  has nine cases with `index.json`, `README.md` and a review template;
  better-borg-c's `main` has sixteen. Read them at the pin and cite the
  commit, or cite `main` with the date.
- **The issues are the one unpinned source.** A claim that rests on an issue
  records its number and the date it was read, because a tracker moves.
- What survives of the old rule, and is unchanged: a model never promotes its
  own claim past `hypothesis` (R4.3); the executor's primitives stay
  mechanical, because hiding the Borg's tactics in the plumbing would hide the
  thing being measured; and T09's quiz answers never enter a prompt.
- T06's prompt-pack test changes shape: it checks **provenance, not
  permission** — every file a prompt draws on is named in `pins.json`'s
  `sources`, and the pack records which.

## 2026-11-08: T03, the bridge

Branch `task/T03-c-bridge`, PR [#8](https://github.com/diegoami/borg-agent/pull/8).

What exists now:
- `bridge/agent-bridge.c` and `.h`, this repository's own C, applied to the
  pinned tree on top of the observer. At the Borg's thinking line it writes
  one observation and waits for one action; with the agent mode off the branch
  falls through to `borg_think()`.
- `src/borg_agent/agent.py`: the Python end — the bounded handshake, schema
  validation both ways, the wire format, and the action stream with its
  SHA-256.
- `src/borg_agent/mind.py`: the `scripted` mind of R2.
- `python -m borg_agent agent` and `agent-determinism`.
- `docs/BRIDGE.md`, and `tests/test_agent.py`.

**The gates.** T03: seed 1 at cap 1,000 ended `turn_cap` at turn 1,000 after
101 decisions, and seed 7 died to "a rock lizard" at turn 311 after 32
decisions; both reproduced byte-identical action streams and traces on a
second run. T01's gate was rerun on the bridge build and still gives seed 7's
trace `2242a3f5…`, which is the evidence that the bridge changes no play
(RULES 9).

Facts the next sessions will need:
- **The Borg's own trackers are stale under the agent.** `borg_grids`,
  `borg_kills` and `borg_takes` are only refreshed inside `borg_think()`,
  which the agent replaces. R1 allows reusing them, but with the agent
  deciding they say floor where the game says wall — the first version of this
  bridge did exactly that and walked into walls for 20,000 decisions. The
  observation is built from `player->cave`, the game's visible monsters and
  the character sheet instead. T05 and T08 should not reach for the Borg's
  trackers either, unless they also call its update.
- **Nothing the bridge writes is true state**, so no observation carries a
  `true_state` block; `asleep` and `health` are null because the player cannot
  tell. A test asserts the bridge calls only four Borg functions
  (`borg_keypress`, `borg_keypresses`, `borg_note`, `borg_what_text`).
- **The handshake order is forced**: the agent opens the observation pipe for
  reading, the bridge opens it for writing and then opens the action pipe for
  reading, and the agent accepts that. Waiting for the first observation
  before accepting the action pipe deadlocks — that cost an hour.
- **Every path handed to the game must be absolute.** The game runs with the
  build tree as its cwd, so a relative `--output` made it quit before writing
  anything, which looked exactly like a seed-dependent hang.
- A stray run can hold `/tmp/angband-validation.lock` for ever if it blocks in
  a handshake; both waits are now bounded and the child is watched. If a run
  seems to hang, look for the lock's holder in `/proc/*/fd` first.
- The executor primitives are not translated yet (T05): `wire()` raises for a
  `primitive` action. Shops are not handled: `shop` is always null and the
  scripted mind escapes a store screen.

From the milestone review (issue #7), fixed here:
- the stall clock of an agent run restarts on every observation, so model
  latency cannot become an outcome (finding 2);
- the game gets an allowlisted environment, so none of the owner's keys
  reaches it or its log (finding 5);
- `budget_cap`, `decision_cap` and `agent_stopped` are outcomes, not failures
  (finding 11);
- the run timer starts inside the lock, and `lock_wait_seconds` is its own
  figure (finding 12);
- `action@1` no longer accepts direction 5 (finding 13);
- `build --output` refuses to delete a directory that is not a build
  (finding 10);
- every run records a `calendar` block, the slow test asserts T01's golden
  trace hash outside 24-26 December, and the docs say why that window matters
  (finding 1, partly) and correct the claim that the observer "only reads
  state" (finding 6, partly).

Left for the owner:
- the two decisions in "Current state" from review finding 8;
- milestone 2's review, when T04 and T05 are in.

## 2026-11-08: T02, the schemas

Branch `task/T02-schemas`, PR [#5](https://github.com/diegoami/borg-agent/pull/5), stacked on #4.

What exists now:
- `schemas/observation@1.json`, `action@1.json`, `run-record@1.json` and
  `claim@1.json`, draft 2020-12, each naming itself in a `schema` field.
- `schemas/examples/<name>/valid-*.json` and `invalid-*.json`: 41 examples,
  and an invalid example's file name says which rule it breaks.
- `tests/test_schemas.py`: every schema compiles, every valid example
  validates, every invalid one is rejected, and the rules a reader would want
  stated are asserted directly — the outcome vocabulary, the profile-only
  model rule, the true-state rule and the claim lifecycle.
- `docs/SCHEMAS.md` explains each schema and what it enforces.
- `jsonschema>=4.21` is now a test dependency (the first beyond pytest).

Facts the next sessions will need:
- **The observation's knowledge rule is in the shape of the schema**, not
  only in prose: a monster entry forbids unknown fields and has no `hp`, what
  the player cannot tell is null, and `true_state` is absent by default and
  must list the names of the fields it carries. T03 fills observations from
  the Borg's own state-reading code, so it has to keep true-state reads out
  of the ordinary fields, or name them there.
- **`action@1` rejects a payload of the wrong kind** rather than ignoring it,
  so a mind that answers `{"kind": "command", "primitive": ...}` fails
  loudly. T06's parse-failure counter should count exactly that.
- **The outcome vocabulary** is the zoo's nine classes plus `agent_stopped`
  (the zoo's `borg_stopped`) and `budget_cap`. A test pins the set, so a
  change has to be deliberate.
- **The claim schema cannot check the review rule** (R4.3): that the reviewer
  was of another family than the producer. `produced_by.family` and
  `reviews[].family` are there for T07 to check, and T07 should.
- The run record's `mind` block refuses unknown fields and has no key field,
  so a key cannot be recorded by accident; `endpoint_host` is a host, never a
  URL with credentials.
- Nothing writes or reads these files yet: the recorder is T04, the knowledge
  store T07. There is no Python model of the schemas on purpose — the schema
  files are the single definition, and code validates against them.

Left for the owner:
- a review by another model family for this PR;
- whether `claim@1`'s `status` set should carry `superseded` as well as the
  `superseded_by` field. R4 lists the statuses and `superseded-by`
  separately, which is what the schema does, so nothing is blocked either
  way.

## 2026-11-08: models by profile, in models.yaml (T06, documents)

Branch `task/T06-models-profiles`, PR [#4](https://github.com/diegoami/borg-agent/pull/4), stacked on #3. Documents and
configuration only; the loader is the rest of T06.

The owner's decision of 2026-11-08, recorded as **D7**: the agent's models
come from a profile in `models.yaml` at the root, and from nothing else. That
replaces the three `BORG_AGENT_*` variables and the planned
`providers.json`, and **this repository no longer uses the owner's local
recommendation service at all**, locally or in the cloud. AGENTS.md now
states the profile rule as the project's own model-choice rule, so the
owner's general rule doesn't apply here.

What exists now:
- `models.yaml`: four providers (alibaba, openrouter, zai, minimax), four
  profiles of the same names, and the model trial's candidates per job. No
  keys: each provider names the environment variable that holds its key.
- `models.local.yaml` is git-ignored; one line (`profile: openrouter`)
  switches profile on the owner's machine, and it may also override a single
  job.
- The requirements (R2.2, R2.4, D3 and the new D7), PLAN.md (T06's
  description, T09's candidates, the cloud column of T09 and T10) and
  AGENTS.md (a "Choosing models" section, and rewritten cloud and local
  sections) all follow the profile rule.

Facts the next sessions will need:
- **Base URLs were checked against each provider's own documentation** on
  2026-11-08 and cited in the file: Alibaba's Token Plan host
  (`token-plan.ap-southeast-1.maas.aliyuncs.com`, which the plan's key is
  bound to: a pay-as-you-go key gets 401 there, and the reverse), OpenRouter,
  Z.ai's **coding** endpoint (`/api/coding/paas/v4`; a coding-plan key fails
  on the general endpoint) and MiniMax's international host.
- **The model ids are not all verified.** The owner gave and checked the
  Alibaba and OpenRouter ids. The zai and minimax ids (`glm-5.3`,
  `glm-5.3-flash`, `MiniMax-M3`, `MiniMax-M2.7`) come from the owner's own
  provider table and were not checked against those providers' catalogues
  here. T06's loader can't check them either; the first real call will.
- **`context_k` is set only where there is a number to stand on** (the
  Alibaba profile, as the owner gave it). The other profiles leave it out,
  so the loader's default applies; T06 chooses that default and says so.
- The one-family plans (zai, minimax) take their **reviewer from OpenRouter**
  (`nvidia/nemotron-3-ultra-550b-a55b`), because a review must be of a
  different family from the consolidator (R4.3). Those two profiles
  therefore need `OPENROUTER_API_KEY` as well as their own key.
- Nothing reads `models.yaml` at run time yet, and `pyyaml` is not a
  dependency yet; T06 adds both with the loader. The repository test only
  checks the file's shape with a line-based reader and that it holds no
  key-looking field.

Left for the owner:
- a review by another model family for this PR;
- whether the four profiles are the ones wanted, and whether to pin the zai
  and minimax model ids after checking them.

## 2026-11-08: T01, the pinned game headless

Branch `task/T01-headless-play`, PR [#3](https://github.com/diegoami/borg-agent/pull/3).

What exists now:
- `python -m borg_agent build`: extracts the `better-borg-c` pin with
  `git archive`, instruments it exactly as the zoo's runner does
  (`tools/measure-native.py --observe` at the `runner` pin), and builds it
  with CMake. The instrumentation recipe is data in
  `src/borg_agent/build.py`, so tests check every site against the pinned
  sources without building, and the build key is a SHA-256 of the recipe
  (game commit, runner commit, sites, CMake arguments, observer file
  hashes). Builds live in `build/<key>`, and a finished build of the same
  recipe is reused.
- `python -m borg_agent play --seed N --cap T`: plays the **stock Borg**
  through the test frontend with the runner's birth input (Human Warrior),
  under `/tmp/angband-validation.lock`, and writes `trace.txt`,
  `terminal.log` and `result.json` to `runs/`.
- `python -m borg_agent determinism --seed N --cap T`: plays twice and
  compares trace bytes, writing `determinism.json`.
- `docs/BUILD-AND-PLAY.md`, and a CI job (`headless`, Ubuntu 24.04) that
  builds, runs the determinism check and the `slow` tests, caching `build/`
  by the recipe key.

Facts the next sessions will need:
- **T01's gate passed.** Seed 7, cap 5,000, Human Warrior: both runs ended
  `turn_cap` at turn 5000 with 53,040 bytes of identical trace, SHA-256
  `2242a3f55de1711fce9c37c5301c9ad3d4cdd9daf32cea8f44066b28a1d7d1f0`, about
  1.9 s each. So T03 may build on it.
- The observer's `trace.txt` holds game facts only (turn, energy, decision
  count, depth, level, HP, the full RNG state, character, options, and the
  Borg's own messages as `BORG <turn> <text>`); no wall time, paths or pids.
  That is why the bytes match, and it is what T04's state hashes can use.
- Checkpoint saves are off by default here (the runner writes one every
  1,000 turns by `fork` and save). T08 needs them on: `--checkpoint-saves`,
  which gives `start.save` and `recent.save` in the run directory.
- The runner's named-play mode (`BORG_MEASURE_PLAY_TURNS` with
  `measure_activate_borg`) is how the zoo resumes a save and plays on at a
  command boundary. T08's "stop k turns before the death" should use that
  path rather than a new one; `src/borg_agent/build.py` already adds the
  activation function the observer needs.
- `vendor/` clones are blobless (`--filter=blob:none`). `git archive` and
  `git show` fetch what they need, but `git grep` over a whole pinned commit
  fetches every blob and takes minutes: don't.

Environment, on the owner's machine:
- `bash scripts/setup.sh --strict` ends with `setup: ready`; the C compiler,
  CMake and `libx11-dev` were already there, and nothing had to be
  installed.
- There is no system `pip` and no system `pytest`; `uv` is present. Made
  `.venv` with `uv venv` and installed the package into it, and added that
  fallback to AGENTS.md. `.venv/` was already in `.gitignore`.
- `python -m pytest -q` now deselects the `slow` tests (the build-and-play
  gate). CI runs both.

Left for the owner:
- a review by another model family (RULES 13, AGENTS.md): T01's PR needs
  one.
- T09 (model trial) and T10 (pilot) still need model access, and the model
  choice per job is still open; see "Current state".

## 2026-11-08: repository initialized

Set up from the owner's local session, which also runs the Borg zoo.

What exists:
- the requirements, with the owner's five decisions accepted;
- the plan for milestone 1, rules, sources policy and pins;
- the setup script, a Python package skeleton, the repository tests and CI.

Facts the next sessions will need:
- **Pins** are in `pins.json`. The C game and Borg are better-borg-c
  milestone 6 (`b3c825c9`, tag `4.2.6-impact-v6`), the zoo's
  `4.2.6-bbc-m6`. The zoo builds and plays every C specimen with
  `tools/measure-native.py` at better-borg-c `fc9d97cb`; read it before T01.
  It extracts the tree with `git archive`, instruments it by text
  replacement (`native-observer.c`, hooks in `main-test.c`, `game-world.c`,
  `ui-game.c`, `borg/borg.c` and `borg/borg-io.c`), builds with CMake and
  plays through the test frontend, whose input is a script of `key` lines.
- **Turns.** The zoo's caps count the C game's `turn`. At normal speed one
  player turn is 10 game turns, so a 100,000-turn cap is about 10,000 player
  turns.
- **The Borg's connection** (R1): it acts through `inkey_hack` (set in
  `src/borg/borg.c`), and reads the player's map knowledge in
  `borg-update.c`, the screen and messages in `borg-io.c` and
  `borg-messages.c`, and the character in `borg-trait.c`.
- **First post-mortem cases** (T08): the zoo's `classes-m6` run (results
  branch of diegoami/borg-zoo, `results/classes-m6/42489102169-1/cells.jsonl`)
  has `4.2.6-bbc-m6` dying to "a floating eye" on seed 1865911738
  (Half-Troll Mage) and seed 1375157069 (Dunadan Priest). The same lead came
  from Mandos on the Neo engine: floating eyes killed 4 of 13 characters in
  the zoo's `mandos-classes-18`.
- **Class matters most** early on: on the zoo's `classes-1800` suite the
  original Borg loses about 70% of Druids and about 19% of Paladins by turn
  100,000. The owner wants strategy by class in the remake.

Left for the owner:
- T09 (model trial) and T10 (pilot) need model access. (Superseded on
  2026-11-08 by decision D7: a profile in `models.yaml`, with its providers'
  key variables set in the environment. This entry originally named three
  `BORG_AGENT_*` variables.) The owner picks the models per job after T09.
- Reviews by a different model family are arranged by the owner.
