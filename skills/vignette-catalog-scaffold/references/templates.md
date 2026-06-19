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
# OMIT these four lines when surface = "files": small data committed to the repo,
# where you WANT data/ tracked. See the note under this block.
data/**
!data/**/
!data/**/.gitkeep

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

See the `vignette-catalog-compose-notebook` skill's `references/manifest.md` for the full manifest schema.
