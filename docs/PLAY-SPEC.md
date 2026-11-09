# How the agent plays: the specification

Written after the first design hit its ceiling (T31, 2026-11-09). It replaces
the vocabulary of R2's "eight primitives" and the prompt built on them, and it
absorbs decision **D12** (ask by state, not by event). Nothing below is
implemented yet: this is what to implement.

## Why the first design failed

Three faults, two of them the owner's observations and one worse than reported.

1. **The model was never told the game existed.** The system prompt listed ten
   primitives with their arguments and then said "or, when you want a single
   game command: `{kind: command, command: {name: "<command>"}}`" — without
   naming one. The game has **112 commands**; the bridge can type **29**; the
   prompt advertised **ten primitives and no commands at all**. `quaff` has
   worked since T05. No model has ever known the word, which is why a Mage
   stood next to a rock lizard at 10 hit points with potions it could not name.
2. **`flee` was a tactic in the plumbing.** Choosing between a staircase and a
   Phase Door scroll is exactly the judgement this repository exists to
   measure, and it sat in `executor.py`. Worse, it routed with a breadth-first
   search over remembered glyphs — no danger, no traps, no door logic — while
   **the game has its own router** (`find_path()` behind `CMD_PATHFIND`) that
   we never used.
3. **"Primitive" meant two things at once**: batching repetition, which is what
   makes a 100,000-turn game affordable, and making choices, which is what
   hides the thing being observed. Only the first belongs to the executor.

## What the agent decides, and in what words

The mind answers with **one action**. Actions come in two kinds, and the
difference is the whole design: a **move** is one thing the game does, a
**batch** is one thing repeated until something changes.

### Directions are compass words

Everywhere — in the observation and in the action — a direction is one of
`n ne e se s sw w nw`. The bridge maps them to the keypad digits the game
wants (`sw`→1, `s`→2, `se`→3, `w`→4, `e`→6, `nw`→7, `n`→8, `ne`→9). The model
never does coordinate arithmetic and never meets a y-axis that grows downwards.

This is the owner's correction, and it is the one that matters most: the old
observation said *"`R` rock lizard at (47, 7), 1 away"* and the old action said
`flee`. The new observation says *"`R` rock lizard, 1 sw"* and the new action
says `go ne` — or `attack sw`.

### Moves: one act of the game

| Action | Arguments | The game's own |
|---|---|---|
| `go` | `dir` | one step |
| `go_to` | `x`, `y` | **the game's pathfinder** (`CMD_PATHFIND`): it routes, walks and stops when disturbed |
| `attack` | `dir` | melee, or whatever altering that square means |
| `stay` | — | stand still |
| `rest` | `until`: `full`, `as_needed`, or `turns` + `count` | the game's rest |
| `down`, `up` | — | the staircase underfoot |
| `pick_up` | — | |
| `quaff`, `read`, `eat`, `use`, `activate`, `wield`, `take_off`, `drop` | `item` (a letter the observation gave) | |
| `aim`, `zap`, `throw` | `item`, and `dir` or `at: {x, y}` or `at: nearest` | |
| `cast` | `book`, `spell`, and optionally the same target | |
| `study` | `book`, and `spell` for a class that chooses | |
| `tunnel`, `disarm`, `open`, `close` | `dir` | |
| `buy`, `sell` | `item`, `count` | in a store |
| `answer` | `text` | a waiting prompt |
| `escape` | — | cancel a prompt |
| `keys` | `keys` | the escape hatch of R1.2, logged as raw |

**The list is generated into the prompt from the table the bridge reads**, the
way the primitives' help is generated from the executor's code today. A command
the bridge cannot type cannot be advertised, and one it can type cannot be
hidden. That is the fix for fault 1, and it is mechanical rather than a list
somebody maintains.

### Batches: the only thing the executor adds

| Batch | Arguments | Stops when |
|---|---|---|
| `explore` | — | the nearest square bordering the unknown is reached, or nothing is left (`explored`), or nothing known reaches one (`unreachable`) |
| `repeat` | `action` (any move above), `until` | the condition holds, or the action is refused |

`until` is one of: `target_gone`, `healed`, `hp_below N`, `sp_below N`,
`decisions N`, `level_changed`, `message <text>`, `nothing_new`. Every batch
also stops for the reasons in "When the model is asked" below — a waiting
prompt, a new monster, a level change — because those are changes, not
judgements.

**`repeat` replaces four of the old primitives and deletes a fifth.**

| Old primitive | Now |
|---|---|
| `fight_nearest` | `repeat {attack sw} until target_gone` — *the mind picks the direction and the limit* |
| `cast_at_nearest` | `repeat {cast a a at nearest} until target_gone` |
| `rest_until_healed` | `rest until full`, or `repeat {rest as_needed} until healed` |
| `read_unknown_scroll` | `read <the letter the mind chose>` |
| `shop_list` | `repeat {buy c} until decisions 3`, or several `buy` actions |
| **`flee`** | **deleted.** The mind says `go_to` the stairs, or `read` the Phase Door scroll, or `go ne`. The choice was always the interesting part |

What the executor may **not** do, restated because this is where it went wrong:
choose a target, choose an escape, estimate danger, hold a threshold, or route
a path. It batches and it reports why it stopped.

## What the model is shown

The observation already carries everything (R1). The prompt presents it, and
these are its parts. Everything a model is asked to name — a letter, a
direction, a spell — appears in the prompt **in the form the action takes**.

| Part | Form | Why it changed |
|---|---|---|
| who you are | race, class, level, **hit points and mana**, depth in feet, gold, armour, speed, hunger, and every condition the status line shows | mana was missing, so a caster could not see its own resource |
| where things are | each monster, object, staircase, door and shop entrance as `` `R` rock lizard, 1 sw `` — glyph, name, distance, **direction** — and `go_to` coordinates only for the squares a route can be asked for | the old prompt gave absolute coordinates and left the arithmetic to the model |
| the map | a window around the player, with a line saying how much more is known and in which directions the known map extends | unchanged in shape; the note is new |
| what you carry | inventory and equipment with their letters | equipment was missing |
| what you can cast | the spell table: book letter, spell letter, name, mana, failure chance, and whether the game would allow it now | added by T29 and never put in the prompt |
| the shop | its stock with letters and prices, while in one | unchanged |
| what just happened | the messages since the last decision | unchanged |
| the waiting prompt | its text, when one waits | unchanged |
| why you are being asked | **the state** (below), and the stop that produced it | the old prompt gave only the stop |
| what you have learned | the claims whose scope fits, in the states where they could matter | T23 wired the filter; the states decide where it is worth the tokens |

## When the model is asked

By **state**, not by event (D12). The agent computes its state from the
observation; the state chooses the prompt template, the actions offered and
whether knowledge is carried.

| State | When | May answer | Carries knowledge |
|---|---|---|---|
| `prompt` | the game is waiting on a prompt or menu | `answer`, `escape`, `keys` | no |
| `panic` | the pack's panic condition: hit points below its fraction, or afraid, confused, blind or poisoned | any move, `repeat` | yes |
| `fighting` | a monster is visible within the pack's fighting distance | any move, `repeat` | yes |
| `shopping` | in a store | `buy`, `sell`, `escape` | yes |
| `town` | depth 0, not in a store | moves, `explore`, `go_to` | yes — **which shop to visit** is a decision, and claims about shops belong here |
| `at_stairs` | standing on a staircase, nothing urgent | `down`, `up`, `rest`, `explore` | yes — **readiness**: is this character ready to go deeper (R4's readiness area) |
| `exploring` | anything else | moves, `explore`, `repeat`, `go_to` | no, unless a claim's scope names the depth |

**The thresholds that define a state are data in the versioned prompt pack**,
not code: what counted as "panic" in any run is then recoverable from the
pack's hash (RULES 12, D12). The executor reads them; it does not own them.

The Borg's own `borg-think-dungeon.c` is organised this way. Its structure is
worth copying; its numbers are what this repository exists to measure.

## The prompt

Two messages, as now. The system message is per **state**; the decision message
is the observation. Both are templates in the pack, hashed with it, and the
parts generated from code (the action list, the state's own rules) are in the
hash too — T29's lesson, where a changed primitive list silently changed every
prompt.

### The system message, for the `fighting` state

> You are playing Angband, one decision at a time. A scripted executor turns
> your answer into keys; it never decides anything.
>
> **You are in a fight.** A monster is next to you or close. Answer with one
> action: hit it, shoot it, cast at it, back away, drink something, or leave.
>
> Answer with one JSON object and nothing else:
>
> ```json
> {"schema": "borg-agent/action@1", "reason": "one line, your own words",
>  "action": {"name": "<one of the actions below>", ...arguments}}
> ```
>
> Directions are compass words: `n ne e se s sw w nw`. Where a target is
> wanted, give `dir`, or `at: {x, y}`, or `at: nearest`.
>
> *(the action table, generated)*
>
> To do one thing many times, wrap it:
>
> ```json
> {"action": {"name": "repeat", "action": {"name": "attack", "dir": "sw"},
>             "until": {"target_gone": true}}}
> ```
>
> The executor stops a repeat as soon as anything changes — a new monster, a
> prompt, a level change — and tells you which. It holds no limits of its own:
> if you want one, say it (`hp_below`, `decisions`).
>
> `reason` is one line and is recorded with the call. Add
> `"note": "..."` when the decision taught you something worth writing down.

The other states differ only in the paragraph that says where you are and what
is worth considering, and in which actions the table lists. One template per
state, one generated action table, nothing hand-maintained.

### The decision message

> Turn 571, decision 60. The last batch stopped: **new_monster**.
>
> Human Mage, level 1, **10/10 hit points, 2/2 mana**, depth 1 (50 feet),
> 512 gold, armour 2, speed normal, fed.
>
> In sight:
> - `R` rock lizard, 1 sw
> - `>` down staircase, 2 s — `go_to {x: 59, y: 55}`
>
> Carrying: `a` a Book of Magic Spells, `b` 2 Rations of Food, `c` a Scroll of
> Word of Recall, `d` 2 Wooden Torches
>
> Wearing: nothing
>
> You can cast: `a` `a` Magic Missile — 1 mana, 16% fail, **yes**;
> `a` `c` Find Traps, Doors & Stairs — 1 mana, 14% fail, yes
>
> The map you know (a 41×21 window; the known map runs 30 squares further
> west):
>
> ```
>   #.#
>   #.R
>   #@#
>   #>#
> ```
>
> Since your last decision: "The rock lizard bites you."
>
> What you have learned that applies here:
> - a floating eye paralyses a character that melees it (quantified, 4 of 10)
>
> Choose one action.

## What is recorded

Per call, as now and plus: the **state**, the prompt as sent (T30), the
model's thinking (T27), the reply, the action, the tokens, the seconds. Per
decision: the state, the action, the batch it belongs to, and the stop that
ended it. A claim can then say *"in the `panic` state, with these claims in the
prompt, this model chose to explore"*, which is the sentence T09 needs to score
a model and a post-mortem needs to explain itself.

## What this costs

Today's run: 5–11 model calls per 1,000 game turns. Under this spec a fight
costs a call per exchange unless the mind wraps it in `repeat`, and exploring
still costs one call per batch. The estimate is **15–40 calls per 1,000
turns** — three to four times today's, which at the measured 2,000 prompt
tokens a call is still of the order of a hundred thousand tokens for a
1,000-turn game.

**It is measurable, and it must be measured** rather than argued: one seed, one
model, the old surface against the new, compared on calls, tokens, depth,
character level, survival and **how many distinct actions the model used at
all**. If the new surface does not move those numbers, the ceiling was not the
vocabulary and this spec was wrong.

## What stays as it is

The bridge's connection (R1), the observation schema, the records and replay
(R5), the probes (mode C), the claim lifecycle (R4), the knowledge store, the
report (T30), and the zoo contract (R6). None of them depends on the
vocabulary. A model's game still replays byte-identically from its action
stream, which is what makes any of this evidence.

## The open questions for the owner

1. **Does `explore` stay?** It is the one batch whose *choice* is not the
   mind's: it walks toward the nearest unknown square. Without it, exploring
   costs a model call per step, which is most of the bill. Recommendation:
   **keep it**, with its frontier rule written here so a claim can cite it.
2. **Coordinates at all?** `go_to {x, y}` needs them, and the observation names
   coordinates only for squares a route can be asked for (stairs, doors, shop
   entrances, the frontier). Everything else is directions. Recommendation:
   **as described**.
3. **The state list**: `prompt`, `panic`, `fighting`, `shopping`, `town`,
   `at_stairs`, `exploring`. Anything missing — `recovering`? `stuck`?
4. **Does the agent keep a notebook between decisions?** R2's third layer
   (notes) exists in the action's `note` field and nothing else. A running
   "what I am trying to do" would cost tokens and might steady the play.
   Recommendation: not yet; measure the plain version first.
5. **`fire` from the quiver, `inscribe`, `browse`, `run`** and the rest of the
   112 commands: added when something needs them, or all at once? The bridge
   speaks 29. Recommendation: **add on demand**, since the generated list means
   the prompt follows the bridge automatically.
