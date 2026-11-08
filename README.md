# borg-agent

An agent that plays Angband through the C Borg's connection, with a language
model choosing what to do in place of the Borg's hand-written rules, and
writes down what it learns.

**Knowledge is the product, not winning.** The knowledge base is a set of
claims about the game, each with its evidence and a replayable run behind
it. A later Rust Borg, the "Borg reborn", is to be built from it.

- [Requirements](docs/REQUIREMENTS.md): what this repository must do, and
  the owner's decisions.
- [Plan](PLAN.md): the milestones and their tasks, with status.
- [Sources](docs/SOURCES.md): what the playing agent may read, and what the
  developer must keep out of it.
- [Handover](docs/HANDOVER.md): where the work stands, for the next session.
- [Building and playing](docs/BUILD-AND-PLAY.md): the pinned game headless,
  and how a run is checked for determinism.
- [models.yaml](models.yaml): which model does which job, by profile. It is
  the only model rule here, and holds no keys.
- [Schemas](docs/SCHEMAS.md): the observation, action, run record and claim.
- [The bridge](docs/BRIDGE.md): how an agent gets the Borg's hands and eyes.

## Status

Initialized on 2026-11-08. T01 builds the pinned game headless and plays it
with the stock Borg; see [building and playing](docs/BUILD-AND-PLAY.md). The
bridge that gives the game's input to an agent (T03) is not written yet.

## Related repositories

- [borg-zoo](https://github.com/diegoami/borg-zoo): measures Borg versions on
  seed suites; it will import this agent's runs.
- [better-borg-c](https://github.com/diegoami/better-borg-c): the C game and
  Borg the bridge attaches to.
- [game-archaeologist](https://github.com/diegoami/game-archaeologist): the
  claim lifecycle the knowledge base follows.
- [Squire](https://github.com/neostryder/neo-angband-mod-squire): a Neo
  Angband mod that asks a model what to do; prior art for the mind and
  executor split.
