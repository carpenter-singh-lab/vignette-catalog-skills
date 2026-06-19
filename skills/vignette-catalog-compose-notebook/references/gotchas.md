# Gotchas

Harvested from repeated vignette-catalog runs.
These are the traps that pass static checks but break the result or the molab preview.

## marimo session snapshots

Session snapshots (`notebooks/__marimo__/session/*.py.json`) store a `code_hash` per cell.
molab attaches a stored output to a source cell only when the hash matches.
Any later edit - including a `ruff format` whitespace pass - shifts every hash and silently strips outputs in the public preview.
They can also include interactive UI widget metadata, including random ids, that drifts across identical exports.

- Treat snapshots as optional generated artifacts, not source, unless the repo explicitly tracks them for molab/static rendering.
- If the repo tracks snapshots, regenerate them **after** the final source/formatter edit and commit them in the same change that touched the `.py`.
- Warn the user before adopting or continuing that policy: snapshot diffs may include random widget-id churn unrelated to notebook behavior.
- A snapshot that fails to execute is a real bug in the notebook, not in the snapshot.
- `marimo check` warns `markdown-indentation` on multi-line `mo.md("""...""")` cells; resolve it with `marimo check --fix` (one pass), not by hand - hand-indenting rarely matches what marimo wants. `validate-notebook.sh` runs `--fix` before the format + export steps for this reason.
- If the repo intentionally tracks snapshots, `.gitignore` needs an explicit `!notebooks/__marimo__/session/*.json` exception; otherwise ignore `notebooks/__marimo__/` and leave exported snapshots local.

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
- Pin SHA-256 on pooch fetches - hosted files and CDNs can redirect or change silently, and the hash is what guarantees integrity across a swap.
- Check sign conventions on similarity/distance matrices against the actual values, not the filename or docstring.
