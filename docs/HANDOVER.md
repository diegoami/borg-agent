# Handover

The newest entry is first. Each session adds one entry at the end of its
work and updates "Current state".

## Current state

- **T01** is in review (PR #TBD, branch `task/T01-headless-play`): the pinned
  game builds headless and the stock Borg plays it reproducibly. The next
  tasks are **T02** (schemas) and **T07** (knowledge store), which need
  nothing, and then **T03** (the bridge), which needs T01 and T02.
- Open owner questions: which models do which job. The owner's note of
  2026-11-08: the models are not fixed in advance; T09 measures the
  candidates on this task's own inputs and outputs first, and the owner then
  records the choice as decision D6. So T06 keeps the model configurable per
  run and nothing earlier than T09 assumes a model.

## 2026-11-08: T01, the pinned game headless

Branch `task/T01-headless-play`, PR #TBD.

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
- T09 (model trial) and T10 (pilot) need model access: the owner's
  machine, or a cloud environment with `BORG_AGENT_BASE_URL`,
  `BORG_AGENT_API_KEY` and `BORG_AGENT_MODEL` set. The owner picks the
  models per job after T09.
- Reviews by a different model family are arranged by the owner.
