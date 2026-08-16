---
name: vignette-catalog-scaffold
description: >-
  Create or adopt a repository as a vignette catalog for one dataset. Use when
  the user asks to start, scaffold, or convert a project into a catalog with
  catalog.toml and reusable marimo notebooks. Produces the smallest runnable
  structure and orientation notebook. Do not use for an existing catalog;
  use vignette-catalog-compose-notebook there.
allowed-tools: Bash, Read, Write, Glob, Grep
---

# Scaffold a vignette catalog

A catalog starts as a manifest and one useful notebook, not a package or pipeline.
Ask for the catalog name, target path, and data surface (`rest`, `duckdb`, `pooch`, or `files`) only when they cannot be inferred.

## Workflow

1. Inspect the target.
   For a new catalog, require an absent or empty directory.
   For an existing repository, preserve its files and use `--adopt`.

2. Generate the minimum structure:

   ```bash
   <skill-dir>/scripts/scaffold.py <target> --name <name> --surface <surface>
   # Existing repository:
   <skill-dir>/scripts/scaffold.py <target> --name <name> --surface <surface> --adopt
   ```

   The script copies real assets rather than asking the model to reproduce templates from prose.

3. Replace the deliberate `NotImplementedError` in `notebooks/nb01_orientation.py` with one bounded call that reaches the actual dataset.
   Put reusable access logic in a top-level `@app.function`, and declare its dependencies and versions in the notebook's PEP 723 block.

4. Fill the dataset-specific fields in `catalog.toml`: description, upstream version, cache, caveats, auth, helper names, and what the orientation notebook demonstrates.
   Keep dataset identifiers, API behavior, hashes, and operational caveats in this catalog rather than the shared skills.

5. Reconcile existing `README.md`, `AGENTS.md`, `.gitignore`, and `pyproject.toml` instead of overwriting them when adopting.
   The generated `AGENTS.md` contains the exact post-clone skill install commands.

6. Install the project skills using that documented command, open the orientation notebook through `vignette-catalog-compose-notebook`, inspect its real output, and run its `scripts/validate-notebook.sh`.

Do not add `src/`, a shared environment, workflow engine, cloud sync, or an index until repeated work demonstrates the need.
