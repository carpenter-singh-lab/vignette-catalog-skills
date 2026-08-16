# Notebook contract

Read this when creating or changing a catalog notebook.
Repository instructions and existing notebooks win when they are more specific.

## Imports

For a cross-notebook import, make `notebooks/` importable inside `app.setup`:

```python
with app.setup:
    import sys
    from pathlib import Path

    NOTEBOOK_DIR = Path(__file__).resolve().parent
    if str(NOTEBOOK_DIR) not in sys.path:
        sys.path.insert(0, str(NOTEBOOK_DIR))
    from nb02_example import useful_helper
```

An imported notebook is a Python module, so the importing notebook's PEP 723 block must include the full transitive dependency set.
Copy the dependency versions from the notebooks being reused rather than guessing newer ones.

## Marimo structure

- Put shared imports, paths, constants, and auth in `with app.setup:`.
- Give every public top-level name one defining cell; use leading underscores only for same-cell scratch values.
- Keep reusable computation in `@app.function` cells and the worked answer in `@app.cell` cells.
- Use `marimo-pair` code mode for changes while a session is active; direct file edits can be stale or overwritten.
- Keep scratch exploration temporary, then persist every load-bearing step in the notebook.

## Data and outputs

Honor the catalog's declared surface, version, cache, auth, caveats, and data-directory policy.
Reuse its existing access helper so retries, identifiers, hashes, and release assumptions stay centralized.
Do not impose `summary.json`, an index notebook, committed snapshots, or a four-tier data tree unless this catalog already uses them.

Inspect values, shapes, missingness, and sign conventions before drawing conclusions.
For a chart, inspect the rendered pixels rather than its object representation.
State important dataset or instrument limits alongside the result.
