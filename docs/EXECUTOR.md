# The executor: the primitives a mind chooses between

From T05. A 100,000-turn game is about 10,000 player turns, so a model cannot
press every key (R2). The executor supplies eight primitives that run until
something changes and then say **why they stopped**; choosing the next one is
the mind's job.

```sh
python -m borg_agent agent --seed 1 --cap 10000 --mind scripted-primitives
```

## What a primitive is, and is not

A primitive paths, steps, rests, reads and buys. It holds **no tactics, no
thresholds and no valuations** (R2, [docs/SOURCES.md](SOURCES.md)): it has no
opinion about whether a monster is dangerous, whether hit points are low, or
whether an item is worth its price. At one hit point, with no limit asked for,
`walk_to` keeps walking — a test says so.

A threshold exists only when the mind asks for one, which it does in the
action itself:

```json
{"kind": "primitive", "reason": "Something is next to me; fight it.",
 "primitive": {"name": "fight_nearest", "stop_if_hp_below": 9, "max_decisions": 40}}
```

That keeps the judgement where it can be measured. If the executor decided
when to flee, the thing being measured would be the plumbing.

## The ten

| Primitive | What it does | Its own stops |
|---|---|---|
| `walk_to {target}` | the shortest known path to a square | `arrived`, `no_path`, `blocked` |
| `explore_floor` | walks to the nearest known square bordering the unknown | `explored` (nothing left), `unreachable` (somewhere unseen, but no known way to it), `blocked` |
| `fight_nearest` | attacks the nearest visible monster, closing in if it must | `no_target`, `no_path` |
| `rest_until_healed` | rests until whole | `healed`, `interrupted` |
| `take_stairs {direction}` | uses the staircase underfoot, or walks to the nearest known one | `changed_level`, `no_stairs_known` |
| `flee {by}` | leaves by the nearest staircase, or reads a Phase Door scroll | `fled`, `no_escape` |
| `read_unknown_scroll` | reads a scroll the player has not identified | `read`, `none_unknown` |
| `shop_list {list}` | buys or sells the labels on a list, in order | `bought`, `not_in_shop`, `missing_item`, `refused` |
| `cast_at_nearest {book, spell}` | casts that one spell at the nearest visible monster until it is gone | `no_target`, `no_such_spell`, `cannot_cast` |
| `study_a_spell {book?, spell?}` | learns one spell the game says may be learned | `studied`, `nothing_to_study` |

The last two are **T29's**, and R2's eight were written for a Warrior: a caster
that can neither cast nor study is not playing its class, and every Mage result
this repository had before them was a Mage deprived of magic. They hold no
opinion about *which* spell is worth casting — the mind names it by the two
letters the observation's `spells` list gives it — and the stops are the game's
own judgements: `cannot_cast` is the game saying no (unlearned, too low a
level, not enough mana), not ours.

Every primitive can also stop for a change that is not its own business:
`prompt` (a prompt opened), `changed_level`, `new_monster` (one the player
could not see before — except while fighting, where it is not a change of
plan), `hp_below` (only when the mind asked), and `decision_limit`.

## Pathing

Breadth-first over **what the player knows**, so it is deterministic and
depends on nothing but the observation:

- floor, stairs and open doors are walkable; a closed door is a step the
  executor takes with `alter`, which opens it;
- a square a monster stands on is not walked through;
- a **known trap is not pathed through** — walking round it is mechanical, and
  if there is no way round the mind is told `no_path` and decides;
- a shop entrance is reachable only as a destination, since stepping on it
  enters the shop.

The observation carries the whole of the player's known map, trimmed to its
bounding box. It began as a 41×21 window, which made exploration blind to
corridors the character had already walked: the frontier was always the window
edge. The box is small while little is known and grows with knowledge, which
is what R1.1 asks for; a 10,000-turn run averaged about 4 KB per observation.

## When the agent cannot act

If every primitive the mind offers stops at once — six in a row — the executor
raises `CannotAct` and the run ends as **`agent_stopped`** with that reason.
That is an outcome (R5), not a harness failure: the agent gave up.

A run also stops as `stalled` if the game answers 500 decisions without its
turn advancing. The turn cap cannot catch that on its own, because entering
and leaving a shop, or walking into a wall, costs no game time — which is
exactly how a first version of this executor burned 31,681 decisions in a
shop doorway.

## What the chooser decided is written down

A run with a chooser in front writes `decisions.jsonl`: one line per choice
(the primitive, the chooser's own reason, the stop it was answering) and one
per stop (the primitive, the reason, the turn, the decisions it took). The
commands in `actions.jsonl` carry only the executor's mechanical reasons —
"Walk towards (34, 11)." — so the journal is the only place that says *why*,
and `explain` reads it. See [docs/RECORDS.md](RECORDS.md).

## The scripted chooser

`mind.PrimitiveMind` is a fixture, not a policy: the shortest rules that
exercise the primitives deterministically. It fights what is next to it,
rests when hurt and alone, explores, and goes down when it has seen enough of
a floor. Its thresholds (half health, 150 decisions of exploring) are the
mind's own, which is the point.

On seed 1 to 10,000 turns it reached depth 2 and character level 3, fought,
rested and changed level twice (876 decisions, action stream `01aeca55…` —
unchanged by the move to the milestone 8 pin, since a scripted chooser does
not depend on the Borg's thinking). Its weakness, left as it is: on a floor whose
staircases it never finds it alternates `explored` and `no_stairs_known` and
waits out the cap rather than digging or going back up — a dumb fixture, not a
strategy.

## Checked on 2026-11-08

- The same seed and fixture played twice: **identical action streams** (876
  decisions, `01aeca55…`), and `verify` reproduced the run with the same state
  hash at every observation.
- The shop path was checked in a live store, twice. Buying label `a` (the
  Mushroom of Stoneskin, 60 gold) worked from the start. Buying label **`c`**
  did not, and that is how a real bug was found: the observation listed the
  stock in `store->stock` order while the store's menu uses
  `store_stock_list`'s order, so a label pointed at the wrong item — the agent
  asked for wine and bought a Ration of Food. The bridge now reads the stock
  the way the menu does; label `c` is the Ration the store offers there, and
  buying it charges exactly the listed price (140 → 137). A slow test keeps it
  honest. The Home is described the way its own screen describes it too: in
  full, with no prices.
- Each primitive is tested on fixtures, including the stops it reports and the
  fact that it has no threshold of its own.

## What is not here yet

- Spells, wands, throwing and targeting have no primitive and no key
  translation; `fight_nearest` is melee only.
- `flee` knows stairs and Phase Door, the two R2 names.
- Selling is implemented but was never exercised in a live store, and with the
  default birth options stores do not buy.
- The model-backed mind that chooses between these is T06.
