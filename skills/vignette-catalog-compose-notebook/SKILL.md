---
name: vignette-catalog-compose-notebook
description: >-
  Work in an existing vignette catalog: set it up, run or inspect its marimo
  notebooks, and answer data questions by reusing their @app.function helpers
  in a live kernel. Use whenever a repository has catalog.toml and the user
  asks to get started, run notebooks, explore the data, make an analysis or
  figure, or compose a new notebook. Do not use for generic notebooks or for
  creating a new catalog.
allowed-tools: Bash, Read, Write, Glob, Grep
---

# Work in a vignette catalog

A catalog is a `catalog.toml` plus self-contained marimo notebooks that double as worked examples and importable helper modules.
Use `marimo-notebook` for general notebook authoring and `marimo-pair` for every live-kernel action.
Repository instructions, `catalog.toml`, and this skill's notebook contract override generic `marimo-notebook` advice when they are more specific.
If either project skill is absent, stop and give the user the repository's documented install command rather than installing it implicitly.
Resolve `<skill-dir>` to this installed skill and execute its Python scripts directly so their `uv` shebangs apply.

## Workflow

1. Read the repository's `AGENTS.md`, `catalog.toml`, and any path named by `[data].caveats`.
   Use the manifest to find likely notebooks, then read their actual code and docstrings.
   The manifest is a curated routing table, not necessarily an inventory of every notebook or helper.

2. Connect to the relevant notebook with `marimo-pair`.
   Discover an existing session first.
   If none fits, run `<skill-dir>/scripts/catalog-session.py start [notebook]`; omitting the notebook starts `[getting_started].first_notebook`.
   The command prints the URL, port, and session id needed to target the kernel explicitly.

3. Take the shortest path that answers the question.
   Change inputs in an existing notebook when its workflow already fits.
   Otherwise create a composed notebook and import the closest helpers instead of recreating their requests, parsing, joins, or plots.
   Read [references/notebook-contract.md](references/notebook-contract.md) when authoring or changing a notebook.

4. Work through the live kernel.
   Use `marimo-pair` code mode for durable cell edits, run each changed cell, and inspect the returned tables and rendered figures before interpreting them.
   Start remote or REST exploration with a bounded query, then widen deliberately.
   Keep every dependency of the answer in the notebook, not only in scratch state.

5. Prove the saved notebook from a clean state:

   ```bash
   bash <skill-dir>/scripts/validate-notebook.sh notebooks/<name>.py
   ```

   The validator runs pinned marimo checks, a stable Ruff rule set, cold execution, and an explicit scan for failed cells because marimo can report failure while exiting zero.
   It restores source and snapshots by default; pass `--write` only when the catalog policy calls for formatting and a refreshed snapshot.
   Follow the catalog's own policy for generated session snapshots and analysis outputs.

6. Report what ran, what you inspected, the answer and its limits, and the live URL if the session remains useful.
   Stop a session you no longer need with `<skill-dir>/scripts/catalog-session.py stop <port>`.
   Promote a composed notebook into `catalog.toml` only when the user wants it curated as a reusable vignette.

## Running a catalog without composing

When the user only wants setup or verification, start the requested notebook, run all cells through `marimo-pair`, inspect one meaningful output, and report the URL.
When asked to verify the whole catalog, enumerate the actual notebook files rather than assuming `catalog.toml` is exhaustive, and validate each in a disposable worktree or archive if the catalog tracks generated snapshots.
