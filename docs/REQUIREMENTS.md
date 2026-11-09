# borg-agent: requirements

Approved by the owner on 2026-11-08, together with the five decisions at the
end, when they created this repository. Changes go through a PR the owner
merges.

## Purpose

borg-agent plays Angband with a language model, or another learned policy, in
place of the Borg's hand-written rules. **Its product is knowledge, not
wins.** It writes down what it learns about the game in a form that a person
can review, an experiment can check, and a later Rust Borg (the "Borg reborn")
can be built from.

It is a step towards the remake described in the Tunable Borg Plan
([neo-angband-tracker `docs/c-borg/TUNABLE-BORG-PLAN.md`](https://github.com/diegoami/neo-angband-tracker/blob/master/docs/c-borg/TUNABLE-BORG-PLAN.md)). The owner's
decisions for the remake apply here too:
- no munchkin mode;
- no lunal mode;
- strategy differs by class, possibly with a separate Borg per class;
- a deep dive is preferred to level scumming, so knowing when a character is
  ready to go deeper matters more than knowing how to farm a level.

What it is not:
- not a Borg replacement: nothing it plays has to be fast or cheap enough for
  everyday use;
- not Squire. Squire, the Neo Angband mod, imitates a player and keeps them
  company. borg-agent explores and runs experiments. Squire is prior art for
  how to ask a model at "the moments that matter"; borg-agent doesn't depend
  on it.

## Phases

| Phase | Agent | Reads | Writes |
|---|---|---|---|
| 1 | **Player-learner** | the manual and the in-game help (required), its own play, and — decision D8 — the game source, the Borg source and its documentation, the Borg specification, the recorded deaths, the open issues and the zoo's results | game knowledge: facts, dangers, tactics, readiness by class |
| 2 | **Borg archaeologist** | the C Borg source (4.2.6 original and the better-borg-c milestones), its history and comments, the zoo's results | design records: what each Borg mechanism does, and why |
| 3 | **Reconciler** | the outputs of phases 1 and 2 | the remake's specification: what to keep, change or drop, and the evidence for each |

The phases say **what each one produces**, not what it may read (decision
D8, 2026-11-08). Phase 1 plays and writes down what it learns about the game;
phase 2 describes the Borg's mechanisms; phase 3 reconciles them into the
remake's specification. Every record says which phase and which sources
produced it, and a claim's basis says whether it was read in the source
(`static:game-source`, `static:borg-source`) or seen in play (`observed`,
`quantified`) — that distinction is what phase 3 needs, and it is carried by
the record rather than by a wall between the phases.

These requirements cover phase 1 in detail. Phases 2 and 3 are sketched at
the end, and get their own requirements once phase 1 has produced knowledge.

## R1. Connector: the Borg's view and the Borg's hands

The agent sees what the Borg sees and acts the way the Borg acts. Then
anything it learns can be expressed in the inputs and outputs a Rust Borg will
have.

The C Borg's connection, in better-borg-c's `src/borg`:
- **acting:** it supplies keypresses through the game's `inkey_hack` hook
  (`borg.c`);
- **seeing:** it reads the player's knowledge of the map (`map_info`,
  `player->cave`), the screen text and the message stream (`borg-io.c`,
  `borg-messages.c`) and the character state (`borg-trait.c`). A few reads of
  the true map remain (for example in `borg-commands.c` and
  `borg-think-dungeon.c`).

Requirements:
1. **One observation schema, versioned**, whatever the engine. It is
   structured JSON: map as known, visible monsters, inventory and equipment,
   character state, messages since the last observation, shop stock when in a
   shop, and the open prompt or menu. It contains only what the player could
   know. Any field that comes from the true game state is named so, and is
   off by default.
2. **One action schema:** game commands with their arguments (walk 6, cast
   b at target, buy item 3 ×5), translated to keys by the connector. Raw keys
   are allowed as an escape hatch and are logged as such.
3. **The game waits for the agent.** No game time passes while the model
   thinks. Wall time never affects play.
4. **Deterministic given the inputs.** Seed, birth choices, settings and the
   recorded action stream reproduce the game exactly. Only the agent's
   choices are non-deterministic, and they are recorded.
5. **Adapters**, one per engine, behind the same schemas:
   - **C 4.2.6**, through a bridge on the Borg's own hook in the better-borg-c
     tree. It may reuse the Borg's own map and state-reading code to fill the
     observation.
   - **Neo Angband**, through the headless Core that Mandos's
     `tools/zoo-run.mjs` uses, with the player-knowledge view that Squire and
     Mandos read. Its `controller.markNondeterministic()` marks such runs.

   C 4.2.6 comes first (owner decision D1); Neo is a later milestone.
6. **Birth:** assigned race and class, ordinary birth otherwise, with the
   game's default birth options. No munchkin start and no lunal mode.

## R2. Playing: deciding at the moments that matter

A model can't choose every keypress: a 100,000-turn game is about 10,000
player turns at normal speed. Play has three layers:
1. **Executor:** scripted, deterministic primitives that run until something
   changes: walk to, explore the floor, fight the nearest monster, rest until
   healed, take the stairs, flee by stairs or Phase Door, read an unknown
   scroll, shop a list. They report why they stopped.
2. **Mind:** the model, asked when the executor stops or something new
   happens: a new monster, low HP, a level feeling, a new item, a shop, a
   prompt. It chooses the next primitive or a single command, and gives a
   one-line reason.
3. **Notebook:** after each event that taught something (a death, a near
   death, a first meeting, a surprise), the agent writes an observation note
   with the turn it refers to.

Requirements:
1. Per run, record every model call: the observation hash, the prompt-pack
   version, the model, the provider, the effort setting, the reply, the
   reason, and the tokens and time used.
2. Retrieve relevant knowledge into each prompt, within the context size the
   active profile gives for that job (`context_k` in `models.yaml`, with a
   default when it is missing). A run reports what it spent: calls, tokens and
   cost (decision D10).
3. Each run has a budget of model calls and tokens. Hitting it is an outcome,
   `budget_cap`, not a failure.
4. Models come from the active profile in `models.yaml`, and from nothing
   else (decision D7), locally and in a cloud session alike. A profile names
   one model per job: `play`, `consolidate` and `review`, with `review` of a
   different family from `consolidate` (R4.3). The active profile is the
   first of `BORG_AGENT_PROFILE`, `profile:` in the git-ignored
   `models.local.yaml`, and `default_profile`. Keys are read at run time from
   the environment variable each provider names; the file holds no key, and a
   missing variable fails before play, naming the variable and never its
   value. Every run record names, per job, the profile, the provider, the
   model and the family, how they were chosen (`profile`, `local override` or
   `environment`), and the SHA-256 of `models.yaml` and of
   `models.local.yaml` when it exists — never a key, a request header or a
   URL with credentials. Prompts carry public game content and game state
   only, so free models may play; they must not get the repository's private
   material, if it has any.

## R3. Modes of learning

| Mode | What it does | Why |
|---|---|---|
| **A. Play** | full games from birth, by class | broad knowledge, and survival figures for the zoo |
| **B. Post-mortem** | takes a recorded Borg death from the zoo or a recording, replays it to some turns before the death, explains what happened, then branches to try alternatives | the zoo has thousands of deaths with causes; this is the cheapest knowledge per model call |
| **C. Probe** | answers one question with a controlled experiment, for example "can a level-1 Warrior melee a floating eye?", as N of M trials | turns a hypothesis into a counted result |
| **D. Consolidate** | merges notes into claims, finds contradictions, and proposes questions for mode C | keeps the knowledge base small and true |

Mode B's first questions come from the zoo: floating eyes killed 4 of 13
Mandos characters in `mandos-classes-18`, and Druids die far more often than
Paladins on `classes-1800`.

Probes may set up a scenario with debug commands (a given depth, gear or
monster). Such runs are marked as interventions and never count in survival
figures (owner decision D4).

## R4. Knowledge records

The knowledge base is the product. It follows the claim lifecycle of
[game-archaeologist](https://github.com/diegoami/game-archaeologist) ([ADR-007](https://github.com/diegoami/game-archaeologist/blob/main/docs/adr/007-evidence-provenance.md) and [ADR-008](https://github.com/diegoami/game-archaeologist/blob/main/docs/adr/008-claim-lifecycle.md)), adapted to a game whose source is
available.

Each **claim** has:
- an id, and one plain statement;
- its **area**: monster, item, spell, class, race, town, dungeon, mechanic,
  danger, tactic or readiness;
- its **scope**: class, race, character level, depth, gear, engine and
  version;
- its **status**: `unknown`, `documented` (the manual says so), `hypothesis`,
  `supported`, `corroborated`, `refuted`, `contested`, plus `superseded-by`;
- its **basis**: `manual`, `observed`, `quantified N of M`, `intervened`,
  `static:game-source`, `static:borg-source`, `static:borg-spec`,
  `static:deaths` or `static:issue` — in any phase (decision D8), since what
  matters is that the record says which;
- its **evidence**: run ids, seeds and turns, each one replayable (R5);
- a **confidence** line in words: what the claim rests on, and which
  alternative explanations were ruled out;
- for a tactic or a readiness claim, **how a program would test it**: the
  zoo experiment or probe that would confirm or refute it;
- the phase and sources that produced it.

Requirements:
1. Raw run records are immutable. Claims point to them; they never edit
   them.
2. Claims live in git as JSON Lines, with a generated Markdown view per area
   that a person can read without tools.
3. The model never promotes its own claim past `hypothesis`. A probe result
   (`quantified`) or a review by a different model family moves it on, and
   the owner decides what becomes part of the specification.
4. Each claim says which engine it was learned on. A claim learned on Neo
   isn't assumed to hold on C until it is checked there.

## R5. Records and replay

Like better-borg-c and borg-rs, every run can be replayed exactly, without
the model, because the engine is deterministic given the recorded actions.

The tools:
- **verify:** rerun the action stream from birth and confirm the same states
  and outcome;
- **view:** show the screen at turn T;
- **dump:** write the observation at turn T;
- **branch:** play on from turn T with a different agent, prompt, model or
  Borg (this is what mode B uses);
- **explain:** show the model calls and notes around turn T.

Run records follow the zoo's outcome vocabulary: `death` with its cause,
`turn_cap`, `stalled`, `borg_stopped` (here "agent stopped", with the
reason), `decision_cap`, `budget_cap` and `harness_failure`. They also carry
the provenance the zoo already records for the Borgs (commit, dirty state,
engine and content identity, settings), plus the model, prompt-pack and
knowledge-base hashes.

Large logs (observations and model replies) go to release assets or another
store, addressed by hash. Only claims, run summaries and hashes go into git.

## R6. Zoo integration, without determinism

The zoo (diegoami/borg-zoo) adds a harness kind for the agent in its own PR,
as it did for Mandos.
1. The agent plays on the owner's machine, or a runner with model access.
   The zoo imports its run records.
2. The zoo's CI **replays each imported run** from its action stream and
   confirms the recorded outcome. CI checks the record, not the agent, and
   needs no model.
3. Agent runs are marked `deterministic: false`. Seeds are still paired with
   the Borgs' runs, since the same seed gives the same starting game. But the
   zoo never reports two agent runs as "identical games", and never treats
   one agent run as a fixed property of the agent. A subset of seeds is run
   twice to measure how much the agent varies.
4. Suites are small to begin with (`classes-18`, then perhaps 180 seeds) and
   use the same caps as the Borg suites.
5. Agent results go on a page of their own. They don't appear on the landing
   page until the owner says so.

## R7. Repository and process

- Its own repository, with AGENTS.md, RULES.md and PLAN.md. It reuses
  game-archaeologist's claim lifecycle and review rule but does not adopt
  harness_imperial (owner decision D5).
- No AI attribution trailers in commits or PR bodies.
- Merges happen only when the owner asks.
- No posts to angband/angband or other upstream forums.
- Original game files are not committed: it builds the pinned engine sources
  the way the zoo does.
- Tests: the schemas, the replay round trip (play, then verify, gives the
  same outcome), and the executor primitives on fixed fixtures.

## Phase 2 and 3, in outline

**Borg archaeologist** (phase 2): for each Borg mechanism (danger
estimation, the flow and pathing families, fighting and defence, escapes,
item power and swaps, shopping, the depth and readiness checks, and the
class code), it writes a design record:
- what the mechanism does, with code references at a pinned commit;
- the documented intent (comments, Borg docs, commit messages), kept apart
  from the inferred intent, which is labelled as such;
- the zoo evidence for and against it (deaths, bisects, confirmations such
  as the M5/M6 warrior work);
- known defects.

**Reconciler** (phase 3): it compares phase 1's game knowledge with phase 2's
design records:
- where the Borg agrees with what the learner found;
- where the Borg relies on something the learner refuted;
- what the learner found that the Borg ignores.

Its output is the remake's specification by class, each item with its
evidence and the experiment that tests it.

## Owner decisions

All five were accepted as recommended on 2026-11-08.

| # | Decision | Accepted |
|---|---|---|
| D1 | First engine: C 4.2.6 or Neo | **C 4.2.6.** The Rust remake will play the C game. The Borg's own state-reading code fills the observation in the Borg's own terms, and the replay tools exist. Neo second: Squire and Mandos have already done the structured view. |
| D2 | Phase 1 sources: the manual only, or the manual plus public spoilers | **The manual and the in-game help only**, as you described. Spoilers come in phase 2. *Superseded on 2026-11-08 by D8: the playing agent may read the game and Borg source, the specification, the issues, the deaths and the zoo's results as well. The manual stays required.* |
| D3 | Where agent runs execute | **Locally** (the owner's machine) **or in a cloud session**; either way the models come from the active profile in `models.yaml` and the keys from the environment variables it names (amended 2026-11-08; see D7). The zoo imports the runs and verifies them by replay in CI. |
| D4 | Debug-set probe scenarios | **Allowed, marked as interventions,** and kept out of survival figures. |
| D5 | Adopt harness_imperial and the game-archaeologist method formally | **Reuse the claim lifecycle and the review rule now.** Adopt the harness only if the repository gets several agents working at once. |

D6 is reserved: it records which model does which job, once the model trial
(PLAN.md T09) has measured the candidates. Added on 2026-11-08:

| # | Decision | Decided |
|---|---|---|
| D8 | What the playing agent may read | **Whatever helps it build the knowledge base**: the manual and the in-game help (required, so it knows the keys and commands), its own play, the game source including `lib/gamedata/` and `docs/hacking/`, the Borg source and its documentation, the Borg specification ([neo-angband-tracker `docs/c-borg/BORG_SPEC.md`](https://github.com/diegoami/neo-angband-tracker/blob/master/docs/c-borg/BORG_SPEC.md)), the recorded deaths ([better-borg-c `docs/deaths/`](https://github.com/diegoami/better-borg-c/tree/main/docs/deaths)), the open issues and the zoo's results. This supersedes D2 and the earlier rule in docs/SOURCES.md, which was not the owner's intent. What is asked instead is **provenance**: every claim names its sources and says whether it was read or seen. The purpose of the repository is to play and to grow the knowledge base the Borg reborn is built from. |
| D9 | The game's seasonal window | **Leave play as the game plays it.** The game admits seasonal monsters on 24-26 December, so a seed plays a different game on those days. Every run records `calendar.seasonal`, and `verify` refuses to compare a run with a replay on the other side of that window. There is **no RULES 9 exception**: the instrumented build never diverges from the unpatched game, not even for three days a year. The price is accepted: a run made inside the window can only be replayed on a day of the same kind. (2026-11-09) |
| D10 | Real model calls before the trial | **Allowed, in small runs.** Milestone 3 may call a real model on the active profile to prove the `api` mind works — short games, a few hundred calls — and every PR that does reports the calls, tokens and what they cost. Spending at the scale of the model trial (T09) or the pilot (T10) still waits for the owner. (2026-11-09) |
| D7 | How models are configured | **By profile, in `models.yaml` at the root.** It holds the providers, the models per job and named profiles, and never a key; a provider names the environment variable that holds its key. Switching profile is one line: `BORG_AGENT_PROFILE`, or `profile:` in the git-ignored `models.local.yaml`, else `default_profile`. This replaces the `BORG_AGENT_BASE_URL`, `BORG_AGENT_API_KEY` and `BORG_AGENT_MODEL` variables and the planned `providers.json`. **The profile is the only model rule in this repository**: the owner's general model rule, which asks their local quota service (quota-tracker) for a recommendation, does not apply here, and this repository does not use that service, locally or in the cloud. |
