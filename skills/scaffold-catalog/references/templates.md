# Scaffold templates

Substitute `<CATALOG_NAME>` and fill `<DATA_SURFACE>` / `<MAP>` from the scaffold arguments.

> These templates reproduce the scaffold-time subset of the notebook/data conventions so this skill stays self-contained (it can be installed without `compose-notebook`).
> The authoritative source is the `compose-notebook` skill's [`references/conventions.md`](https://github.com/carpenter-singh-lab/catalog-skills/blob/main/skills/compose-notebook/references/conventions.md).
> If the two ever diverge, the canonical file wins - update it there first, then sync the relevant template here.

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
# Data contents (structure tracked via .gitkeep)
data/**
!data/**/
!data/**/.gitkeep

# marimo caches, except committed session snapshots
notebooks/__marimo__/**
!notebooks/__marimo__/
!notebooks/__marimo__/session/
!notebooks/__marimo__/session/*.json

# Local cache
.cache/
```

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
This catalog uses the shared catalog-skills (`getting-started`, `compose-notebook`); its specifics live in `catalog.toml`.

## Launching notebooks

Always use `--sandbox` so PEP 723 inline metadata is provisioned:

    uvx marimo edit --sandbox notebooks/nbNN_*.py

Do not improvise alternative launch commands.

## Validation rule

After composing or editing any notebook, run `validate-notebook.sh`, then open it and look at the outputs.
Static checks do not catch wrong outputs, empty tables, stale endpoints, broken plots, or sign-convention mistakes.

## Architecture

- Catalog over library. Helpers are top-level `@app.function` cells in numbered notebooks; later notebooks import them via `sys.path`.
- <DATA_SURFACE: how this catalog reaches its data - REST via httpx/requests, DuckDB+parquet, pooch downloads.>
- Do not add a Python package until repeated cross-notebook imports make it painful.

## Conventions

Semantic line breaks in markdown. ASCII-only. Conventional Commits. `ruff line-length = 120` is Python only.

## When the question fits the catalog

<MAP: question type -> notebook, one line each. Mirror the [[vignette]] table in catalog.toml.>
```

## catalog.toml

```toml
name = "<CATALOG_NAME>"
description = "<one line>"

[data]
surface = "<DATA_SURFACE>"   # rest | duckdb | pooch | files
cache = ""                   # env var or path for large cached artifacts; omit if none

[auth]
env_var = ""                 # required token var; empty = public

[getting_started]
first_notebook = "nb01_orientation.py"

[[vignette]]
notebook = "nb01_orientation.py"
helpers  = []                # fill once the orientation notebook defines helpers
does     = "Orientation: what this dataset is and how to reach it"
```

See the `compose-notebook` skill's `references/manifest.md` for the full manifest schema.
