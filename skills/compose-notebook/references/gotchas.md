# Gotchas

Harvested from the live catalogs (jx, fgx, prx, dmx). These are the traps that pass static checks but break the result or the molab preview.

## molab session snapshots (the big one)

Session snapshots (`notebooks/__marimo__/session/*.py.json`) store a `code_hash` per cell.
molab attaches a stored output to a source cell only when the hash matches.
Any later edit - including a `ruff format` whitespace pass - shifts every hash and silently strips outputs in the public preview.

- Always regenerate snapshots **after** the final source/formatter edit.
- Commit the regenerated `.json` in the same change that touched the `.py`.
- A snapshot that fails to execute is a real bug in the notebook, not in the snapshot.
- `marimo check` warns `markdown-indentation` on multi-line `mo.md("""...""")` cells; resolve it with `marimo check --fix` (one pass), not by hand - hand-indenting rarely matches what marimo wants. `validate-notebook.sh` runs `--fix` before the format + snapshot steps for this reason.
- The snapshot only survives if `.gitignore` keeps the `!notebooks/__marimo__/session/*.json` exception. A blanket `__marimo__/` ignore - common in repos not scaffolded by this skill - silently drops the snapshots you just regenerated; reconcile it when adopting the pattern in an existing repo.

## altair / vega-lite in molab

- Wrap altair charts in `mo.ui.altair_chart(chart)` - molab's static viewer does not ship a raw vega-lite renderer, though the live kernel does.
- Project the DataFrame to only the encoded columns before charting (`df.select([...])`); a wide frame embeds unused columns in the vega-lite spec and blows past molab's ~10 MB `output_max_bytes`.
- Pass polars frames to altair directly (the narwhals bridge handles it); some endpoints need `.to_dicts()` for small inline data.
- Datasets under ~10 rows can break the `mo.ui.altair_chart()` wrapper; render plainly instead.

## marimo cell traps

- Only the **last expression** in a cell renders. Narrative written before the data is silently dropped - wrap in a single `mo.vstack([...])` or split into cells.
- **Top-level variable names must be unique** across cells (marimo's reactive graph allows one definition per name). Prefix cell-private scratch with `_` (e.g. `_chart`); rename genuinely shared values.
- A name starting with `_` is cell-local and cannot be referenced from another cell - drop the underscore if it needs to be visible.

## environment

- `env -u PYTHONPATH` before `uvx marimo ...`: a Nix-shell websockets shim on `PYTHONPATH` crashes marimo startup.
- Always launch with `--sandbox` or PEP 723 deps are not provisioned and every notebook fails with `ModuleNotFoundError`.

## data surfaces

- Query an API's OpenAPI spec before guessing parameter names; semantic endpoint names do not imply response shape or granularity.
- Pin SHA-256 on pooch fetches - Figshare and CDNs 302-redirect, and the hash is what guarantees integrity across a swap.
- Check sign conventions on similarity/distance matrices against the actual values, not the filename or docstring (a jx cosine matrix is labeled like a distance but holds similarities in [-1, 1]).
