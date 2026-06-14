---
name: scaffold-catalog
description: >-
  Stand up a brand-new vignette catalog for a new dataset, following the
  catalog-skills pattern. Use when someone wants to start a catalog, create a
  new instance like jx/fgx/prx/dmx for a different dataset, or "scaffold a
  catalog" - produces the minimum runnable files, conventions, manifest, and an
  orientation notebook.
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion
---

# Scaffold a new catalog

Stamp out the minimum a new catalog needs.
The templates are in [references/templates.md](references/templates.md); read it before generating files.
The templates are a self-contained subset; the authoritative notebook/data conventions are the `compose-notebook` skill's [`references/conventions.md`](https://github.com/carpenter-singh-lab/catalog-skills/blob/main/skills/compose-notebook/references/conventions.md) - consult it (and prefer it on any conflict) when generating the orientation notebook.
The metric that matters is time-to-second-instance: how fast a domain expert ships a catalog for a new dataset.

## Why so little

A catalog is uv + PEP 723 + notebooks, nothing more.
Resist adding a package, a pipeline, or an environment manager now - those are weight you cannot remove later and almost never need.
Start minimal and let the catalog earn complexity only when a stable subset of the work demands it.

## Arguments

- `catalog-name` (required): short lowercase name (e.g. `cellpaint-x`). Ask if missing.
- `data-surface` (optional): how the catalog reaches its data - `rest`, `duckdb`, `pooch`. Ask if not given.
- Ask where to create it (absolute path to the parent directory).

## Steps

Run in order; stop and report on any failure.

1. `mkdir <parent>/<catalog-name> && cd` into it, `git init`.

2. Create the tree:

   ```bash
   mkdir -p notebooks/__marimo__/session
   mkdir -p data/{external,raw,interim,processed}
   touch data/{external,raw,interim,processed}/.gitkeep
   ```

3. Write `pyproject.toml`, `.gitignore`, `CLAUDE.md`, `AGENTS.md`, and `catalog.toml` from the templates in [references/templates.md](references/templates.md), substituting the catalog name and data surface.

4. Install the catalog skills so the agent can compose against the new catalog:

   ```bash
   npx skills add carpenter-singh-lab/catalog-skills --agent claude-code -y
   ```

5. Write an orientation notebook `notebooks/nb01_orientation.py`: a PEP 723 header, a `with app.setup:` block, one `@app.function` that hits the data surface, and a `## To extend` cell. Keep it minimal but runnable.

6. Write a short `README.md`: what the catalog is, the one-row notebook list, getting-started, links to sibling catalogs and to the catalog-skills repo.

7. Fill `catalog.toml` with the orientation notebook's helper(s) and the data surface / auth.

8. Validate: `bash scripts/validate-notebook.sh notebooks/nb01_orientation.py` (from the catalog-skills install), or run the launch/ruff/marimo-check/export sequence by hand.

9. `git add . && git commit -m "feat: initial catalog scaffold"`.

## What this skill does NOT create

No `src/` package, no Snakemake/redun pipeline, no pixi environment, no Justfile, no S3 sync.
Those production pieces are added later, only if a stable subset earns them - see the catalog-skills README, "Graduating to a production pipeline".
