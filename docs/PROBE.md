# Mode C: one question, answered in counted trials

```sh
python -m borg_agent probe --probe probes/floating-eye-melee.yaml          # run it
python -m borg_agent probe --probe floating-eye-melee.yaml --claim         # and file the claim
```

A probe answers **one** question with counted trials (R3, mode C). It is the
only promoter of a claim in this repository that is not another model: nothing
leaves `hypothesis` without counted trials or a review by a different family
(R4.3, RULES 13), and a model may **propose** a probe — mode D already does —
and never score one. The harness writes the result.

## A probe is data

One file per probe under [`probes/`](../probes), validated against
`schemas/probe@1.json`. A new probe is a file, not a patch. It says:

| | |
|---|---|
| `question` | the one question, in a line |
| `statement` | how the answer should be phrased as a claim, when that differs |
| `area`, `scope` | the claim's own vocabulary: what the answer is about, and for whom |
| `setup` | how the situation comes about: `natural` or `intervened`, the turn the agent takes over at, the steps, and what the game must **show** before the action is tried |
| `action`, `control` | the two things to try, each an executor primitive or a single command |
| `trials` | the seeds, **declared before the probe runs**, and the game-turn cap per trial |
| `success` | the predicate: `survived`, or `killed_it_and_lived` |

The seeds are in the file and in the result, so a probe cannot be run again
until it gives the answer someone wanted. **A probe file edited after it has a
result is a new probe with a new id.**

## Two kinds of setup

- **`natural`**: the situation is found in deterministic play. The Borg plays
  the prefix to the turn the probe names and the agent takes over, which is
  T08's machinery with a condition instead of a death. Nothing is tampered
  with, so such a trial counts in survival figures.
- **`intervened`**: the situation is built with the game's **own debug
  commands**, driven as keys through the bridge's escape hatch (R1.2) — the
  debug prefix, the command's own letter from the game's debug table
  (`cmd_debug*` in `src/ui-game.c` at the game pin), and the answer to its
  prompt, exactly as a person would type them. Nothing is added to the game or
  the Borg (RULES 9). Decision **D4**: such runs are interventions, marked as
  such, and never count in survival figures.

  The game's own flag is the proof: the first debug command of a character sets
  `player->noscore |= NOSCORE_WIZARD` after asking
  *"Are you sure you want to use the debug commands?"*, which the probe answers
  `y` — and the trial records that it did.

### What the experiment settled

The plan allowed for pushing `CMD_WIZ_SUMMON_NAMED` from the bridge with
`cmd_set_arg_number`, which would have been new C beside the Borg. **It is not
needed.** The debug commands answer to keys, and the sequence is

```
^A j   →  "Are you sure you want to use the debug commands? [y/n]"  →  y
       →  "Jump to level (0-127):"  →  1 ⏎  →  "Choose cave profile? [y/n]"  →  n
^A n   →  "Summon which monster?"  →  Floating eye ⏎
```

so a step is a **list of keypresses, not one string**: the game asks questions
in between, and a key queued behind a question is eaten by it. The probe
answers the debug confirmation `y` and every other question the setup did not
ask for `n` — a level jump offers to choose a cave profile, and a probe that
chose one would be arranging the dungeon as well as the monster.

The bridge needed **one** change: its raw keys now carry a byte above 0x7f and
read a newline as the game's `KC_ENTER` (0x9c). Without it a text prompt could
not be answered at all — the Borg's own `borg_keypresses` passes a signed
`char` to a keycode, so `0x9c` arrives as `0xffffff9c`, and `'\r'` is not Enter
to this game.

## A trial, and a trial that does not count

Every trial is an **ordinary run**: recorded, replayable with `verify`, in the
same outcome vocabulary. A probe result is its trials plus the counts; it
introduces no new kind of evidence.

- The situation is checked before the action is tried (`setup.expect`). A trial
  that never sees it is **`setup_failed`**, counted apart, and never counted as
  a trial the character survived — that would be the easiest way to make a
  probe say what one wants. A probe where every trial fails its setup raises
  rather than reporting 0 of M.
- A trial ends when the game ends it (death, the cap) or when the game
  **reports the monster dead**. Absence proves nothing: a monster out of sight
  is not a monster dead, and the control arm walks away from it on purpose.
- `final_turn` in a run's result is the last *sampled* state, so a short trial
  can report turn 1 for a game that reached turn 109. A trial reports
  `last_turn` from the observations the agent actually saw.

## The result, and the claim

`probes/results/<id>.json` holds the counts per arm (trials, successes, deaths,
and how often the monster died), the setup failures, every trial, and whether
the control arm **isolated the action**. The claim it makes carries
`quantified N of M`, with the status the **harness** sets: `supported` from one
probe, `corroborated` only when a second probe on fresh seeds agrees. Its
review names a trial run the evidence carries, which is what makes a probe
review checkable at all (the milestone 3 review found that an invented probe
review promoted a claim).

## The first probe, and what it showed

[`probes/floating-eye-melee.yaml`](../probes/floating-eye-melee.yaml) asks the
question mode B kept raising: **can a level-1 Human Warrior melee an adjacent
floating eye and live?** Floating eyes killed 4 of 13 Mandos characters in the
zoo's `mandos-classes-18` — which is Neo, through Mandos — and the C side at
this pin had no number at all. Ten declared seeds, two arms, cap 1,200, an
intervention.

| Arm | Survived | The eye died | Deaths |
|---|---|---|---|
| melee it (`fight_nearest`) | **10 of 10** | 10 | 0 |
| explore on (`explore_floor`) | 9 of 10 | 9 | 1 (turn 1,069) |

Three things worth knowing, and the claim says all three:

1. **The eye dies in one or two blows.** Every action trial ended between turn
   109 and 167, a handful of turns after the handover at 100. The paralysis the
   eye is feared for never gets a chance against this class: there is barely a
   fight. That is an answer about a **level-1 Warrior**, not about a Mage.
2. **The control did not isolate the action.** The eye died in 9 of the 10
   control trials too, because `explore_floor` walks into a monster in its
   path and walking into a monster attacks it. So these counts do not separate
   "melee it" from "be next to it"; the claim's `alternatives_ruled_out` says
   **NOT ruled out** in as many words.
3. **Every trial is this harness's assigned birth** — a Human Warrior (R1.6).
   A probe about another class waits for a birth the probe can choose, which is
   why the scope says `class: Warrior` and means it.

## What a probe may not do

- A model never scores a probe, and a probe never scores itself twice: one
  probe gives `supported`.
- The executor's primitives stay mechanical (R2, docs/SOURCES.md). A probe
  chooses between them and sets up the situation; it does not teach them
  tactics.
- A probe's trials are runs like any other, so RULES 9 holds: the game and the
  Borg are unchanged, and with the agent off the trace is the stock Borg's.
