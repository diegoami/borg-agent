# Importing agent runs into the zoo

For a session working in **diegoami/borg-zoo** that adds the harness kind for
this repository (R6). It is the interface document, the way Mandos's
`docs/ZOO-HARNESS.md` is for `zoo/mandos.py`: the zoo's `docs/DESIGN.md` gets a
"**borg-agent specimens** (kind `agent`)" entry pointing here.

**Nothing in the zoo is changed by this repository** (RULES 8). This says what
the zoo needs, what it gets, and what it must not conclude.

## What an agent run is, and what it is not

The same C game as the `4.2.6-bbc-*` specimens — the same pinned source, the
same observer instrumentation, built the same way — with **the Borg's rules
replaced by a mind** at the Borg's own `inkey_hack` hook. A run's record names
the game pin it was played at (`engine.pins`), today better-borg-c milestone 8
(`017e038e`).

So a borg-agent "specimen" is not a game commit. It is the tuple the record
carries:

| Part | Where it is in the record |
|---|---|
| the game and Borg source | `engine.pins`, `engine.build_key`, `engine.binary_sha256` |
| this repository's own C and Python | `engine.commit`, `engine.dirty`, `engine.patch_sha256` |
| the mind: provider, model, family, profile | `mind.*`, per job in `mind.jobs` |
| the prompt pack | `mind.prompt_pack` (version and hash) |
| the knowledge base it played with | `mind.knowledge_sha256` |

**Agent runs are `deterministic: false`** (R6.3). The model's choices are not
reproducible; the *recorded run* is. Two agent runs on one seed are two
different games played in the same world.

**They pair with C runs by seed**, unlike Mandos: the same seed gives the same
starting game, because it is the same engine at the same pin. What the zoo may
not do is call two agent runs the same game — see below.

## What the zoo gets: the import bundle

| File | What it is |
|---|---|
| `run-record.json` | one `borg-agent/run-record@1` document, immutable once written (R4.1) |
| `actions.jsonl` | the action stream the replay feeds back; its count and hash are in `action_stream` |
| `state-hashes.txt` | one hash per observation, in order; its hash is `evidence.state_hashes_sha256` |

Everything else stays with us and is addressed by hash in the record: the
observations, the model call log, the chooser's journal, the trace. The zoo
never needs them to confirm a run, and they are the part that is large.

A bundle is self-describing: the record names every hash, so the zoo can tell
that the bundle it holds is the run the record describes before replaying
anything (`record_matches_run` in the verdict).

## Replaying an imported run, without a model

```sh
python -m borg_agent build                      # the pins the record names
python -m borg_agent verify --run <bundle>      # borg-agent/verify@1
```

The build is the zoo's own recipe plus this repository's bridge: the runner and
observer are **byte-identical** at the zoo's harness commit (`fc9d97cb`) and at
the game pin, which four tests here check. CI needs **no model and no key**,
and must never be given one (RULES 16).

The verdict says:

| Field | Meaning |
|---|---|
| `verified` | the run reproduced, as far as its scope allows |
| `scope` | `full` when the game ended the run — every state hash, the outcome, the cause, the turn and the trace must match. `prefix` when the harness ended it (a cap, a budget, a stall): every recorded state must match and the stream must run out where the recording stops |
| `state_hashes_match`, `first_differing_decision` | where a divergence is, by decision, not by outcome |
| `record_matches_run` | every count and hash the record published is still the file the replay read |
| `comparable`, `comparable_reason` | `false` when the run and the replay fall on opposite sides of the game's seasonal window (24–26 December, decision D9). Not a failure to reproduce: the game admits different monsters on those days, so the comparison is refused instead of being called a divergence |

**Cost.** Replaying a 1,000-turn, 51-decision agent run took **0.3 s** on one
CPU (measured 2026-11-09, `records/api-first.json`). A replay is the game at
full speed with nothing waiting on a model, so an imported suite costs the zoo
about what a stock-Borg suite of the same caps costs, minus the Borg's thinking.

**What this repository still owes before the zoo's PR**: `verify` reads a run
*directory* today, including its `result.json`. A bundle-only mode — record plus
the two streams — is ours to add, and this document is its specification. The
zoo should not work around it.

## Mapping a record onto `borg-zoo/cell@1`

| Cell field | From the record |
|---|---|
| `harness_kind` | `agent` |
| `specimen_ref` | `engine.commit` (this repository), with `engine.pins['better-borg-c']` as the game |
| `seed`, `cap` | `game.seed`, `game.turn_cap` |
| `birth` | `game.birth.rule` (`fixed` for the cohort's Human Warrior, `assigned` when the run asked for a race and class) |
| `played_race`, `played_class`, `character` | `game.birth.race`, `game.birth.class`, `game.birth.name` — read by the observer from the game, not from what was asked for |
| `outcome`, `runner_outcome` | `outcome.kind` |
| `cause` | `outcome.cause` |
| `final` | `outcome.turn`, `.depth`, `.max_depth`, `.level`, `.max_level`, and `usage.decisions` |
| `first_turn_at_depth` | `outcome.depth_marks` |
| `wall_seconds` | `usage.wall_seconds` — **dominated by model latency**, not by the game |
| `trace_sha256` | `evidence.trace_sha256` |
| `config_sha256`, `effective_options` | `game.settings_sha256`, `game.settings` (the observer's own effective-settings line) |
| `binary_sha256`, `compiler`, `platform` | `engine.*`, captured at play time, not at recording time |
| `calendar` | `calendar`, including `seasonal` |

Agent-only fields the zoo should keep, because they are what an agent run is
judged by:

`deterministic: false`, `mode` (`play`, `post_mortem`, `probe`, `consolidate`,
`trial`), `intervention`, `parent` and `from_turn` (a mode B run names the run
and turn it took over at), `mind.*`, `usage.model_calls`,
`usage.prompt_tokens`, `usage.completion_tokens`, `usage.parse_failures`, and
`mind.budget`.

`play_sha256`: the zoo computes it from the trace without the configuration
lines. It stays well defined for an agent run, but it identifies **that run**,
never the agent: two models, or one model twice, give different traces on the
same seed. Do not use it to assert that two agent runs are the same game.

A record that cannot say what it must does not exist: the recorder refuses to
write one when the observer's settings or birth-option lines are missing, so
the zoo's `config_error` case cannot arrive as a half-filled cell.

## What the zoo must not conclude

1. **Never "identical games" for two agent runs**, and never treat one agent
   run as a fixed property of the agent (R6.3). A subset of seeds is run twice
   to measure how much the agent varies; that variation is the figure, not an
   anomaly.
2. **Interventions never enter survival figures** (decision D4). A mode C
   probe builds its situation with the game's own debug commands and is marked
   `intervention: true`; the game's own `NOSCORE_WIZARD` flag is set on such a
   character. Probe trials are evidence for a claim, not survival data.
3. **`budget_cap`, `agent_stopped` and `decision_cap` are outcomes, not
   failures, and none of them is a death** (R2.3, R5). `harness_failure` is
   ours — a provider that refused, timed out or could not be reached — and
   says nothing about the game.
4. **Agent results go on a page of their own** and not on the landing page
   until the owner says so (R6.5).
5. A mode B run (`mode: post_mortem`) is **not** a run from birth: the Borg
   played its prefix and the agent took over at `from_turn`. Its survival
   figures belong beside its parent, not beside full games.

## Suites, and the order to do this in

- Start with **`classes-18`**: 18 seeds, assigned births, the same caps as the
  Borg suites (R6.4). Assigned births are possible here since T24 — a run can
  be born any race and class the game offers, and a replay is born the same
  character.
- Model calls dominate the cost of *playing*: the measured run was **5 calls
  per 1,000 game turns** with the executor in front of the mind, and 99 s wall
  of which about 90 s was the model. The zoo's wall limits apply to its own
  replays, which are the 0.3 s above.
- The agent plays on the owner's machine or a runner with model access
  (decision D3); the zoo imports and replays. That split is the point of R6.2:
  **CI checks the record, not the agent.**

## A catalogue entry, for the shape of it

```json
"4.2.6-agent-qwen3.8-flash": {
  "kind": "agent",
  "repository": "diegoami/borg-agent",
  "ref": "<the borg-agent commit the runs were played at>",
  "game": "4.2.6-bbc-m8",
  "import_only": true,
  "label": "borg-agent: qwen3.8-flash plays the m8 game through the Borg's connection",
  "source": "https://github.com/diegoami/borg-agent/blob/main/docs/ZOO-IMPORT.md"
}
```

`import_only` is the part that differs from every specimen the zoo has: there
is nothing for the zoo to run. It verifies what it is given.
