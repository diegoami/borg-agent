# Handover

The newest entry is first. Each session adds one entry at the end of its
work and updates "Current state".

## Current state

- **T01** is in review ([#3](https://github.com/diegoami/borg-agent/pull/3), branch `task/T01-headless-play`): the pinned
  game builds headless and the stock Borg plays it reproducibly.
- **T06's documents** are in review ([#4](https://github.com/diegoami/borg-agent/pull/4), branch
  `task/T06-models-profiles`, stacked on #3): the agent's models come from a
  profile in `models.yaml`, decision D7. T06's loader is still to write, and
  needs T02 and T05 first.
- **T02** is in review ([#5](https://github.com/diegoami/borg-agent/pull/5), branch `task/T02-schemas`, stacked on #4):
  the four schemas and their examples.
- **The stack is at three unmerged PRs** (#3, #4 and #5), so this session
  stopped there (RULES 5). The next tasks are **T07** (knowledge store),
  which needs nothing, and **T03** (the bridge), which needs T01 and T02.
- Open owner questions: which models do which job. The models are not fixed
  in advance; T09 measures the candidates from `trial:` in `models.yaml` on
  this project's own inputs and outputs, and the owner then records the
  choice as decision D6.

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
- a review by another model family (RULES 12, AGENTS.md): T01's PR needs
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
