# Building the pinned game and playing it headless

From T01. The commands below need a C compiler, CMake and `libx11-dev`
(`scripts/setup.sh` says what is missing, and installs it in a cloud
session).

```sh
bash scripts/setup.sh --strict        # pinned clones into vendor/, tools check
pip install -e '.[test]'
python -m borg_agent build            # the instrumented game, cached
python -m borg_agent play --seed 7 --cap 5000
python -m borg_agent determinism --seed 7 --cap 5000
```

Caps count the C game's `turn`: at normal speed one player turn is 10 game
turns, so `--cap 5000` is about 500 player turns.

On a machine without `pip` (no system pip, as on the owner's WSL), make a
virtual environment first: `uv venv .venv && uv pip install -e '.[test]'
--python .venv/bin/python`, then use `.venv/bin/python`.

## What the build is

`src/borg_agent/build.py` follows the zoo's runner
(`tools/measure-native.py --observe` at the `runner` pin, see
[pins.json](../pins.json)):

1. `git archive` the `better-borg-c` pin out of `vendor/better-borg-c` into
   `build/<recipe hash>/source`;
2. copy the runner pin's `tools/native-observer.{c,h}` into `src/`, add its
   include to the five files that call it, and apply the runner's six text
   replacements, each of which must match exactly once;
3. add `measure_activate_borg` to `borg-commands.c` (the observer calls it)
   and the observer source and `PRIVATE_USER_PATH` to `CMakeLists.txt`;
4. configure and build with `-DSUPPORT_BORG=ON -DSUPPORT_TEST_FRONTEND=ON
   -DSUPPORT_X11_FRONTEND=ON -DCMAKE_BUILD_TYPE=Debug`.

The sites are the runner's, unchanged, so this build stays comparable with
the zoo's specimens. The observer only reads state and writes `trace.txt`; it
takes no action and draws no RNG, so RULES 8 holds. **Nothing of the game is
committed here**: the tree and the observer are read from the pinned clones,
and everything written lands under `build/` and `runs/`, which git ignores.

### The cache

The build key is a SHA-256 of the recipe: the game commit, the runner commit,
every instrumentation site, the CMake arguments and the hashes of the two
observer files. It is the directory name under `build/`, and a finished build
of the same recipe is reused (`--force` rebuilds). A moved instrumentation
site is an error, never a silent skip.

## What a run is

`python -m borg_agent play` plays the **stock Borg** — nothing in this
repository decides anything yet — through the test frontend, with the
runner's birth input (splash, first race, first class, default point buy,
then the Borg's own `C-z`), which gives a Human Warrior. Heavy runs take
`/tmp/angband-validation.lock` with `flock`, as the owner's other Angband
work does (`--no-lock` skips it).

A run directory holds `input.txt`, `trace.txt`, `terminal.log` and
`result.json` (seed, cap, birth, build key, binary hash, outcome, cause,
states, trace hash, wall time). The run record of R5, with the action stream
and replay, is T04; this is only what T01 needs.

Outcomes come from the runner: `death`, `completion`, `turn_cap`, `saved`,
`stalled`, `wall_timeout`, `crash`, `harness_failure`.

## Determinism

`trace.txt` holds game facts only — turn, energy, decision count, depth,
level, HP, the RNG state, the character, the options and the Borg's messages
— and no wall time, paths or process ids. So two runs of one seed and cap
must give byte-identical traces.

Checked on 2026-11-08, seed 7, cap 5000, Human Warrior, on the owner's
machine (WSL2, gcc 13, Python 3.14): both runs ended `turn_cap` at turn 5000,
53,040 bytes of trace, SHA-256
`2242a3f55de1711fce9c37c5301c9ad3d4cdd9daf32cea8f44066b28a1d7d1f0`, about 1.9
seconds each. `python -m borg_agent determinism` writes that verdict as
`determinism.json`, and prints the first differing line when there is one.
The same check runs in CI (`headless` job, Ubuntu 24.04).

Checkpoint saves are off by default here. The runner writes them every 1,000
turns by `fork` and save; `--checkpoint-saves` turns them on for a run that
needs a save to continue from (T08 will).
