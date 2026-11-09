# Examples

These files are **illustrative fixtures for the schemas**, not knowledge.

- `valid-*.json` must validate against the schema in the directory above;
  `invalid-*.json` must not, and its file name says which rule it breaks.
  `tests/test_schemas.py` checks both.
- The **run-record** examples are generated from real runs by
  `scripts/refresh-examples.py`, so an example cannot claim something the
  recorder does not produce. Regenerate them rather than editing them by hand.
- The **claim** examples are written by hand to show the lifecycle of R4. The
  statements in them are illustrations, and the provenance in each one is
  honest: a claim that rests on the zoo's results says `zoo-results`, one read
  in the Borg's source says `static:borg-source` and names its reference.

**They are not the knowledge base.** Nothing here may be loaded into
`knowledge/`, into a prompt pack, or into any ingestion path: a fixture is not
evidence, and a claim with no run behind it is not a claim. The knowledge store
(T07) reads `knowledge/` only.
