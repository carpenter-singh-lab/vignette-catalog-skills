---
name: vignette-catalog-compose-notebook
description: >-
  Work in an existing vignette catalog: open or rerun its marimo notebooks,
  set it up, and answer data questions by reusing their @app.function helpers
  in a live kernel. Use whenever a repository has catalog.toml and the user
  asks to open or run a notebook, get started, explore the data, make an
  analysis or figure, or compose a new notebook. Do not use for generic
  notebooks or for creating a new catalog.
allowed-tools: Bash, Read, Write, Glob, Grep
---

# Work in a vignette catalog

A catalog is a `catalog.toml` plus self-contained marimo notebooks that double as worked examples and importable helper modules.
Resolve `<skill-dir>` to this installed skill and execute its Python scripts directly so their `uv` shebangs apply.
`<skill-dir>/scripts/catalog-session.py` owns the whole session lifecycle: it starts, reuses, inspects, runs, and stops catalog kernels deterministically and survives shell wrappers.
Never launch marimo through ad hoc `nohup` or backgrounding, and never reconstruct session state from `pgrep`, `ss`, `curl`, or `/api/sessions` by hand.
If the helper fails, report its exact output before trying anything else.

## Route the request first

- Open, run, or view a specific notebook, or "get this catalog running": follow the fast path below, then stop.
  Do not read the notebook contract, unrelated notebooks, or data references on this path.
- Change inputs in a notebook that is already live: reuse its session through `marimo-pair` code mode.
  Do not start a second kernel unless the current one is irrecoverable.
- Compose a new notebook or answer a data question: follow the compose workflow.
- Open-ended research: use the compose workflow for mechanics; research methodology stays with the user and repository, not this skill.

## Fast path: open an exact notebook

1. Read the repository's `AGENTS.md` and `catalog.toml`.
   You need only auth requirements and `[getting_started].first_notebook`; skip caveats and notebook code that launching does not require.

2. Run one command; it reuses a healthy session for that exact notebook or starts one, ensures the cells ran, and prints the result:

   ```bash
   <skill-dir>/scripts/catalog-session.py open [notebooks/<name>.py]
   ```

   Omitting the notebook opens `[getting_started].first_notebook`.
   When the user can already reach this machine directly (for example over Tailscale or a LAN), pass `--host <reachable-address>` so the printed URL works without a tunnel; set up SSH forwarding only when no direct route exists.

3. Report `url=` and `session=` and the `cells=` line verbatim.
   `cell_error=` lines mean the notebook ran but has failing cells: report them; the session stays live for iteration.
   Answer any follow-up about session state with `<skill-dir>/scripts/catalog-session.py status --cells`, rerun cells with `run <port>`, and stop a session you own with `stop <port>`.

## Compose workflow

Use `marimo-notebook` for general notebook authoring and `marimo-pair` for every live-kernel action.
Repository instructions, `catalog.toml`, and this skill's notebook contract override generic `marimo-notebook` advice when they are more specific.
If either project skill is absent, stop and give the user the repository's documented install command rather than installing it implicitly.

1. Read the repository's `AGENTS.md`, `catalog.toml`, and any path named by `[data].caveats`.
   Use the manifest to find likely notebooks, then read their actual code and docstrings.
   The manifest is a curated routing table, not necessarily an inventory of every notebook or helper.

2. Take the shortest path that answers the question.
   Change inputs in an existing notebook when its workflow already fits.
   Otherwise create a composed notebook and import the closest helpers instead of recreating their requests, parsing, joins, or plots.
   Read [references/notebook-contract.md](references/notebook-contract.md) when authoring or changing a notebook.

3. For a new composition, create its smallest valid marimo scaffold, including the initial setup imports.
   Open the exact notebook you are adapting or composing with `catalog-session.py open notebooks/<name>.py`.
   Use the reported URL and session id with `marimo-pair`; the active runtime is authoritative until you validate the saved file.

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

When asked to verify the whole catalog, enumerate the actual notebook files rather than assuming `catalog.toml` is exhaustive, and validate each in a disposable worktree or archive if the catalog tracks generated snapshots.
