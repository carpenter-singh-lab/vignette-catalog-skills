# Indexing the catalog

A catalog accumulates outputs.
Past a handful of notebooks you cannot eyeball what it has produced, so the catalog describes itself.

**Each notebook writes a `summary.json` envelope** into its own `data/processed/<analysis>/`, with a fixed shape:

```json
{
  "description": "one-line statement of what this output is",
  "numbers": { "n_compounds": 116753, "median_map": 0.42 },
  "files": [ { "path": "data/processed/<analysis>/fig1.png", "caption": "..." } ]
}
```

Those three keys are required. An analysis that is incomplete - waiting on upstream data, or holding a provisional result - may add an optional `status` object so the gap is recorded where the numbers are, not just in prose:

```json
{
  "description": "...", "numbers": { "...": "..." }, "files": [],
  "status": { "state": "pending", "note": "48h only; 24h raw not yet delivered" }
}
```

Use `state` for one of `complete` (the default - omit `status` entirely), `pending` (waiting on an input), or `provisional` (a result that will be revised), and `note` for a one-line human reason.
The index should surface it (a badge or note on the block) so a partial result is not read as final; discovery below is a superset check, so envelopes with or without `status` are both picked up.

**An index notebook** (`notebooks/index.py`) discovers every envelope, renders one block per envelope (description, numbers table, files, inline figures), and collates them into one consolidated artifact (`data/processed/index.{json,csv}`).

Key properties:

- The index **computes nothing of its own** - every number is read from the node that canonically produces it, tagged with its source and how it was derived.
  One number, one owner.
- Build it **dual-mode**: in a checkout it discovers via the repo and writes the artifact; standalone (e.g. on molab) it globs the public datastore anonymously and only renders.
- Discover envelopes by globbing `data/processed/**/summary.json` and keeping dicts whose keys are a superset of `{description, numbers, files}`.

Reference implementation: [`jump_production/notebooks/dataset_reference.py`](https://github.com/broadinstitute/jump_production/blob/main/notebooks/dataset_reference.py).

## Index vs GitHub Issues

Two surfaces, different jobs - use both:

- **GitHub Issues** carry the narrative: one issue per experiment, titled with the hypothesis, updated to the conclusion. Link notebooks, paste figures.
- **The index notebook** carries the quantitative map: what the catalog has produced and the verifiable numbers behind it.

Issues answer "why did we try this and what did we conclude"; the index answers "what numbers does this catalog stand behind, and where do they come from."
