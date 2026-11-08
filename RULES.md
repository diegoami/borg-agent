# Rules

These hold for every session working on this repository, local or cloud.

## Owner

1. The owner merges. A session opens PRs and never merges, even when it has
   the rights to.
2. Scope comes from [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) and
   [PLAN.md](PLAN.md). Work outside them waits for the owner. A session that
   finds a requirement wrong or impossible says so in its PR or in
   [docs/HANDOVER.md](docs/HANDOVER.md), and goes on with the rest.
3. The owner's decisions (requirements, "Owner decisions") are not reopened
   by a session. A session may report evidence against one.

## Git and GitHub

4. No AI attribution trailers in commits or PR bodies: no `Co-Authored-By`
   lines for a model and no "Generated with" footers.
5. One task per PR, on a branch named `task/Tnn-short-name`. If the previous
   task's PR is not merged yet, the next branch may start from it; the PR
   says "stacked on #n". At most three unmerged PRs in a stack; then stop
   and wait.
6. Each PR updates its task's row in PLAN.md and the handover.
7. No posts to angband/angband or any other upstream project or forum.
   Nothing is filed in other repositories; a needed change there is
   described in the handover for the owner.

## Play and evidence

8. **No change to the game's rules or the Borg's behaviour.** The bridge
   adds a connection; with the agent mode off, play is byte-identical to the
   unpatched build.
9. **Determinism.** Seed, birth, settings and the recorded action stream
   reproduce a game. Wall time and model latency never affect play.
10. **Raw before interpretation.** Run records are immutable once written;
    claims point to them and never change them. Corrections are new records
    or new claims.
11. **The playing agent's sources** are limited as in
    [docs/SOURCES.md](docs/SOURCES.md). Executor primitives contain no Borg
    tactics.
12. A model never promotes its own claim above `hypothesis`. A counted probe
    or a review by a different model family does, and the owner decides
    what enters the remake's specification.
13. No munchkin start and no lunal mode. Birth options are the game's
    defaults.

## Files

14. Original game files, build output, saves and large logs are not
    committed. Large logs are stored by SHA-256 outside git, and the record
    names the hash.
15. No secrets in the repository or in run records. Model keys come from the
    environment.
