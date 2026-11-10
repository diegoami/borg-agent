# The death replay analyser: specification

The owner, 2026-11-09, pivoting the repository:

> *"what we could build is a tool that using the knowledge of the game could
> analyze death replays and produce leads of what could be improved in a
> situation… the output would be leads, not certainty, of what a borg might
> want to improve. No more playing."*
>
> *"in the end we do not need even external LLM keys, we would just build a
> skill, with fixed context containing the rules of game, strategic manual and
> so on, and we could evaluate a borg replay and return a diagnostic
> automatically, for the borg reborn to reuse."*

This is what to build. It replaces [PLAY-SPEC.md](PLAY-SPEC.md), which was
written for an agent that plays; nothing in it is needed for this.

## The shape

Two pieces, and the split is the point.

| Piece | What it is | Needs a model? |
|---|---|---|
| **The extractor** | Python in this repository: a death's artefacts in, a **feature report** out — facts, counts and timelines, no judgement | **no** |
| **The skill** | a packaged set of instructions with fixed, pinned context — the game's rules, the manuals, the Borg's specification, the corpus conventions — that turns a feature report into **leads** | it is *run by* whatever session loads it (Claude Code, the owner's harness). **No API key, no `models.yaml`, no budget** |

The extractor is testable and deterministic: the same death gives the same
report, byte for byte. The skill is where reading and judgement live, and it
leaves its reasoning in the diagnostic it writes.

**What this deletes**: the `api` mind, `models.yaml`'s play job, budgets, the
model trial (T09), the pilot (T10), and mode A playing. **What it keeps**: the
bridge and `branch` (to *test* a lead by replaying from a turn), `verify`, mode
C probes, the claim lifecycle, the knowledge store, and the run report.

## What a death already gives us

Researched at the pins, 2026-11-09. Three sources, and they are richer than
expected.

### 1. better-borg-c's curated corpus — `docs/deaths/` at the game pin

Thirteen cases, ten distinct starting conditions, 21 death-process attempts.
Per case:

| File | Holds |
|---|---|
| `record.json` | `better-borg-c/death-record@1`: the id, the raw cause, the encounter family, and every **attempt** with its build identity, binary hash, source commit, carried patches (with their issues and credits) and calendar |
| `assessment.json` | the human verdict: `classification`, `cause_category`, `confidence`, **`findings`** (each a status and a summary) and **`actions`** — the leads, keyed, with their issue and status — plus owner `feedback` quoted verbatim |
| `events.log` | **the Borg's own reasoning**, line by line, interleaved with the game's messages |
| `snapshots/T-minus-N.{txt,json}` | the screen and the **whole state** at 5, 12, 25, 40, 60, 82, 105 turns before death: gear with quantities and timeouts, depth, decisions, RNG, and `diagnostics.borg` — `fleeing`, `fleeing_to_town`, `leaving`, `avoidance` |
| `input.txt` | the key script, so the death is reproducible |
| `report.md`, `terminal.map.txt` | the write-up and the final map |

`index.json` aggregates the cases, and its **36 action keys** are what leads
look like when a person writes them: `phase-door-first-choice`,
`escape-stock-trajectory`, `clw-tier`, `excessive-danger-guard`,
`heal-eligibility`, `starvation-emergency`, `worm-scary-rule`, `weapon-swap`,
`quiver-full-pickup`, `recall-retention`, `theft-danger-weight`…

`tools/aggregate-deaths.py` only **collects** those hand-written actions into
the index. **Nothing generates them.** That is the gap this tool fills: it
proposes what a person currently writes by hand, with the evidence attached.

### 2. The Borg's own notes, in any trace we or the zoo produce

The observer copies every `borg_note` into the trace, so a death we replay
ourselves carries the same stream — **1,563 note lines** in our seed-3 death.
They are regular enough to parse:

| Note | What it gives |
|---|---|
| `# Loc:35,53 Dep:1 Lev:1 HP:9/13 SP:2/2 Danger:p=36` | position, depth, level, hit points, mana and **the Borg's own danger estimate**, periodically |
| `# Fleeing and leaving the level. (scaryguy)` | its **intent**, and why |
| `# Flowing toward stairs at cost 51` | its pathing target and the cost it accepted |
| `# Backing up to 54,34 (11 > 0)` | a retreat with its numbers |
| `# Scary guy on level.` / `# Removing Regional Fear (x,y) because of a LOS giant white ant` | the flags driving it |
| `# Performing attack type 1 with value 34.` | the attack it chose and what it valued it at |
| `# Facing giant white ant at (35,54) who has 14 Hit Points.` | the target and its true hit points |
| `# Attacking with weapon 'Whip (1d3) (+0,+0)'` | the weapon, with its dice |
| `# HIT_BY:The small kobold (3)` / `# MISS:the giant white ant (2)` | the exchange, blow by blow |
| `# FEELING_DANGER:18 (+)` | the level feeling it acted on |

### 3. The zoo's cells — `borg-zoo` at its pin

Per run: outcome, cause, the final state, `first_turn_at_depth`, the play hash,
the effective settings, the build identity. Not a timeline, but the **cohort**:
how often this cause kills, at what depth, on which specimen. A lead that is
true in one death and never in two thousand runs is a different lead.

## The extractor: what it computes

Input: a case directory, a trace, or a run directory of ours. Output: one
`death-features@1` document. Every feature names where it came from, and
nothing in here is a judgement.

1. **Identity and honesty checks, first, because they can void everything
   else.** Build, source commit, carried patches, seed, birth, and the
   **effective settings** from the trace's own options line. If a forbidden
   mode was in effect — munchkin, lunal — the report says so at the top and
   every survival-shaped feature is marked not comparable with ordinary play.
   *(This is not hypothetical: every Borg run this repository made before
   2026-11-09 was a munchkin run, because the milestone 8 tree defaults
   munchkin on and our settings file said nothing. T34.)*
2. **The death**: cause, the killing blow, the turn, the depth, the character's
   level, and the last ten exchanges from `HIT_BY`/`MISS`.
3. **The hit-point trajectory**: every drop with its turn, the deepest drop,
   and the window in which the character lost half its hit points.
4. **The Borg's danger estimate against what happened**: its `Danger:p=` over
   time beside the damage actually taken in the next N turns. A systematic gap
   is the most mechanical lead there is.
5. **Intent against outcome**: every stated intent (`Fleeing`, `Flowing toward
   stairs at cost 51`, `Backing up`) with how long it was held and whether it
   was achieved. *"It intended to leave the level for 40 turns and never
   left"* is a feature, not an opinion.
6. **The fight it chose**: the weapon and its dice, the target's hit points,
   the expected rounds to kill, the damage taken per round, and therefore
   whether the fight was winnable at the time it was entered.
7. **Escape stock over time**, from the snapshots' gear: Phase Door, Cure Light
   Wounds, Teleport, food, and when each was spent or absent. With the shop
   purchases from the messages, this is the `survival-stock-priority` lead
   whenever the gold went elsewhere.
8. **Status windows**: paralysis, confusion, fear, poison, blindness — when
   they began, how long they held, and what was adjacent while they did.
9. **Triggers**: traps sprung, a siren, aggravation, a level feeling acted on.
10. **The situation at T-minus-N** for each snapshot: what was in sight, what
    was reachable, which stairs were known and at what flow cost.

## The skill: what it reads and what it must not do

A skill directory, versioned here, with **fixed context pinned by commit**:

| Context | Source |
|---|---|
| the game's rules and commands | the `manual` paths at the game pin |
| the strategy manual, including chapter 15's machine-oriented rules | `docs/c-manual/` at the `borg-spec` pin |
| the Borg's specification | `docs/c-borg/BORG_SPEC.md` at the same pin |
| the Borg's own source for the mechanism under suspicion | `src/borg/` at the game pin |
| the corpus conventions | `docs/deaths/README.md`, `REVIEW-TEMPLATE.md`, the 36 existing action keys |
| the Rust remake, to say whether a lead is already taken | `borg-rs` at its pin |

Its procedure: read the feature report, not the raw logs first; name the
mechanism each feature implicates, in the Borg's own vocabulary; propose leads;
for each, cite the evidence and the source site; and say what would settle it.

Three rules it is held to, carried over from the knowledge base:

- **A lead is a lead.** It enters as `hypothesis`, never as a fact (R4.3), and
  the word "defect" is not used without a counted trial or a reproduced
  comparison.
- **It never promotes its own lead.** A probe, a branch comparison or a review
  by another family does that (RULES 13).
- **It cites or it is silent.** Every claim in a diagnostic points at a file,
  a turn and a line. A lead with no evidence pointer is dropped.

## The output: `lead@1`

One diagnostic document per death, and a lead looks like this:

```json
{
  "schema": "borg-agent/lead@1",
  "id": "D0013-flee-before-retreat",
  "statement": "At danger 400 the Borg read its only Phase Door instead of stepping one square back, which would have left the stationary eye's reach.",
  "status": "hypothesis",
  "mechanism": {"area": "escape-order",
                "source": "src/borg/borg-escape.c",
                "borg_rule": "caution evaluates escape before retreat"},
  "evidence": [{"kind": "note", "turn": 3571, "line": "# Fleeing (excessive danger) danger400"},
               {"kind": "snapshot", "turn": 3571, "file": "snapshots/recorded-T-minus-105.json",
                "shows": "one Phase Door, no Cure Light Wounds"}],
  "how_to_test": {"kind": "branch", "from_turn": 3651,
                  "instead": "step to (56,41) rather than reading Phase Door",
                  "expected_if_true": "the eye cannot reach; the scroll is kept for the kobold"},
  "already_in_the_remake": false,
  "confidence": "one death; the ordering is read from the source, not measured"
}
```

`how_to_test` is the part that makes this repository the right home for the
tool: **`branch` and the probes already exist**, so a lead can be turned into a
reproduced comparison with the machinery that is already tested. The owner did
exactly this by hand for D0013 — a verified manual branch from turn 3651 — and
that is the loop to automate.

The diagnostic is written for the Borg reborn to consume: leads keyed the way
`index.json`'s actions are keyed, so they can be filed, rejected or carried
across to `borg-rs`.

## What we should learn from the corpus before trusting any of it

The 36 existing action keys are a **validation set**. Run the extractor and the
skill over the thirteen curated cases and ask: of the leads a person wrote, how
many does the tool propose, and what does it propose that nobody wrote? That is
the measure of the tool, and it needs no model keys and no new play.

## Open questions for the owner

1. **Where does the skill live?** In this repository (versioned with the
   extractor, which is the honest pairing), or in the owner's skills directory
   so any session has it? Recommendation: **here**, with a one-line pointer
   wherever skills are kept.
2. **Does the tool ever run the game?** It does not need to for the extractor,
   but a lead's `how_to_test` wants `branch`, which plays. Recommendation:
   extract without playing; **play only to test a lead**, and mark such runs as
   what they are.
3. **The corpus is thirteen cases of a munchkin-mode Borg?** The corpus's own
   runs predate our discovery; their settings lines will say. Worth checking
   before leads are drawn from them.
4. **Do we keep mode A at all?** The requirements' phase 1 is a player-learner.
   This pivot makes the Borg's own deaths the source of knowledge, which is
   closer to phase 2 (the archaeologist). Recommendation: say so in the
   requirements rather than leaving two plans in the repository.
5. **What happens to `models.yaml` and the api mind?** They work and are
   tested. Recommendation: keep the code, mark the trial and pilot as not
   started, and remove the keys from the documented path so nothing needs a
   provider.
