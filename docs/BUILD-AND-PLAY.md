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

The sites are the runner's, with one indentation-only difference in
`ui-game.c`, so this build stays comparable with the zoo's specimens.

The observer takes no game action and makes no Borg decision, which is what
RULES 9 asks. It is not inert, though, and the earlier claim here that it
"only reads state" was wrong: it seeds the RNG from `BORG_MEASURE_SEED` (which
is what makes a seed control the game at all), writes the map at the end,
calls `quit()` at the cap, and with `--checkpoint-saves` forks and saves. None
of that changes a rule of the game or a choice of the Borg, and none of it is
byte-identical to an unpatched build.

**Nothing of the game is committed here**: the tree and the observer are read
from the pinned clones, and everything written lands under `build/` and
`runs/`, which git ignores. The bridge of T03
([docs/BRIDGE.md](BRIDGE.md)) is applied on top, from `bridge/` in this
repository; with the agent mode off it changes nothing.

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
then the Borg's own `C-z`), which gives a Human Warrior.

Heavy runs take `/tmp/angband-validation.lock` with `flock`, as the owner's
other Angband work does. Each run takes it itself, and an **outer `flock` on
the same file is detected**: if a process we are a child of already holds the
lock, the run does not try to take it again — it cannot succeed, because the
holder is waiting for us. `flock /tmp/angband-validation.lock pytest -m slow`
therefore works, which it did not before: it deadlocked, and a reviewer lost
an afternoon to it. `--no-lock` or `BORG_AGENT_NO_LOCK=1` skips the lock,
`BORG_AGENT_LOCK` points it elsewhere, and a wait longer than ten minutes
gives up naming the holder instead of hanging.

A run directory holds `input.txt`, `trace.txt`, `terminal.log` and
`result.json` (seed, cap, birth, build key, binary hash, outcome, cause,
states, trace hash, wall time). The run record of R5, with the action stream
and replay, is T04; this is only what T01 needs.

Outcomes come from the runner: `death`, `completion`, `turn_cap`, `saved`,
`stalled`, `wall_timeout`, `crash`, `harness_failure`, and from the agent
`budget_cap`, `decision_cap` and `agent_stopped`. A death, a cap and a budget
are outcomes; only the harness's own troubles are failures (R2.3).

The game is given an environment built from an allowlist, not this session's,
so none of the owner's model keys reaches a process that never calls a model
(RULES 16).

Two limits guard a run: a wall limit, and a stall limit measured from the last
sign of progress. For the stock Borg that sign is the trace's turn; for an
agent run it is the arrival of an observation, because the game waits while
the mind thinks (R1.3).

## Choosing the birth (T24)

Every run is born the zoo cohort's **Human Warrior** unless it says otherwise.
`play.birth_input(race, class_)` writes the key script for another character,
and `play`, `play_with_mind`, `branch`, `verify`, a post-mortem and a probe all
take `race` and `class_`; with neither, the script is the runner's own, byte for
byte, which is what keeps our games the zoo's games.

Two facts worth knowing before touching it:

- **The birth menus select on a double tap.** Pressing an item's letter moves
  the cursor to it; pressing it again selects it. Only the first item's letter
  selects at once. A single `key b` in the class menu therefore births a
  **Warrior** while looking like it asked for a Mage, which is exactly what the
  harness did before T24. This is the zoo's own rule (`zoo/harness.py`).
- **The tags skip h, j, k and l**, because those are the roguelike movement
  keys: the game's `all_letters_nohjkl` is `abcdefgimnop…`. So Half-Troll, the
  eighth race, is tagged `i`. Both the tags and the race and class order are
  read from the game at the pin (`src/ui-menu.c`, `lib/gamedata/p_race.txt`,
  `lib/gamedata/class.txt`), never written down here, because getting one wrong
  silently births someone else.

A run that chose its birth records `game.birth.rule` as **`assigned`** rather
than `fixed`, with the race and class the observer saw, and `result.json` keeps
the choice so a replay is born the same character.

## Determinism

`trace.txt` holds game facts only — turn, energy, decision count, depth,
level, HP, the RNG state, the character, the options and the Borg's messages
— and no wall time, paths or process ids. So two runs of one seed and cap
must give byte-identical traces.

Checked on 2026-11-09 at the **milestone 8** pin, seed 7, cap 5000, Human
Warrior, on the owner's machine (WSL2, gcc 15, Python 3.14): both runs ended
`turn_cap` at turn 5000, 542,917 bytes of trace, SHA-256
`a6ffbae042dddaabfd8d48a9b6d3546d935c422249062fe633f10688ee4ce844`, about 15
seconds each. The slow test asserts that hash.

**The hash belongs to the pin as much as to the seed.** At milestone 6 the
same seed and cap gave `2242a3f5…`, 53,040 bytes, in 1.9 seconds. Milestone 8
carries 25 more fixes, writes about ten times as much to the trace and thinks
about eight times as long per turn; it also survives seed 7 to 100,000 turns,
where milestone 6 died to a green naga at 27,808.

**That hash is not a property of the seed alone.** The game admits seasonal
monsters on 24-26 December (`get_mon_num` reads the clock), so the same seed
plays a different game on those days: the first town monster changes, and
everything after it. A run record therefore carries a `calendar` block, the
slow test skips the hash assertion inside that window, and a replay that must
match a recorded run has to run on the same calendar day until the build
neutralizes that one clock read. This was found by the milestone-1 review and
is on the plan as T12. `python -m borg_agent determinism` writes that verdict as
`determinism.json`, and prints the first differing line when there is one.
The same check runs in CI (`headless` job, Ubuntu 24.04).

Checkpoint saves are off by default here. The runner writes them every 1,000
turns by `fork` and save; `--checkpoint-saves` turns them on for a run that
needs a save to continue from (T08 will).
