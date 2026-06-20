---
name: vignette-catalog-scaffold
description: >-
  Create or adopt a repository as a new vignette catalog for a dataset,
  following the vignette-catalog pattern. Use when someone asks to start,
  scaffold, or build a new catalog, or make an existing repo follow the
  vignette-catalog pattern. Produces the minimum runnable files, conventions,
  manifest, and orientation notebook. Do not use for first-run setup in an
  already scaffolded catalog; use vignette-catalog-setup for that.
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion
---

# Scaffold a vignette catalog

Stamp out the minimum a new catalog needs.
The templates are in [references/templates.md](references/templates.md); read it before generating files.
The templates are a self-contained subset of the notebook/data conventions, so this skill can run without a sibling skill installed.
Step 8 can use the sibling validator only after step 4 installs the collection; when this skill is installed alone, run the equivalent validation sequence by hand.
When maintaining this collection, keep them aligned with the `vignette-catalog-compose-notebook` conventions.
The metric that matters is time-to-second-instance: how fast a domain expert ships a catalog for a new dataset.

## Why so little

A catalog is uv + PEP 723 + notebooks, nothing more.
Resist adding a package, a pipeline, or an environment manager now - those are weight you cannot remove later and almost never need.
Start minimal and let the catalog earn complexity only when a stable subset of the work demands it.

## Arguments

- `catalog-name` (required): short lowercase name (e.g. `cellpaint-x`). Ask if missing.
- `data-surface` (optional): how the catalog reaches its data - `rest`, `duckdb`, `pooch`, or `files` (small data committed to the repo). Ask if not given.
- Ask where to create it (absolute path to the parent directory).

## Steps

Run in order; stop and report on any failure.

1. Create the directory, but stop if the name is taken.
   A bare `mkdir` succeeds on an existing empty dir and `git init` will happily re-init over a populated one, so an accidental collision silently adopts or clobbers a catalog from a prior run.
   Guard against it:

   ```bash
   target="<parent>/<catalog-name>"
   if [ -e "$target" ] && [ -n "$(ls -A "$target" 2>/dev/null)" ]; then
       echo "error: $target already exists and is non-empty - pick another name or adopt it (see 'Adopting the pattern')" >&2
       exit 1
   fi
   mkdir -p "$target" && cd "$target"
   git init
   ```

2. Create the tree:

   ```bash
   mkdir -p notebooks
   mkdir -p data/{external,raw,interim,processed}
   touch data/{external,raw,interim,processed}/.gitkeep
   ```

3. Write `pyproject.toml`, `.gitignore`, `CLAUDE.md`, `AGENTS.md`, and `catalog.toml` from the templates in [references/templates.md](references/templates.md), substituting the catalog name and data surface.

4. Install the catalog skills so the agent can compose against the new catalog:

   ```bash
   npx skills add carpenter-singh-lab/vignette-catalog-skills -y
   ```

   The skills CLI auto-detects common agents; pass `--agent <agent>` only when the project needs an explicit target.
   This pulls the *published* skills and records that GitHub source in `skills-lock.json`. When you are iterating on the skills themselves and need the scaffold to use unpublished edits, install from a local checkout instead - `npx skills add <path-to-vignette-catalog-skills-checkout> -y` - then publish before the catalog is shared.

5. Write an orientation notebook `notebooks/nb01_orientation.py`: a PEP 723 header, a `with app.setup:` block, one or more `@app.function` helpers (at least one hits the data surface), and a `## To extend` cell. Keep it minimal but runnable. Start from the `notebooks/nb01_orientation.py` skeleton in [references/templates.md](references/templates.md) - it has the full marimo app frame (`import marimo`, `app = marimo.App(...)`, `if __name__ == "__main__": app.run()`), not just the setup block.
   Omit `__generated_with`; the step 8 validate (`marimo check --fix`) adds it back and normalizes the file - that is why you commit (step 9) after validating, so the stamped, normalized form is what lands.

6. Write a short `README.md`: what the catalog is, the one-row notebook list, setup instructions, links to sibling catalogs and to the vignette-catalog-skills repo. The setup section must include the post-clone skill restore (`npx skills update`), since the skill stores are gitignored and a cloner has only `skills-lock.json`.

7. Fill `catalog.toml` with the orientation notebook's helper(s) and the data surface / auth.

8. Validate with the `validate-notebook.sh` bundled in the installed `vignette-catalog-compose-notebook` skill, passing `notebooks/nb01_orientation.py`. After step 4's `npx skills add` the script lands under `.agents/skills/` (universal install) or `.claude/skills/` (when the install targets Claude Code) - resolve whichever exists rather than assuming one:

   ```bash
   VALIDATE=$(ls .agents/skills/vignette-catalog-compose-notebook/scripts/validate-notebook.sh \
                .claude/skills/vignette-catalog-compose-notebook/scripts/validate-notebook.sh 2>/dev/null | head -1)
   bash "$VALIDATE" notebooks/nb01_orientation.py
   ```

   If this skill was installed alone, run the launch/ruff/marimo-check/export sequence by hand.

9. `git add . && git commit -m "feat: initial catalog scaffold"`.

## Adopting the pattern in an existing repo

Often the target is not an empty directory but a repo that already exists - a planning repo or an analysis project with its own `README.md`, a `data/` tree, other tooling, maybe its own `CLAUDE.md` and `.gitignore`.
Here the catalog governs only the `notebooks/` and analysis side; it does not take over the repo.
The steps above still apply, with these adjustments:

- Skip step 1 - no `mkdir`, no `git init`, no `cd` into a new directory. You are already in the repo.
- Still author the contract: `catalog.toml`, `AGENTS.md`, the `pyproject.toml` ruff block, and a thin `CLAUDE.md`. If a `CLAUDE.md` already exists, thin it to a pointer at `AGENTS.md` rather than forking guidance across both.
- Reconcile the `.gitignore`, do not overwrite it. Keep the repo's existing rules and merge in only what is missing - in particular the skill-store ignore (`.agents/`, `.claude/skills/*`) so step 4's `npx skills add` does not vendor third-party skills into the repo. Ignore `notebooks/__marimo__/` by default; only add a `!notebooks/__marimo__/session/*.json` exception when the repo explicitly chooses to track molab/static snapshots, and warn that those JSONs can drift from random UI widget ids. For `surface = "files"`, do not add the `data/**` ignore: the repo commits its small data on purpose.
- Preserve the repo's existing planning docs and data; create only the `data/` tier directories that are missing.

Then continue from step 5 (orientation notebook) as normal.

## What this skill does NOT create

No `src/` package, no Snakemake/redun pipeline, no pixi environment, no Justfile, no S3 sync.
Those production pieces are added later, only if a stable subset earns them - see the vignette-catalog-skills README, "When to use a catalog vs a production pipeline".
