# The knowledge base

From T07. **The knowledge base is the product** (R4): not the games played, not
the code, but a set of claims about Angband that a person can review, an
experiment can check, and the Rust remake can be built from.

```sh
python -m borg_agent consolidate --run runs/<name>    # a run becomes claims (mode D)
python -m borg_agent knowledge list                   # what is known
python -m borg_agent knowledge views                  # rebuild the Markdown
```

## What is in `knowledge/`

| | |
|---|---|
| `claims.jsonl` | the claims, one JSON object per line, appended and never rewritten |
| `<area>.md` | a generated view per area — monster, danger, tactic, … |
| `README.md` | the index: each area, how many claims, how well established |

The Markdown is **generated**. A claim changes by being superseded, never by
being rewritten, so editing a view would only make it disagree with the
claims. A test fails if a view in git is stale.

## What may enter

Two guards, and they are not the same:

- the **schema** ([`claim@1`](../schemas/claim@1.json)) checks the shape: one
  plain statement, an area, a scope, a basis, evidence that names a run and a
  turn, a confidence in words, the phase and the sources;
- **`borg_agent.checks`** checks what a schema cannot, because it compares one
  field with another: that a review came from a different family than the
  producer, that a `quantified` basis does not claim more successes than
  trials, that a model-written claim names its model and family (R4.3).

And one rule the store itself keeps: **a claim a model wrote enters as
`hypothesis`**, whatever status it asked for, and the claim records that it was
lowered. A probe's counted result or a review by another family moves it on;
the owner decides what becomes part of the remake's specification.

A duplicate id is refused. A correction is `supersede(old_id, new_claim)`,
which adds the new claim and writes a `superseded_by` pointer into the old
one — the only edit the store makes, and it adds a pointer rather than
changing what a claim says. A superseded claim never goes into a prompt.

## Mode D: a run becomes claims

`consolidate` reads a finished run — its outcome and cause, the depths and
levels reached, **what the agent chose and why**, its own notes, and the last
messages the game printed — and asks the profile's `consolidate` model what the
run teaches.

What the harness decides, not the model:

- **the status**: `hypothesis`, always;
- **who wrote it**: `produced_by` is filled from the configuration, because a
  model asserting its own identity is worth nothing;
- **the seed and the run id** in every piece of evidence; a claim that points
  at no turn of the run is refused, because nothing could check it.

Everything accepted goes into the store, the views are rebuilt, and
`consolidation.json` beside the run records what was offered, what was added,
what was refused **and why**, the model, the pack and the tokens.

## What a prompt carries

`Store.for_prompt(observation)` gives the play prompt one line per claim, best
established first, leaving out what cannot apply: a claim scoped to a Mage, or
to depth 20, is not shown to a level-2 Warrior in the town. The filter is
mechanical; whether a claim is *useful* is the mind's judgement, not the
store's. `--no-knowledge` plays without it, and the run record carries the
knowledge base's hash so a decision can be traced to what the agent knew.

**It is asked once per decision, with that decision's observation.** The
milestone 3 review found the wiring resolving it once, at mind construction,
with no observation at all — so the filter never ran and every claim rode every
decision. The mind takes a retriever, not a finished string, and the store's
own test was never the thing in doubt.

A claim is **scanned for credentials before it enters** (RULES 16), like a run
record. It is model words with a worse destination than a log: `claims.jsonl`
is in git, the views are generated from it, and `for_prompt` reads it back into
every later prompt.

## The first real claims, and what they showed

On 2026-11-09 `qwen3.8-max` consolidated the first model-played run (51
decisions, seed 1, 1,000 turns). It offered seven claims and all seven were
accepted — anchored to the run, to the seed and to a turn:

- *A Human Warrior can kill a giant yellow centipede in melee on dungeon
  depth 1* (turn 431)
- *A wild cat can hit the Human Warrior with a claw attack on dungeon depth 1*
  (turn 479)
- …and five more.

**The machinery works, and the first claims are thin.** Two are real game
knowledge; the rest restate the run — *the run ended because it reached the
1000-game-turn cap* is true, checkable, and teaches nothing. That is a finding
about the prompt, not about the model: `consolidate-1` asks for claims the run
supports without saying that a claim should be about **the game** rather than
about this run's narrative. The next version of the pack should say so, and
T09's trial will measure exactly this — its most important number is **false
claims**, and the second is whether a claim is worth having at all.

It cost one call, 13,373 tokens and **284 seconds** — about ten times a play
decision. A consolidator reads a whole run, so the first real call timed out at
the play mind's 120-second limit; the default is 420 now.

## What is not here yet

- **No probe (mode C).** Nothing can move a claim past `hypothesis` by
  counting, so every claim in the store today is a hypothesis.
- **No review job running.** The profile names a reviewer of another family
  (R4.3) and `checks` enforces the rule, but nothing calls it yet.
- **No contradiction finding.** R3's mode D also asks for contradictions
  between claims and questions for mode C; consolidation does neither.
- A claim's `static:` references are not checked against the sources they
  name — the schema requires a reference, nothing verifies it points at
  something real.
