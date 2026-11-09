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
pip install -e '.[test]'       # no system pip? see below
python -m pytest -q
```

The owner's WSL has no system `pip` and no system pytest, so there make a
virtual environment first and use it for every command:

```sh
uv venv .venv && uv pip install -e '.[test]' --python .venv/bin/python
.venv/bin/python -m pytest -q
```

`python -m pytest -q` leaves out the `slow` tests, which build the pinned
game and play it (a few minutes). Run those with `pytest -m slow`; see
[docs/BUILD-AND-PLAY.md](docs/BUILD-AND-PLAY.md).

`scripts/setup.sh` clones the pinned repositories into `vendor/`, which git
ignores, and checks the build tools. In a cloud session it also installs
missing packages. `.claude/settings.json` runs it when a Claude Code session
starts.

## Choosing the work

PLAN.md's milestone table says which tasks belong to the milestone in
progress. **Work only inside that milestone.** Take the first task of it
whose status is `todo`, whose "Needs" are `done` or in an open PR you can
stack on (RULES 5), and which runs in your kind of session. Set its row to
`in progress` with your branch in your first commit.

At the end of a task:
1. tests pass (`python -m pytest -q`, and the task's own checks);
2. PLAN.md's row and docs/HANDOVER.md are updated: what was done, what was
   found, what is left, and anything the owner has to decide;
3. a PR says what changed, how it was checked and what was not checked;
4. **you merge it yourself** once CI is green (RULES 1) — nothing waits for
   the owner inside a milestone.

Then take the next task of the same milestone.

**When the milestone's last task is merged, stop.** Do not start the next
milestone. Open the review PR instead (RULES 7):

```sh
gh pr create --base reviewed --head main --title "Milestone N review: ..."
```

Its diff is everything since the last review, because `reviewed` stands at
the last reviewed state of `main`. Say in the body what each task delivered,
what was verified, what was not checked and what the owner has to decide, and
give the prompt a reviewer needs. The owner merges that PR; a later session
turns the findings into a task.

## Choosing models

**The models the agent plays and reviews with come from `models.yaml` and the
active profile, and from nothing else** (requirements, decision D7). No
recommendation service, no ranking, no fallback chain: the owner's general
model-choice rule does not apply in this repository.

- `models.yaml`, at the root and committed, holds the providers (base URL and
  the name of the environment variable that holds the key), the models per
  job (`play`, `consolidate`, `review`) in each named profile, and the model
  trial's candidates. **It never holds a key.**
- The active profile is the first of: `BORG_AGENT_PROFILE`; `profile:` in
  `models.local.yaml` at the root, which git ignores and which may also
  override single jobs; `default_profile` in `models.yaml`.
- Keys are read from the environment at run time. A missing variable fails
  before play, naming the variable, never its value. Nothing logs or records
  a key, a request header or a URL with credentials.
- Every run record names, per job, the profile, provider, model and family,
  how they were chosen, and the hashes of the model files.
- The loader and its tests are T06; until then nothing reads this file at
  run time.

This is about the models the **agent** uses. Which model writes the code in a
session, and which reviews a PR, stays with the owner.

## Cloud sessions

A cloud session has GitHub and the package registries but none of the
owner's local services. In particular:
- **A profile and its keys come from the environment.** To run the `api`
  mind, the model trial (T09) or the pilot (T10) there, the owner sets:
  - `BORG_AGENT_PROFILE`, or leaves `default_profile` as it is;
  - the key variables that profile's providers name (`api_key_env`);
  - network access to those providers' domains (the default allowlist covers
    GitHub and the package registries, not model APIs).

  The record then says the profile was chosen by `environment`. Never record
  or log a key or the request headers. Without those variables, use the
  `scripted` mind for tests and the `external` mind for debugging, and leave
  real-model runs to the owner's machine with the exact commands in the
  handover.
- **No reviewer from another model family** for the code. Say in the PR that
  it still needs one; the owner arranges it.
- The `gh` CLI may be missing or unauthenticated. All task state is in this
  repository, so nothing depends on issues.

## Local sessions (the owner's machine)

Switch profile by writing one line in `models.local.yaml` (git-ignored), for
example `profile: openrouter`; the same file may override a single job. The
keys come from the environment, which the owner fills from
`~/.config/ai-keys.env`.

Heavy local runs take the lock `/tmp/angband-validation.lock` with `flock`,
as the owner's other Angband work does. Every run in this repository takes it
itself, so

```sh
.venv/bin/python -m pytest -q -m slow                      # locks itself
flock /tmp/angband-validation.lock .venv/bin/python -m pytest -q -m slow
```

both work: an outer `flock` is detected (the lock is already held by an
ancestor, so the runs inside do not take it again). `BORG_AGENT_NO_LOCK=1`
skips it altogether, and `BORG_AGENT_LOCK` points it at another file. A run
that waits more than ten minutes for the lock gives up and says which process
is holding it, rather than hanging.

## Where things are

| Path | What |
|---|---|
| `pins.json` | the pinned commits of every repository used, and the manual files |
| `models.yaml` | the providers, the models per job and the profiles (no keys) |
| `scripts/setup.sh` | tools check and pinned clones into `vendor/` |
| `src/borg_agent/` | the Python package: connector, executor, mind, records, knowledge |
| `bridge/` | the C patch applied to the pinned game tree (T03); see [docs/BRIDGE.md](docs/BRIDGE.md) |
| `schemas/` | JSON Schemas (from T02) |
| `knowledge/` | claims, JSON Lines and their Markdown views (from T07) |
| `docs/reports/` | pilot and experiment reports |
| `tests/` | tests; `test_repository.py` keeps pins, plan and docs consistent |
