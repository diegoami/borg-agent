# Sources: what each role may read

The owner's decision of 2026-11-08 (requirements, **D8**): **the playing agent
may read whatever helps it build the knowledge base** — the manual, the game
source, the Borg source and its documentation, the Borg specification, the
open issues, the recorded deaths, the zoo's results and its own play. The
earlier rule here, that phase 1 saw only the manual, was not the owner's
intent and is withdrawn.

What the manual is, is **required**: the agent has to know the keys and the
commands before anything else can work.

The point of this repository is to play, and to grow a knowledge base that
the Borg reborn can be built from. A fact that comes from the Borg's source
or from the spec is as welcome as one the agent learned by dying, as long as
the record says which it was.

## The playing agent

| May read | Where it is |
|---|---|
| **the manual** (required) | the `manual` paths in [pins.json](../pins.json), at the `better-borg-c` pin: the game's own "Getting Started" and "The Manual" pages, and the in-game help |
| what the game shows during play | the observation (R1), monster recall and object descriptions as the game prints them |
| the game source, including `lib/gamedata/` and `docs/hacking/` | the `better-borg-c` pin, or the `original` pin for the unmodified C Borg |
| the Borg source and its documentation | the same pins (`src/borg/`, `docs/hacking/borg.rst`) |
| the Borg specification | the `borg-spec` pin: `docs/c-borg/BORG_SPEC.md` in diegoami/neo-angband-tracker |
| the strategy manual | the `borg-spec` pin: `docs/c-manual/` — 17 chapters, ten appendices generated from `lib/gamedata/`, and a copy of the official user manual. **Chapter 15, "notes for the borg", is a machine-oriented distillation** with rule ids, thresholds, sources and confidence; it says of itself that its rules are a starting policy to be measured, not truths, which is exactly how a claim from it must enter: `static:strategy-manual`, never `documented` |
| the Rust remake, as it stands | the `borg-rs` pin: 59 Borg modules under `borg-rs/src/`, its docs and its harness. This is the Borg reborn the knowledge is for. The pin moves as the remake does; a claim says **which side of the port and which milestone** it is about, because the two sides are not always on the same one |
| **the user manual** | the `c-borg-reference` pin: `docs/user-manual.md`, a single-file manual of the whole game (about 3,700 lines: commands in both keysets, birth, stores, objects, combat, magic, every spell list, options, the Borg's commands and `borg.txt`). Added at the owner's request, 2026-11-09; see below |
| **the online command reference** | <https://angband.readthedocs.io/en/latest/command.html>, the upstream rendering of `docs/command.rst`. Added at the owner's request, 2026-11-09. Read it at a pin: on that date angband/angband's `master` stood at `e473720` (the `original` pin), and `docs/command.rst` is byte-identical there and at the `better-borg-c` pin, so a claim cites that file as `manual`, not the moving URL |
| the recorded deaths | `docs/deaths/` at the `better-borg-c` pin (nine cases there; more on its `main`) |
| the open issues of the related repositories | the trackers themselves; a claim records the issue number and the date it was read |
| the zoo's results | the `borg-zoo` pin and its results branch |
| its own knowledge base | the claims and notes under `knowledge/` |

Nothing on that list is forbidden. Two things are still asked of it:

1. **Provenance.** Every claim says which sources produced it (R4). A claim
   read out of the Borg's source is marked `static:borg-source`, not
   `observed`; a claim from the zoo's results says so. That is what lets
   phase 3 tell "the Borg believes this" from "the game does this".
2. **Honesty about what was checked.** Reading something in the source is not
   the same as seeing it happen. A claim's basis says which it is, and a
   `quantified` claim still needs its counted trials.

### The strategy manual and the user manual: what they are and how far to trust them

- The strategy manual is `docs/c-manual/` at the `borg-spec` pin: seventeen
  chapters, ten appendices and a copy of the official user manual. Until
  2026-11-09 this source was `docs/strategy/` on the `c-borg-reference`
  branch — an index, six appendices and eight chapters that did not exist.
  That directory is gone from master; this is the same work finished, and it
  is what the agent reads now.
- Its **appendices are generated** from `lib/gamedata/`, which is
  byte-identical at the `c-borg-reference`, `better-borg-c` and `original`
  pins (a test checks it). So a table there describes the game we play, as far
  as the generator reads the data right.
- Its **prose was written by a model**, and it says so: chapter 15, the
  machine-oriented distillation for a borg, calls its own rules "a starting
  policy to be measured, not truths", and its constants tunables. That is
  precisely how a claim from it enters — as a hypothesis with a
  `static:strategy-manual` basis — so the manual and the claim lifecycle agree
  about their own standing.
- Its copy of the official user manual (`docs/c-manual/user-manual/`) is not a
  separate source: the game's own manual at the game pin is the authority, and
  that is what `manual` names.
- **The user manual** (`docs/user-manual.md`, same pin) was also written by a
  model the same day, from the branch's `src/`, `lib/gamedata/` and `docs/`;
  its tables were extracted from `lib/gamedata/`. Where it and the game's own
  manual (the `manual` paths) disagree, the game's manual wins and the
  disagreement is worth a note. A spot-check of its key table against
  `docs/command.rst` found them in agreement.
- Neither is **the manual**. A claim read in one has the basis
  `static:strategy-manual` or `static:user-manual` and the matching source
  name, and it never makes a claim `documented`. Where a number matters, check it against
  `lib/gamedata/` or `src/` at the game pin and add `game-source`.

## What is still kept apart

- **A model never promotes its own claim past `hypothesis`** (R4.3). That is
  unchanged, and it is about review, not about reading.
- **The executor's primitives stay mechanical** (R2): pathing, resting until a
  condition, taking stairs, following a shop list. The developer does not
  hard-code the Borg's danger estimates, flee thresholds or item valuations
  into them, because choosing between primitives is the mind's job and the
  point is to find out what the mind decides. Reading the Borg's code to
  understand it is fine; copying its tactics into the plumbing hides the
  thing being measured.
- **The model trial's answer key** (T09) never enters a prompt or the
  knowledge base: a candidate must not be able to read the quiz's answers.
  That is test hygiene, not a source rule.

## The developer, and later phases

A session working on this repository may read everything public. The phases
of the requirements still describe **what each phase produces** — game
knowledge, design records, then the remake's specification — but they are no
longer a rule about what may be read.
