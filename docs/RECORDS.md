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
no scripted rules, just the recorded answers — and compares:

1. the state hash at **every** observation, reporting the first decision that
   differs;
2. the number of decisions, the outcome, the cause, the final turn;
3. the trace's hash.

It writes `verify.json` with both sides of each comparison, and
`verified: true` only when all of them agree. Checked on 2026-11-08: a
101-decision scripted run on seed 1 at cap 1,000 verified, with identical
state hashes at all 101 observations and the same trace.

If the recorded stream runs out before the game stops asking, the replay says
so and names the decision — it never invents an action.

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
  hit points, depth and messages. When a model is deciding (T06) the model
  call joins that line.

## The date

Play is **not** independent of the calendar date: the game admits seasonal
monsters on 24-26 December, so the same seed plays a different game on those
days. Every record therefore carries a `calendar` block, and `verify` records
both sides' dates in its verdict. A replay that must match a record made in
that window has to run on the same day until the build neutralizes that clock
read — which is T12.

## What is not here yet

- `explain` has no model calls to show until T06, and no notes until the
  notebook of R2.3 exists.
- A stock-Borg run (T01) has no action stream, so `verify` does not apply to
  it; its determinism is checked by replaying the seed instead.
- The zoo's import contract (T11) says which of these fields the zoo needs and
  how its CI replays an imported run.
