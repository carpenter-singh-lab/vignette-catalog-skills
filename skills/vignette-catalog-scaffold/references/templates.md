# Scaffold templates

Substitute `<CATALOG_NAME>` and fill `<DATA_SURFACE>` / `<MAP>` from the scaffold arguments.

> These templates reproduce the scaffold-time subset of the notebook/data conventions so this skill stays self-contained.
> When maintaining this collection, sync them with `skills/vignette-catalog-compose-notebook/references/conventions.md`.

## pyproject.toml

```toml
[tool.ruff]
line-length = 120

[tool.ruff.lint.per-file-ignores]
"notebooks/nb*.py" = ["B018", "F401", "F821", "F841"]
```

No `[project]` table - a catalog is not an installable package.

## .gitignore

```text
# Data contents (structure tracked via .gitkeep) - for fetched/large data only.
# OMIT this data/** block when surface = "files": small data committed to the repo,
# where you WANT data/ tracked. See the note under this block.
data/**
!data/**/
!data/**/.gitkeep
# Index envelopes are kilobyte metadata the index notebook discovers - keep them
# tracked even though the fetched/large data beside them is ignored.
!data/processed/**/summary.json

# marimo caches and exported session snapshots
notebooks/__marimo__/**

# Python and tool caches
.venv/
uv.lock
.ruff_cache/
__pycache__/
*.py[cod]

# Installed skills: recorded in the tracked skills-lock.json, NOT vendored.
# `npx skills add` writes content into these stores; ignoring them keeps a clone
# from committing third-party skill copies that go stale. A fresh clone restores
# them from the lock with `npx skills update` (see AGENTS.md / README). To commit
# a FIRST-PARTY skill you author in this repo, add an allow line, e.g.
# `!.claude/skills/<your-skill>/`.
.agents/
.claude/skills/*

# Local cache
.cache/
```

`skills-lock.json` itself is tracked - it is the record `npx skills update` restores from. Do not ignore it.
The `data/**` block is right for `rest` / `duckdb` / `pooch` surfaces, where `data/` holds large fetched artifacts.
The `!data/processed/**/summary.json` allow line is the deliberate exception: those envelopes are kilobyte metadata the index notebook globs and renders (see `indexing.md`), so they stay tracked even while the bulk data beside them is ignored.
For `surface = "files"` - small data committed to the repo (the whole point of a committed-data instance) - drop those four `data/**` lines so the data is tracked; git is then the integrity mechanism (see the `vignette-catalog-compose-notebook` data contract).
Do not track `notebooks/__marimo__/session/*.json` by default. Those files are useful local export artifacts, but they can include random marimo UI widget ids and produce noisy diffs. If a catalog deliberately wants molab/static previews from committed snapshots, add an explicit `!notebooks/__marimo__/session/*.json` exception and warn the user about the churn tradeoff.

## CLAUDE.md

```markdown
# CLAUDE.md - <CATALOG_NAME>

See [AGENTS.md](AGENTS.md) for all agent guidance.
This file exists only so Claude Code discovers the contract; do not fork guidance here.
```

## AGENTS.md

```markdown
# AGENTS.md - <CATALOG_NAME>

Project-specific guidance for agents working in this catalog.
`README.md` is the human entry point.
This catalog uses the shared vignette-catalog-skills (`vignette-catalog-setup`, `vignette-catalog-compose-notebook`); its specifics live in `catalog.toml`.

## Skills (restore after clone)

The catalog skills are installed via `npx skills add`, recorded in the tracked `skills-lock.json`, but **not vendored** -
the install stores (`.agents/`, `.claude/skills/*`) are gitignored. A fresh clone has only the lock, so the on-disk
skill content (and the `validate-notebook.sh` the rule below depends on) is missing until you restore it. Run once, from the repo root:

    npx skills update

This reconstitutes every skill the lock pins. Do this before relying on the skills or the validation rule.
(This instruction lives here, in a tracked file, on purpose: a skill cannot bootstrap its own install.)

## Launching notebooks

Always use `--sandbox` so PEP 723 inline metadata is provisioned:

    uvx marimo edit --sandbox notebooks/nbNN_*.py

Do not improvise alternative launch commands.

## Validation rule

After composing or editing any notebook, run the `validate-notebook.sh` bundled with the installed `vignette-catalog-compose-notebook` skill, passing the notebook path, then open it and look at the outputs.
Static checks do not catch wrong outputs, empty tables, stale endpoints, broken plots, or sign-convention mistakes.

## Architecture

- Catalog over library. Helpers are top-level `@app.function` cells in numbered notebooks; later notebooks import them via `sys.path`.
- <DATA_SURFACE: how this catalog reaches its data - REST via httpx/requests, DuckDB+parquet, pooch downloads.>
- Do not add a Python package until repeated cross-notebook imports make it painful.

## Conventions

Semantic line breaks in markdown. ASCII-only. Conventional Commits. `ruff line-length = 120` is Python only.

## Canonical contract (read before editing)

The rules above are the headline subset. The full, canonical contract lives in the installed
`vignette-catalog-compose-notebook` skill's `references/` - notebook conventions, the data
contract, indexing, the `catalog.toml` schema, and marimo gotchas (that skill's SKILL.md indexes
them). Read the relevant one before authoring or editing a notebook or its outputs; do not wait
for the skill to be invoked. Restore with `npx skills update` if the skill store is empty.

## When the question fits the catalog

The notebook-to-question routing lives in the `[[vignette]]` table in `catalog.toml` - each notebook, its helpers, and what it does - which is the single source the `vignette-catalog-compose-notebook` skill reads. Do not mirror that table here; point at it.
```

Two surfaces enumerate the notebooks on purpose, and that is the most they should: `catalog.toml`'s `[[vignette]]` table is the machine copy (the compose skill reads it), and the `README.md` table is the human copy (it carries molab preview links and prose for someone browsing the repo). `AGENTS.md` is for the agent, which already reads `catalog.toml`, so it adds a pointer, not a third copy. This keeps the scaffold aligned with `manifest.md`: "Keep `catalog.toml` the single source of the vignette table."

## catalog.toml

```toml
name = "<CATALOG_NAME>"
description = "<one line>"

[data]
surface = "<DATA_SURFACE>"   # rest | duckdb | pooch | files
cache = ""                   # env var or path for large cached artifacts; omit if none

[auth]
env_var = ""                 # required token var; empty = public
indirect_env_var = ""        # optional: var holding a secret-manager reference (e.g. an op:// item) the catalog resolves at runtime; omit if none

[getting_started]
first_notebook = "nb01_orientation.py"

[[vignette]]
notebook = "nb01_orientation.py"
helpers  = []                # fill once the orientation notebook defines helpers
does     = "Orientation: what this dataset is and how to reach it"
```

See the `vignette-catalog-compose-notebook` skill's `references/manifest.md` for the full manifest schema.

## notebooks/nb01_orientation.py

The orientation notebook is a real marimo `.py`, so it needs the marimo app frame, not just a setup block and a function.
Start from this skeleton and fill the surface-specific bits (`<DEP>` deps, the `@app.function` body that hits the surface).
Omit `__generated_with`; `marimo check --fix` (the validate step) stamps it - which is why you commit after validating, not before.

```python
# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = [
#     "marimo",
#     # <DEP: surface deps, e.g. "requests==2.32.5" (rest), "duckdb" + "pyarrow" (duckdb), "pooch" + "polars" (pooch)>
# ]
# ///

import marimo

app = marimo.App(width="medium")

with app.setup:
    import marimo as mo
    # <surface imports and constants, e.g. BASE_URL / a cache path>


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # nb01 - orientation

    <one paragraph: what this dataset is and how the catalog reaches it>
    """)
    return


@app.function
def reach_surface():
    """One call that hits the data surface and returns something real."""
    ...  # <surface-specific: a GET, a DuckDB query, a pooch fetch>


@app.cell
def _():
    result = reach_surface()
    mo.md("## Live check")
    result
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## To extend

    <two or three concrete next questions this catalog should answer>
    """)
    return


if __name__ == "__main__":
    app.run()
```

### REST surfaces: harden the HTTP helper

For a `rest` surface the orientation helper is the catalog's first HTTP call, and a bare `requests.get(url).raise_for_status()` is too optimistic against a real public API (see `conventions.md`, "REST surfaces are flaky", for why).
Send an identifying `User-Agent` and retry transient `5xx` / connection errors under a bounded timeout, factored as one importable `@app.function` so every later notebook inherits it:

```python
with app.setup:
    import time

    import requests

    BASE_URL = "https://<api-host>/<base-path>"
    HEADERS = {"Accept": "application/json", "User-Agent": "<catalog>/0.1 (+<repo-url>)"}


@app.function
def api_get(endpoint: str, params: dict | None = None, *, retries: int = 5, backoff: float = 2.0) -> object:
    """GET <dataset> with a bounded timeout and retry on transient 5xx / connection errors."""
    last = None
    for attempt in range(retries):
        try:
            response = requests.get(
                f"{BASE_URL}/{endpoint.lstrip('/')}", params=params, headers=HEADERS, timeout=30
            )
            if response.status_code < 500:
                response.raise_for_status()  # 4xx is a real client error - surface it now
                return response.json()
            last = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last = str(exc)
        time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"{endpoint} failed after {retries} retries: {last}")
```

`reach_surface()` then calls `api_get(...)` instead of a bare GET.
Live HTTP only - `duckdb` / `pooch` / `files` surfaces do not need it.
