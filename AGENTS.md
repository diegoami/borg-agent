# Agent entry

This file is for any session that works on this repository: a cloud
session, a local one, or a different model. Read it first, then:
1. [RULES.md](RULES.md);
2. [docs/HANDOVER.md](docs/HANDOVER.md): where the work stands and what the
   last session left;
3. [PLAN.md](PLAN.md): the tasks and their status;
4. [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md): what the repository must
   do, and the owner's decisions;
5. [docs/SOURCES.md](docs/SOURCES.md): what the playing agent may read.

## Starting

```sh
git status --short
git log --oneline -5
bash scripts/setup.sh          # tools check and pinned clones; safe to rerun
pip install -e '.[test]'
python -m pytest -q
```

`scripts/setup.sh` clones the pinned repositories into `vendor/`, which git
ignores, and checks the build tools. In a cloud session it also installs
missing packages. `.claude/settings.json` runs it when a Claude Code session
starts.

## Choosing the work

Take the first task in PLAN.md's status table whose status is `todo`, whose
"Needs" are `done` or in an open PR you can stack on (RULES 5), and which
runs in your kind of session. Set its row to `in progress` with your branch
in your first commit.

At the end of a task:
1. tests pass (`python -m pytest -q`, and the task's own checks);
2. PLAN.md's row and docs/HANDOVER.md are updated: what was done, what was
   found, what is left, and anything the owner has to decide;
3. a PR is open, with what changed, how it was checked, and what was not
   checked.

Then take the next task, or stop if the stack is at three unmerged PRs.

## Cloud sessions

A cloud session has GitHub and the package registries but none of the
owner's local services. In particular:
- **Model access only through the environment.** The owner's quota
  service isn't reachable, so the model rule below can't run. Instead the
  owner configures the cloud environment with:
  - `BORG_AGENT_BASE_URL`: an OpenAI-compatible chat endpoint;
  - `BORG_AGENT_API_KEY`: its key;
  - `BORG_AGENT_MODEL`: the model id;
  - network access to that endpoint's domain (the default allowlist covers
    GitHub and the package registries, not model APIs).

  The model is then the owner's choice. Record it as
  `"chosen_by": "environment"`, with the endpoint's host and the model id.
  Never record or log the key or the request headers.

  With those set, the `api` mind, the model trial (T09) and the pilot
  (T10) can run in a cloud session; the trial needs one set per candidate,
  so the owner configures it as the trial needs. Without
  them, use the `scripted` mind for tests and the `external` mind for
  debugging, and leave real-model runs to the owner's machine with the exact
  commands in the handover.
- **No reviewer from another model family.** Say in the PR that it still
  needs one; the owner arranges it.
- The `gh` CLI may be missing or unauthenticated. All task state is in this
  repository, so nothing depends on issues.

## Local sessions (the owner's machine)

Models for play and for reviews follow the owner's model rule: ask the local
quota service, `curl -s "http://localhost:8765/recommend?tier=light"` for
play decisions and `tier=heavy` for consolidation and hard reviews, use the
`pick` (or `pair` for an implementer and a reviewer), and record the rows
used and their reasons in the run record. Don't choose a model any other
way. Keys come from the environment, which the owner fills from
`~/.config/ai-keys.env`; `providers.json` (T06) maps each provider to its
endpoint and the name of its key variable. If the service doesn't answer, run `systemctl --user restart
quota-tracker` and retry; if it still doesn't, tell the owner.

Heavy local runs take the lock `/tmp/angband-validation.lock` with `flock`,
as the owner's other Angband work does.

## Where things are

| Path | What |
|---|---|
| `pins.json` | the pinned commits of every repository used, and the manual files |
| `scripts/setup.sh` | tools check and pinned clones into `vendor/` |
| `src/borg_agent/` | the Python package: connector, executor, mind, records, knowledge |
| `bridge/` | the C patch applied to the pinned game tree (from T03) |
| `schemas/` | JSON Schemas (from T02) |
| `knowledge/` | claims, JSON Lines and their Markdown views (from T07) |
| `docs/reports/` | pilot and experiment reports |
| `tests/` | tests; `test_repository.py` keeps pins, plan and docs consistent |
