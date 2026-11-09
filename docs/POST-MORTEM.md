# Mode B: taking over before a death

From T08. The requirements call this the cheapest knowledge per model call
(R3), because the game has already done the expensive part: it has killed
somebody, and said what killed them.

```sh
# find a death on a seed, then take over 200 turns before it
python -m borg_agent post-mortem --seed 7 --cap 100000 --before 200 --mind api

# or work from a death already recorded
python -m borg_agent post-mortem --run runs/death-seed7-cap100000 --before 500
```

## How it works, and why there is no save file

The Borg's play is **deterministic** — that is T01's gate — so a death does
not need to be frozen and thawed. Playing the same seed again brings the game
back to the same place, turn for turn.

So the bridge keeps the agent's hand off the wheel until a turn the run names
(`BORG_AGENT_FROM_TURN`): before it, `agent_active()` is false and the Borg
decides, exactly as it would in a plain run; at that turn the pipes open, the
handover is written into the trace, and the agent plays on. Nothing is
serialized, and the Borg's own memory — which the runner's own notes say a save
does not fully carry — is never in question, because the Borg built it by
playing.

That also makes a post-mortem **replayable like any other run**: `verify`
reads the handover turn (`from_turn` in the run directory's `result.json`),
replays the Borg's prefix by playing it, and feeds the recorded actions back
from the handover. The prefix comes back by itself; the agent's part comes back
from the stream. The **run record** carries `from_turn` as well, so a record
alone says where the agent's own play began — it did not until the milestone 3
review pointed out that the document and the code disagreed about which
artifact was authoritative.

**A branch of a post-mortem plays the same prefix.** `branch` left `from_turn`
out, so the actions recorded from the handover were fed to a newborn character
in the town: a self-consistent recording of a different game under the parent's
name, which even verified. Branching before the parent's handover is refused,
because the recording does not reach there.

**What is refused, and what is flagged.** The handover must be before the death
and the cap after it, and `--before` cannot be negative: otherwise the Borg
dies before the agent has a decision and the post-mortem block reads as if the
agent had tried and failed. A run where the agent never got a decision carries
`agent_played: false` and a warning saying the other fields describe the Borg's
own play.

The cost is time rather than storage: taking over at turn 20,000 means playing
20,000 turns of Borg first, about a minute at the milestone 8 pin.

## Where the cases come from

**Deaths this build produces.** The task originally named two of the zoo's
`classes-m6` floating-eye deaths, but the game pin is better-borg-c milestone
8 now and the zoo has no m8 results — so those are deaths of a build we no
longer play (T17).

The pinned tree's own `docs/deaths/` is richer than anything we can make: 19
cases, each with a verified replay, an assessment with findings and status, and
an issue. `D0001` is a stegocentipede death at turn 174,862 with the fight
reconstructed hit by hit. But those cases belong to **older builds** — `D0001`
carries five fixes where milestone 8 carries 88 — and to turns in the hundreds
of thousands. They are a **source to read** (decision D8), which is how a
post-mortem gets its questions, not a case list we can reproduce.

So a case is found by playing: `post-mortem --seed N` plays the Borg until it
dies and then takes over. Milestone 8's Borg is good, which makes this slower
than it was.

**Known at the milestone 8 pin** (searched on 2026-11-09, cap 30,000):

| Seed | What the Borg did |
|---|---|
| 1, 2 | survived 30,000 turns |
| **3** | **died: a green naga at turn 15,714** |
| 7 | survived 100,000 turns (it died to a green naga at 27,808 at milestone 6) |

`BORG_AGENT_DEATH_SEED` tells the slow gate which seed to use; without it the
gate skips, because finding a death costs minutes of play and CI has no case
to work from.

## What a post-mortem records

The run is a branch of the death: its record has `mode: post_mortem` and names
its `parent` — the death's run id and the turn the agent took over at — and its
`result.json` carries a `post_mortem` block:

| | |
|---|---|
| `death` | the run, seed, turn and cause it was taken from |
| `asked_to_take_over_at` | the handover turn |
| `survived_past_the_death` | did it get further than the Borg did? Compared against the record's `final_turn`, which is the **last sampled** state — the observer writes one every hundred Borg decisions — so it understates rather than overstates |
| `died_again`, `same_cause` | did it die anyway, and of the same thing? |

Those last three are the question mode B exists to ask, and they are recorded
as facts rather than conclusions: one branch surviving proves that *this*
death was avoidable from that turn, not that the Borg was wrong. A claim from
it says so, and mode C's probe — N of M trials — is what turns it into a
number.

## The first real post-mortem

On 2026-11-09, on the case above: the Borg died to a green naga at turn
15,714 on seed 3. `qwen3.8-flash` took over at turn **15,514** — 200 turns
before the end the Borg was known to come to.

It explored, met a monster, chose to fight it, and **got to turn 16,039**:
325 turns past the point where the Borg died. Then the provider took longer
than the play mind's 120-second limit and the run ended **`harness_failure`**
— infrastructure, not play, which is why the limit is 240 seconds now and
`--model-timeout` can raise it.

So: it did get past the death, and **nothing about avoiding the death is
proved.** One branch is an anecdote; a run that ends because a provider was
slow is not evidence about the game at all. That is what mode C is for — N of
M trials from the same turn — and what the record says: the facts
(`survived_past_the_death`, `died_again`, `same_cause`) are recorded, and the
conclusion is not drawn.

The gate, with the scripted mind instead of a model, passes in 119 seconds:
the Borg's death reproduces from the seed (same trace hash, same cause, same
turn), the agent takes over 200 turns before it, and the post-mortem
**verifies** — the prefix replays by being played again, and the recorded
actions replay from the handover.

## What is not here yet

- **No probe (mode C)**, so a post-mortem's result cannot yet be counted into
  a `quantified` claim. One branch is one anecdote.
- **No consolidation of a post-mortem.** `consolidate --run` works on any run
  directory, including one of these, but the pack does not know that a
  post-mortem is a comparison; it would describe the branch rather than the
  difference.
- Nothing reads `docs/deaths/` yet. It is the obvious source for the questions
  a post-mortem should ask, and for comparing what the Borg's own investigators
  concluded with what the agent finds.
