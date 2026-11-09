# Run records, and replaying a run

From T04. A run record is what makes a run evidence: it holds everything
needed to play the game again without the mind that played it, and the five
tools of R5 work on it.

```sh
python -m borg_agent agent  --seed 1 --cap 1000            # play; writes runs/<name>/
python -m borg_agent record --run runs/<name>              # the run record
python -m borg_agent verify --run runs/<name>              # replay and compare
python -m borg_agent branch --run runs/<name> --turn 500    # play on from turn 500
python -m borg_agent view    --run runs/<name> --turn 500
python -m borg_agent dump    --run runs/<name> --turn 500
python -m borg_agent explain --run runs/<name> --turn 500
```

## What a run directory holds

| File | What |
|---|---|
| `result.json` | the harness's own account of the run: command, limits, outcome, calendar, the action stream's hash |
| `observations.jsonl` | every observation the mind was shown, one per line |
| `actions.jsonl` | every action it answered, one per line, valid against `action@1` |
| `trace.txt` | the observer's trace: turn, RNG state, options, the Borg's notes |
| `state-hashes.txt` | one hash per observation, written by `record` |
| `decisions.jsonl` | the chooser's decisions and the executor's stop reasons, when a chooser was used (a branch keeps the journal of the mind that took over) |
| `run-record.json` | the record itself, valid against [`run-record@1`](../schemas/run-record@1.json) |
| `terminal.log`, `input.txt`, `user/borg.txt` | what the game was given |

## The record

`src/borg_agent/record.py` builds it from a finished run. The schema
**requires** what R5 names, so a record that validates can actually be
replayed:

- the pins of every repository used, the build key, the binary hash, the hash
  of every patch applied (the observer's files and the bridge's), the game
  data's hashes, the compiler and platform;
- **this repository's commit and whether the tree was dirty** — a record from
  a dirty tree is not reproducible from its commit alone, so the field is
  required and may be empty but not absent;
- the seed, the birth rule and the birth options the observer printed, the
  effective settings from the observer's own `BORG_OPTIONS` line and the hash
  of `borg.txt`, and the hash of the birth key script;
- the **calendar** (see "The date" below);
- the action stream's count and hash, and hashes of the trace, the
  observations and the state hashes;
- the outcome with its cause or reason, the final and maximum depth and level,
  and the first turn at each depth;
- who decided: `stock-borg`, `scripted`, `external`, `api` or `replay`. An
  `api` run must also name the job, profile, provider, model, family, how they
  were chosen, the context size, the budget, the prompt pack and the knowledge
  hash (R2.1–R2.3, decision D7). A field with nothing to say is `null`, but it
  is stated.

`deterministic` is true exactly when no model chose anything; `intervention`
marks a run set up with debug commands, which never counts in survival figures
(decision D4).

A record is **immutable** (R4.1): `record` refuses to overwrite one. A
correction is a new record.

### The state hash

The state hash of an observation is a SHA-256 over the observation in
canonical form, with the run's own `run_id` left out — everything else the
agent was shown is part of the state, down to the order of the messages. Key
order cannot change it. That is what lets a replay in another directory
produce the same hashes, and what `verify` compares decision by decision.

## verify

`verify` replays the recorded action stream with the `replay` mind — no model,
no scripted rules, just the recorded answers — and compares the state hash at
**every** observation, reporting the first decision that differs, then the
decisions, the outcome, the cause, the final turn and the trace's hash. It
writes `verify.json` with both sides of each comparison.

**How far it can compare depends on how the run ended**, and conflating the
two was the main finding of the milestone 2 review:

| The run ended because | `scope` | What must match |
|---|---|---|
| the **game** ended it: a death, the turn cap, a win | `full` | every state hash, the decisions, the outcome, the cause, the final turn, the trace |
| the **harness** ended it: a decision or budget cap, a stall, a wall limit, the agent giving up | `prefix` | every **recorded** state hash, and the stream must run out exactly where the recording stops |

A capped run is the expected shape of a model run (R2.3), and it can never
replay to the same end: the game would have played on, and the recording
stops. The replay therefore sees one observation more than there are recorded
actions — the game asks again, and there is nothing to answer with — and the
`replay` mind raises `StreamEnded`, which the run records as `agent_stopped`
with the decision and turn. `verify` reads that as "the stream was replayed to
its end" and says so in `verified_as`. Before this, such a run reported
`verified: false` with "the states differ" while naming no difference at all.

`verify` also checks **the record against the run**: every count and hash the
record published — the action stream's count and hash, the observations, the
state hashes, the journal — must still be the file the replay read
(`record_matches_run`, with `record_mismatch` naming the first that does not).
All of them, not just one: with only the state hashes compared, a run could be
cut short at the end — the replay reproduces what remains, and `prefix`
tolerates a stream that ends early — while the record still claimed the longer
run. That hole was opened by the `prefix` tolerance itself and found by the
re-review.

One limit of `prefix` by construction: it compares no part of the trace, so a
divergence that shows only in the trace's RNG fields *after* the last recorded
decision is out of its scope. A run the game ended is compared on the trace as
well.

Checked on 2026-11-09: a 101-decision run verified `full`; a run stopped at a
decision cap of 20 verified `prefix` with all 20 states reproduced; a run with
one recorded action altered was refused, naming decision 2; and a run whose
logs were both cut short by three decisions was refused, naming the action
stream.

A record's immutability is a convention — `record` refuses to overwrite one —
and nothing anchors its hash outside the run directory yet. The zoo's import
contract (T11) is where that gets settled.

A replay that ends on the stream records its own outcome as `agent_stopped`:
the vocabulary has no word for "the recording ended", and the `stream_ended`
block carries the truth. A record of a replay would therefore read
`agent_stopped` with `mind.kind: replay`; nothing records replays today.

Run directories made before T15 have no `provenance` block in their
`result.json`, so no record can be written for them. They were throwaway; the
refusal is deliberate.

## branch

`branch --turn T` replays the recorded actions until the game reaches turn T,
then hands over to another mind. The new run's record names its `parent`: the
run it continues and the turn it took over at (the first observation at or
after T, which is recorded as `handed_over_at`, since turns advance in steps
of ten).

That is the mechanism mode B needs (R3): take a recorded death, go back k
turns, and try something else. Checked on 2026-11-08: branching that same run
at turn 500 replayed 51 actions, handed over at turn 501, and played on to the
cap with a different mind; the observations before the handover are identical
and the ones after are not.

## view, dump, explain

All three read the recorded observations, so they cost nothing and need no
build. Each takes the last observation at or before the turn asked for.

- `view` prints the screen as the player saw it;
- `dump` prints or writes the observation;
- `explain` prints the decisions around that turn with their actions, reasons,
  hit points, depth and messages — and, when a chooser was picking primitives,
  what it chose, why, and why the primitive before it stopped. When a model is
  deciding (T06) the model call joins that line.

### The journal

A run whose mind chooses primitives writes `decisions.jsonl` beside the
actions — including a **branch**, where the mind that took over is the one with
something to say (the `replay` mind passes the drain through to it): one line per choice (which primitive, the chooser's own reason, and
the stop it was answering) and one per stop (which primitive, why, at which
turn, after how many decisions). The commands in `actions.jsonl` carry only
the executor's mechanical reasons, so without the journal a record could not
say why the agent stopped exploring at a turn — which is what R2 has
primitives report stops for. Its hash goes into the record's evidence as
`journal_sha256`.

## The date

Play is **not** independent of the calendar date: the game admits seasonal
monsters on 24-26 December, so the same seed plays a different game on those
days. Every record therefore carries a `calendar` block, and `verify` records
both sides' `seasonal` flags in its verdict and **refuses to compare across
the window**. A replay that must match a record made inside it has to run on a
day of the same kind.

Whether to neutralize that clock read in the instrumented build is the owner's
open question: it would make replay date-independent at the price of play
differing from the unpatched game on three days a year, which RULES 9 leaves
to them.

## What is not here yet

- `explain` has no model calls to show until T06, and no notes until the
  notebook of R2.3 exists.
- A stock-Borg run (T01) has no action stream, so `verify` does not apply to
  it; its determinism is checked by replaying the seed instead.
- The zoo's import contract (T11) says which of these fields the zoo needs and
  how its CI replays an imported run.
