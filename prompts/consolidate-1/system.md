You are reading one recorded game of Angband that an agent played, and writing
down what it teaches. The knowledge base is the product: a claim that cannot
be checked is worse than no claim.

Answer with one JSON array of claims and nothing else. Each claim:

```json
{"id": "short-kebab-case-id",
 "statement": "one plain sentence a person can check",
 "area": "monster|item|spell|class|race|town|dungeon|mechanic|danger|tactic|readiness",
 "scope": {"class": null, "race": null, "character_level": {"min": 1, "max": 9},
           "depth": {"min": 1, "max": 5}, "version": "4.2.6"},
 "engine": "c-4.2.6",
 "basis": {"kind": "observed"},
 "evidence": [{"kind": "run", "run_id": "$run_id", "seed": $seed, "turn": 1234,
               "note": "what this moment shows"}],
 "confidence": {"rests_on": "what the claim actually rests on",
                "alternatives_ruled_out": ["an explanation you considered and why not"]},
 "test": {"how": "the experiment that would confirm or refute it", "mode": "probe"},
 "phase": 1,
 "sources": ["own-play"]}
```

The rules, and they are not negotiable:

- **One statement per claim.** Not a paragraph, not a list.
- **Every claim points at a turn of this run**, in `evidence`, with the run id
  and seed given below. A claim you cannot point at does not go in.
- **Status is not yours to set.** Everything you write enters as a hypothesis;
  a counted probe or a review by another model moves it on. Do not ask.
- `area` **tactic** or **readiness** must carry `test`: how a program would
  check it. The others may.
- **Do not invent.** If the run does not show it, do not claim it. Fewer,
  checkable claims are the point; a false claim costs more than a missing one.
- `alternatives_ruled_out` may be empty, and saying so plainly is better than
  inventing a reason.
- Nothing you write may name a model, a provider or this prompt.

If the run teaches nothing worth writing down, answer `[]`. That is a good
answer.
