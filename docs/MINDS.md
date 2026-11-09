# The mind: who decides, and what it is told

From T06. The executor runs primitives; the **mind** chooses which one, with a
one-line reason. There are four, behind one interface — `act(observation)`
returns an [`action@1`](../schemas/action@1.json) action:

| Mind | Who decides | For |
|---|---|---|
| `scripted` | fixed rules | tests, and the gates |
| `scripted-primitives` | fixed rules, choosing primitives | tests |
| `external` | a person or another session, through files | debugging a few decisions by hand |
| `api` | a model on an OpenAI-compatible chat API | the real thing |

```sh
python -m borg_agent agent --seed 1 --cap 1000 --mind api --budget-calls 8
python -m borg_agent agent --seed 1 --cap 1000 --mind external --external-dir /tmp/ask
```

## Which model: `models.yaml` and the active profile

`src/borg_agent/models.py` is the only thing that decides which model does
which job (decision **D7**). The active profile is the first of:

1. `BORG_AGENT_PROFILE` in the environment — the record says
   `chosen_by: environment`;
2. `profile:` in `models.local.yaml`, which git ignores and which may also
   override single jobs — an overridden job says `local override`;
3. `default_profile` in `models.yaml` — `profile`.

The loader refuses a configuration rather than letting a run discover it:

- it validates both files against [`models@1`](../schemas/models@1.json);
- **a field whose name contains `key`** (other than `api_key_env`) is refused
  before anything else is even validated, in either file, so a key in the file
  cannot reach a validator's error message;
- a profile, provider or job that does not exist is named;
- `review.family` must differ from `consolidate.family` (R4.3) — checked
  **after** the local overrides, because the rule is about what the run will
  actually do;
- a job without `context_k` gets the loader's default, 32k;
- the key is read from the environment when a call is made. A missing variable
  fails **before play**, naming the variable and never its value.

What the run record is told per job: the profile, provider, model, family, how
they were chosen, the context size, the endpoint's **host** and the hashes of
both model files. Never a key, a header, or a URL with credentials.

## What the model is told: prompt packs

A pack is a directory under `prompts/`, named by its version (`play-1`). It
holds the templates and a manifest naming its **extracts**: each one a source
from `pins.json`, a path, and the headings between which the text was taken.

```json
{"as": "movement_and_resting_commands", "source": "manual",
 "pin": "better-borg-c", "path": "docs/command.rst",
 "from": "Movement Commands", "to": "Alter Commands"}
```

The pack is refused if it draws on something `pins.json` does not name as a
source, or reads a source at a pin other than the one that source is read at.
That is the test docs/SOURCES.md asks for, and it is about **provenance, not
permission** (decision D8): the agent may read a great deal, and what matters
is that a prompt says where its words came from, so a claim made from it can
cite them. The pack's SHA-256 covers the manifest, the templates **and** every
extract, and it goes in the run record.

What `play-1` tells a model: the task, the primitives **generated from the
executor's own code** (so a prompt cannot promise a primitive that does not
exist, or forget one that does, or claim a stop a primitive never reports), the
answer format, and the game manual's own words about moving and resting, with
the citation `docs/command.rst at better-borg-c 017e038e8726`.

What it is *shown* each decision is a summary, not the observation: the
character line, a 61×21 window on the known map with `@` on the player, the
monsters in sight with their distance, the inventory, the shop's stock when in
one, the messages since the last decision, any waiting prompt, and **why the
last primitive stopped**. About 2,000 tokens a decision, of which the system
message is 1,600 and the same every time.

## The call log, and the budget

Every call is written to `model-calls.jsonl` (R2.1): the observation's state
hash, the pack's version and hash, the job, provider, model, family and effort,
the endpoint's host, the reply, **the model's own thinking**, the reason, the
tokens and the seconds. The key never appears — it is a header, built in the one
method that makes the request.

**The thinking is not in the reply.** A thinking model returns it beside the
answer — `reasoning_content`, `reasoning` or `thinking`, depending on the
provider — and the first Mage run billed **3,781 completion tokens for a
270-character reply**: everything it had to say was in a field we were not
reading. It is kept now as `reasoning`, with `reasoning_chars` beside it, and
it is redacted like every other field. The run pays for those tokens whether or
not they are kept, and they are the only account of *why* a choice was made
beyond the one line the model writes into its action — which is what T09 has to
judge a consolidator on, and what a post-mortem is supposed to explain itself
with.

**Every field of an entry is scanned, not only the reply**, and anything that
looks like a credential is replaced where it stands; a field named like a key
goes too. The rest of the entry stays, because the call has already happened
and the entry is the evidence R2.1 asks for — which is why a log is redacted
where a record is refused. (Until the milestone 3 review only `reply` was
replaced, so a key the model put in its `reason` was logged intact.)

A run's budget is `--budget-calls` and `--budget-tokens` (R2.3), and an `api`
run **must name one**: with neither flag the only ceilings were the decision
cap and the wall clock, which in tokens is enormous. `--no-budget` runs without
one, deliberately and on the record. The rule is *spend up to the limit, then
stop*, since a call's cost is only known afterwards. Reaching it ends the run
with the outcome **`budget_cap`** and the reason — an outcome, not a failure.

A reply that cannot be read as an action is counted, and the model is asked
again once with its own words and a correction. Twice over and the run ends
`agent_stopped`, saying what was wrong — the agent never guesses an action. A
provider that refuses or cannot be reached is `harness_failure`: infrastructure,
not play, and nothing about the game is concluded from it.

## What a real run looked like

On 2026-11-09, the first game a model played here — `qwen3.8-flash` on the
Alibaba Token Plan, profile `alibaba`, pack `play-1`, seed 1, cap 1,000, budget
8 calls:

| | |
|---|---|
| outcome | `turn_cap` at turn 1,000, 51 decisions |
| model calls | **5**, no parse failures |
| tokens | 10,470 prompt, 7,496 completion (17,966) |
| time | 14 s a call (median), 99 s in all |
| what it chose | explore the town, take the stairs down, explore the new floor, fight a giant centipede, rest at 15/40 hit points |
| afterwards | the record validates, and **`verify` replayed the run exactly** — 51 decisions, every state hash equal |

**Five calls for a thousand game turns** is the economy the executor buys: the
model is asked when a primitive stops, not when the game asks for a key. At
that rate a 20,000-turn pilot run is of the order of a hundred calls, which is
what T09 and T10 should budget for — and a figure to measure again with a model
that chooses worse and so stops more often.

A second run with `--budget-calls 2` ended `budget_cap` after two calls, as it
should.

## What is not here yet

- **Knowledge in the prompt.** `render` takes a `knowledge` argument and the
  system message has a place for it, but nothing fills it: the store is T07.
  Until then a model plays on what it can see and what the manual says.
- **A pack per job.** `play-1` is the only pack; consolidation and review get
  their own in T07.
- One model per run in practice. The record can carry several
  (`mind.jobs`), which T07 and T08 will use.
- The `external` mind writes a question and waits for an answer file; nothing
  yet drives it from outside.
