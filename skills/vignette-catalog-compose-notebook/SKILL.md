---
name: vignette-catalog-compose-notebook
description: >-
  Compose a marimo notebook that answers a data question by importing reusable
  @app.function helpers from an existing vignette catalog, running each step in
  a live kernel, and validating the final notebook. Use when a user asks for an
  analysis, figure, vignette, or notebook against a catalog dataset, even if
  they do not mention marimo or helper reuse. Do not use for generic notebook
  authoring outside a vignette catalog; run vignette-catalog-setup first if no
  live kernel exists.
allowed-tools: Bash, Read, Write, Glob, Grep
---

# Compose a notebook from a vignette catalog

Answer a question by composing existing catalog helpers in a live marimo kernel, not by writing a pipeline from scratch and checking it headless.
The live kernel - driven by the `marimo-pair` skill - is where you compose and look; the `.py` on disk is the durable artifact you commit.
The headless `validate-notebook.sh` is the final gate, not the feedback loop.

## Why compose instead of writing fresh

- **Catalog over library.** The catalog's reusable logic lives as top-level `@app.function` cells in numbered notebooks, not a package. Reuse them by importing; do not re-implement what a vignette already does, and do not reach for a `src/` package.
- **Vignettes vs composed notebooks.** The catalog's curated notebooks (vignettes) each teach one move and earn their place. What you produce here is a *composed* notebook - it only has to answer the question. Most composed notebooks stay composed; few become vignettes. This keeps the catalog small and high-signal.
- **Compose in the kernel, not against it.** Build the notebook by editing the `.py` and running each changed cell in the live kernel, looking at the output as it lands. Static checks pass on notebooks that return empty tables, wrong-signed correlations, or plots that render but say nothing; only a cell you have run and looked at is trustworthy. Discovering what your outputs say is the kernel's job, not the headless gate's.

## Procedure

1. **Ensure a live kernel.**
   You compose against a running marimo kernel driven by the `marimo-pair` skill.
   If none is running - no `marimo-pair` session, no port you can post cells to - run `vignette-catalog-setup` first: it installs `marimo-pair`, launches the catalog's first notebook under `--sandbox`, runs its cells, and hands back a live kernel on a known port.
   Keep that port; every "run a cell" below targets it.

2. **Orient from the manifest.**
   Read `catalog.toml` at the repo root for the vignette table (each notebook, its reusable `@app.function`s, and what they do), the data surface, and any auth.
   Then read the actual notebooks closest to the question - the helpers have docstrings and the cells are worked examples.
   See [references/manifest.md](references/manifest.md) for the schema.

3. **Pick the path.**

   - Parameter swap: the question is an existing vignette with different inputs -> change the inputs in the live notebook and re-run, cheapest.
   - Compose: the question needs helpers from two or more notebooks -> add a new `notebooks/<topic>.py` that imports them.
     Import helpers as plain Python; see [references/conventions.md](references/conventions.md) for the setup-block and `sys.path` recipe.

   Either way the `.py` on disk is the source of truth: author cells there, then run them in the kernel to see the result.
   Scratch exploration can happen live, but anything the finished notebook depends on must land in the `.py`, not only in kernel state - a fresh kernel has to reproduce it.

4. **Compose in the kernel - run, look, iterate.**
   This is the feedback loop.
   Work one cell at a time: run the fetch first and look at the actual frame before writing any narrative around it; do not fabricate numbers or describe outputs you have not run.
   Then add each downstream cell, run it in the kernel via the `marimo-pair` execute scripts (targeting your port), and read the output before moving on.
   For charts, looking means inspecting the rendered image, not just confirming the cell ran without error - use `marimo-pair`'s facilities for viewing cell outputs; if you cannot get eyes on a chart from the agent, export the figure to a file under `data/processed/<topic>/` and open that.
   Keep going until every cell runs clean and says something true.

5. **Final check - the headless gate.**
   Once the notebook reads right in the kernel, run it from a clean slate to catch what only the live session was propping up (stale kernel state, import order, a cell that never re-ran).
   Use the `scripts/validate-notebook.sh` bundled with this skill, passing the notebook path:

   ```bash
   bash <vignette-catalog-compose-notebook-skill-dir>/scripts/validate-notebook.sh notebooks/<topic>.py
   ```

   It runs `marimo check --fix`, runs `ruff` on that notebook, and - last, after the final source edit - executes the notebook through marimo export.
   This is a CI-style gate, not where you discover what your outputs say - you already looked at those in the kernel (step 4).
   It may write `__marimo__/session/*.json` as a local export artifact; treat those as gitignored generated files.
   Commit them only when the repo explicitly tracks snapshots for molab/static rendering, and warn the user about that tradeoff first.
   The snapshot tradeoffs and other traps are in [references/gotchas.md](references/gotchas.md).

6. **Write outputs and an index envelope.**
   Save analysis outputs under `data/processed/<topic>/`.
   Write a `summary.json` envelope (`{description, numbers, files}`) next to them so the catalog's index notebook can pick it up - see [references/indexing.md](references/indexing.md).
   Respect the data contract in [references/data.md](references/data.md): raw is immutable, fetches are SHA-256 pinned.

7. **End with "## To extend"** - two or three concrete next questions, so the notebook is a launchpad.

8. **Decide promotion.**
   Most composed notebooks stay composed notebooks.
   A few earn catalog-vignette status, but only if they teach a reusable move and only by deliberate curation; if so, add a row to `catalog.toml`.

## References

- [conventions.md](references/conventions.md) - notebook structure, naming, imports, PEP 723, ruff
- [data.md](references/data.md) - the four-tier data contract, SHA-256 pinning, caching
- [indexing.md](references/indexing.md) - the `summary.json` envelope and the index notebook
- [gotchas.md](references/gotchas.md) - marimo snapshots, altair/vega-lite, marimo cell traps
- [manifest.md](references/manifest.md) - the `catalog.toml` schema
