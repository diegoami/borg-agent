# Rules

These hold for every session working on this repository, local or cloud.

## Owner

1. **A session merges its own task PRs** into `main` once CI is green, with no
   approval and nothing waiting on the owner (the owner, 2026-11-08). The one
   merge a session never makes is the **review PR** at a milestone: that one is
   the owner's.
2. Scope comes from [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) and
   [PLAN.md](PLAN.md). Work outside them waits for the owner. A session that
   finds a requirement wrong or impossible says so in its PR or in
   [docs/HANDOVER.md](docs/HANDOVER.md), and goes on with the rest.
3. The owner's decisions (requirements, "Owner decisions") are not reopened
   by a session. A session may report evidence against one.

## Git and GitHub

4. No AI attribution trailers in commits or PR bodies: no `Co-Authored-By`
   lines for a model and no "Generated with" footers.
5. One task per PR, on a branch named `task/Tnn-short-name`, merged by the
   session that wrote it. A branch may start from an unmerged one; the PR then
   says "stacked on #n".
6. Each PR updates its task's row in PLAN.md and the handover.
7. **Reviews happen at milestones, not per task** (the owner, 2026-11-08).
   [PLAN.md](PLAN.md)'s milestone table says which tasks belong to which
   milestone. When the last task of a milestone is merged, **a session stops**
   — it does not begin the next milestone — and opens the review PR:

   ```sh
   gh pr create --base reviewed --head main --title "Milestone N review: ..."
   ```

   The `reviewed` branch stands at the last reviewed state of `main`, so that
   PR's diff is exactly the milestone's work. Its body lists the tasks, what
   each verified, what was not checked and the open questions, and carries the
   prompt a reviewer needs. The reviewer posts findings on it; the **owner**
   merges it, which advances `reviewed`. The findings then become a task of
   their own (T12 is milestone 1's).
8. No posts to angband/angband or any other upstream project or forum.
   Nothing is filed in another repository **unless the owner asks for it**,
   and then only in one of their own: the needed change is otherwise
   described in the handover for the owner to carry over. The owner asked on
   2026-11-09 for the milestone 8 request to the zoo
   ([borg-zoo#36](https://github.com/diegoami/borg-zoo/issues/36)), which is
   what that exception looks like: a request, in the owner's own repository,
   changing nothing there.

## Play and evidence

9. **No change to the game's rules or the Borg's behaviour.** The bridge
   adds a connection; with the agent mode off, play is byte-identical to the
   unpatched build.
10. **Determinism.** Seed, birth, settings and the recorded action stream
    reproduce a game. Wall time and model latency never affect play.
11. **Raw before interpretation.** Run records are immutable once written;
    claims point to them and never change them. Corrections are new records
    or new claims.
12. **The playing agent's sources** are those of
    [docs/SOURCES.md](docs/SOURCES.md): the manual is required, and decision
    D8 allows the game source, the Borg source, the specification, the
    deaths, the issues and the zoo's results. Every claim names its sources
    and says whether a fact was read or seen. Executor primitives still
    contain no Borg tactics.
13. A model never promotes its own claim above `hypothesis`. A counted probe
    or a review by a different model family does, and the owner decides
    what enters the remake's specification.
14. No munchkin start and no lunal mode. Birth options are the game's
    defaults.

## Files

15. Original game files, build output, saves and large logs are not
    committed. Large logs are stored by SHA-256 outside git, and the record
    names the hash.
16. No secrets in the repository or in run records. Model keys come from the
    environment.
