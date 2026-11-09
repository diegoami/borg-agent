# Run records: the runs this repository has published

R5 says only claims, run summaries and hashes go into git; the large logs
(observations, actions, model replies) stay outside it, addressed by hash. The
`runs/` directory git ignores is where a run is played; **this is where the
record of a run worth citing is kept**, so a claim's evidence can be checked
by someone who has only the repository.

Each file is one `borg-agent/run-record@1` document, immutable once written
(R4.1): a correction is a new record, never an edit. Each names the pins, the
build and its content identity, this repository's commit and dirty state, the
seed, the birth, the settings, the calendar, and the hash of every stream the
run wrote. `python -m borg_agent verify` needs the run directory itself; what a
record alone proves is **what the run claimed**, which is what a reviewer of a
claim needs first.

| Record | What it is |
|---|---|
| [api-first.json](api-first.json) | the first run a real model played (T06, 2026-11-09): `qwen3.8-flash` on the Alibaba Token Plan, seed 1 to 1,000 game turns, 51 decisions, **5 model calls**, no parse failures. It was replayed afterwards with `verify`, which reproduced all 51 state hashes |
| [pm-model.json](pm-model.json) | the first mode B post-mortem a real model played (T08, 2026-11-09): the Borg's death on seed 3 (a green naga at turn 15,714), the agent taking over at 15,514. It reached turn 16,039 and then the provider timed out, so the outcome is `harness_failure` and **nothing about avoiding the death is proved** |

Added after the milestone 3 review, which could not check either run: the
numbers were in the pull request and the records were not in git (R5's own
rule, unmet).
