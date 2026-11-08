# The bridge: the Borg's hands and eyes, given to an agent

From T03. The bridge is a patch on the pinned game tree, applied on top of
the zoo's observer (see [building and playing](BUILD-AND-PLAY.md)). It adds a
connection and nothing else.

```sh
python -m borg_agent agent --seed 7 --cap 1000                # one game
python -m borg_agent agent-determinism --seed 1 --cap 1000     # T03's gate
```

## Where it attaches

The Borg supplies keypresses through the game's `inkey_hack` hook. Inside
that hook, `generate_keypress` in `src/borg/borg.c` does the game's
housekeeping — messages, `-more-`, the key queue, deactivation and death —
and then thinks:

```c
    /* Think */
    while (!borg_think())
        ;
```

The observer wraps that line, and the bridge wraps it once more:

```c
    while (!(measure_decision(), agent_active() ? (agent_think(), true) : borg_think()))
```

So the agent replaces **only the Borg's thinking**. Everything the Borg does
around thinking still happens, and the keys the agent's actions become go into
the Borg's own key queue (`borg_keypress`), so the game sees nothing new.

`agent_active()` is true only when `BORG_AGENT_OBS` and `BORG_AGENT_ACT` name
the two pipes. With them unset the branch falls through to `borg_think()`:
**play is then byte-identical to the stock Borg's** (RULES 8). That is checked
by rerunning T01's gate on the bridge build; it still gives seed 7's trace
`2242a3f5…`.

## The protocol

One decision is one observation out and one action in. The game waits for the
answer, so no game time passes while the mind thinks and wall time never
affects play (R1.3).

- **Out:** one line of JSON per decision, valid against
  [`observation@1`](../schemas/observation@1.json), on the `BORG_AGENT_OBS`
  pipe.
- **In:** one line per decision on `BORG_AGENT_ACT`, in the bridge's own
  compact form: `command walk dir=6`, `command go_down`, `keys %1b`. Values
  are percent-escaped, so a line never breaks on a space.

`src/borg_agent/agent.py` owns the Python end: it validates both directions
against the schemas, turns an [`action@1`](../schemas/action@1.json) action
into that line, and writes the action stream to `actions.jsonl` with its
SHA-256, so a run can be replayed without the mind (T04).

The handshake is ordered by what a FIFO does: the agent opens the observation
pipe for reading, the bridge opens it for writing and then opens the action
pipe for reading, and the agent accepts that. Both waits are bounded and the
game is watched while they last — a game that dies before the bridge opens its
end must not leave a run blocked on a pipe that will never have a writer,
holding `/tmp/angband-validation.lock`.

### What an action becomes

The table lives in the bridge, in `apply_action`. The keys are the ones the
Borg itself sends for the same command.

| Action | Keys |
|---|---|
| `walk` with a direction | `;` then the direction |
| `alter` with a direction (attack, open, tunnel) | `+` then the direction |
| `stay` | `,` |
| `pickup` | `g` |
| `rest` (`mode` `full`, `as_needed` or `turns` with a `count`) | `R`, then `*`, `&` or the count, then Enter |
| `go_down`, `go_up` | `>`, `<` |
| `answer` with text | the text itself |
| `escape` | Escape |
| `keys` (the escape hatch of R1.2) | the keys, logged as raw |

Anything else is refused on the Python side before a key is sent, and the
bridge refuses it again. The executor primitives of R2 (`walk_to`,
`explore_floor`, …) are **not** translated yet: they are T05, and `wire()`
raises for them.

## What the observation holds, and what it does not

Everything comes from what the player could know:

| Part | Source |
|---|---|
| map | `player->cave`, the player's own remembered grid, drawn with the game's glyphs; a square never seen is blank. A window of 41×21 around the player, with its `origin` |
| monsters | the monsters the player can see (`monster_is_visible`), with the glyph the player sees and the name the game would give. `asleep` and `health` are null: the player cannot tell |
| objects | the objects the player remembers on the floor, described as the game describes them |
| character | the character sheet: level, hit points, depth, gold, armour, speed, stats as printed, and the status line's conditions |
| messages | the game's message log since the last observation, in reading order |
| prompt, screen | the screen as the player sees it, through the Borg's own `borg_what_text` |

No field is read from a monster's or a grid's hidden state, so **no
observation the bridge writes carries a `true_state` block** (R1.1). The
schema's `true_state` exists for probes (mode C), which may be told more and
must then name every such field.

The Borg's own trackers (`borg_grids`, `borg_kills`, `borg_takes`) are
deliberately **not** used, although R1 allows it: they are only refreshed
inside `borg_think()`, which the agent replaces, so with the agent deciding
they are stale. That was the first thing this bridge got wrong — the map said
floor where the game said wall.

The bridge calls four of the Borg's functions and no others:
`borg_keypress`, `borg_keypresses`, `borg_note` and `borg_what_text` — the key
queue, the log and the screen. A test asserts that, because it is what keeps
the Borg's tactics out of the connector (docs/SOURCES.md).

## The scripted mind

`src/borg_agent/mind.py` holds the `scripted` mind of R2, which exists for
tests. It walks where the known map says it can, keeps its heading so it
crosses a room, opens a door rather than walking into it, avoids a square a
monster stands on, takes a down staircase it is standing on, answers a prompt
before anything else, and stays put when it knows nowhere to go. It has no
tactics, no thresholds and no valuations; the model-backed mind is T06.

## Determinism

T03's gate: the same mind, the same seed, the same recorded actions and the
same outcome. Checked on 2026-11-08, on the owner's machine:

| Seed | Cap | Outcome | Decisions | Action stream |
|---|---|---|---|---|
| 1 | 1,000 | `turn_cap` at turn 1,000 | 101 | identical, both runs |
| 7 | 1,000 | `death`, "a rock lizard", turn 311 | 32 | identical, both runs |

The traces are identical too. `agent-determinism` writes that verdict as
`determinism.json`, with the first differing action when there is one.

A run's stall clock restarts on **every observation**, not when the game's
turn moves: with a model mind the game is waiting while the model thinks, and
latency must never become an outcome (R1.3). The real limit on a model run is
its budget (R2.3), whose outcome is `budget_cap` — an outcome, not a failure.

## What is not here yet

- the executor primitives (T05) and the model-backed mind (T06);
- shops: `shop` is always null and the scripted mind escapes a store screen,
  so nothing buys anything yet;
- the run record of R5 and replay (T04). `result.json` holds the action
  stream's hash, the calendar, the build key and the outcome, which is what
  T04 will build on.
