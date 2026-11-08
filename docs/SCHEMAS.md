# The schemas

From T02. Four versioned JSON Schemas (draft 2020-12) under
[`schemas/`](../schemas), each with examples beside it in
`schemas/examples/<name>/`: `valid-*.json` must validate, `invalid-*.json`
must not, and an invalid example's file name says which rule it breaks.
`tests/test_schemas.py` checks all of that, and the rules below that a schema
can't express on its own.

| Schema | What it is | Requirement |
|---|---|---|
| `observation@1` | what the agent is shown at one decision | R1.1 |
| `action@1` | one answer from the mind | R1.2, R2 |
| `run-record@1` | one run, replayable, with its provenance | R5 |
| `claim@1` | one statement about the game, with its evidence | R4 |

The examples beside each schema are fixtures, not knowledge: see
[schemas/examples/README.md](../schemas/examples/README.md).

Each carries its own name in a `schema` field (`borg-agent/observation@1` and
so on), so a file says what it is. A later version is a new file and a new
field value; nothing in version 1 changes meaning.

## observation@1

Only what the player could know: the map as the player knows it, the monsters
the player can see (with `name: null` until the player has learned it), the
character's own state, the messages since the last observation, the shop's
stock while in a shop, and the open prompt or menu.

A monster entry has no room for what the player cannot know — there is no
`hp` field, and unknown values are null. The level feeling is the words the
game gives the player; the danger and treasure numbers behind it are cave
internals, so they are not in the ordinary map.

Anything taken from the true game state goes under `true_state`, which is
absent by default and must list the name of every true-state field it carries.
**That naming rule is a comparison between fields, which a JSON Schema cannot
make**, so it lives in `borg_agent.checks.check_observation`, which runs on
every observation the bridge writes. The schema alone would accept
`{"fields": ["a"], "b": 1}`; the check does not.

## action@1

`kind` is `primitive` (an executor primitive of R2), `command` (one game
command with its arguments) or `keys` (raw keypresses, the escape hatch of
R1.2, which must say why no command covers it). The payload of another kind
is rejected rather than ignored, each primitive must carry the arguments it
needs (`walk_to` a target, `flee` a way out, `shop_list` a list), and a
command may not both name a target and ask for the nearest one.

Every action carries a one-line `reason`, which is recorded with the model
call (R2.1), and may carry a `note` for the notebook.

## run-record@1

Enough to replay the run and to judge its evidence: the pinned commits, the
build key and binary hash, the patch hashes, the seed and birth, the
settings, the action stream and its SHA-256, hashes of the other streams, the
outcome, and what the run cost. Records are immutable once written (R4.1); a
correction is a new record.

**Outcomes** are the zoo's vocabulary — `death`, `completion`, `turn_cap`,
`stalled`, `wall_timeout`, `crash`, `harness_failure`, `config_error`,
`decision_cap` — with `borg_stopped` renamed `agent_stopped` and
`budget_cap` added (R5). A death names its cause; `agent_stopped`,
`harness_failure` and `config_error` name their reason. Only `death` counts
as a death.

**The model** comes from the active profile in `models.yaml` and from nothing
else (decision D7): the record names the job, profile, provider, model,
family, how they were chosen (`profile`, `local override` or `environment`),
the context size and the hashes of the model files. There is no field for a
key, and the mind block refuses unknown fields, so a key cannot be recorded
by accident (RULES 16). `endpoint_host` is a host, never a URL with
credentials.

`deterministic` is false for any run a model decided (R6.3); replaying its
recorded action stream is deterministic either way. `intervention` marks a
run set up with debug commands, which never counts in survival figures
(decision D4).

## claim@1

The lifecycle of R4, which this repository takes from game-archaeologist: a
single plain statement, its area, scope, status, basis, evidence, a
confidence in words (what it rests on, and which alternatives were ruled
out), the phase and the sources that produced it.

The schema enforces what it can:
- a tactic or readiness claim says how a program would test it;
- `documented` means the manual says so, so its basis is the manual;
- `quantified` carries its N of M;
- run evidence names the run and the turn, and there is at least one piece of
  evidence;
- a `corroborated` claim names the probe or the review that moved it there,
  since a model never promotes its own claim past `hypothesis` (R4.3);
- a claim read in a source (`static:game-source`, `static:borg-source`,
  `static:borg-spec`, `static:deaths`, `static:issue`) names its reference:
  the file and the pinned commit, the specification's section, the death's id,
  or the issue's number and the date it was read. Any phase may use such a
  basis (decision D8); what matters is that the record says whether a fact was
  read or seen.

What a schema cannot check is a comparison between fields:

- that the reviewer was of **another family** than the producer (R4.3);
- that a `quantified` basis does not claim more successes than trials.

Both live in `borg_agent.checks.check_claim`, beside the observation's
true-state rule. The schema carries what it can — `produced_by` is required, a
model names itself and its family, every review names a family (null for a
probe), run evidence names its seed and turn, and anything above `hypothesis`
rests on counted trials or on a review — and the check does the rest. T07 runs
both when a claim enters the store.
