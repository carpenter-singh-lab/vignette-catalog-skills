---
name: compose-notebook
description: >-
  Compose a new marimo notebook that answers a data question by reusing the
  @app.function helpers already in a vignette catalog (jx, fgx, prx, dmx, or any
  catalog on the catalog-skills pattern), then validate it in a live kernel.
  Use whenever someone asks for an analysis, figure, notebook, or vignette
  against a catalog's dataset - even if they don't say "marimo" or "reuse the
  catalog" - instead of writing a query pipeline from scratch or duplicating
  helpers that already exist.
allowed-tools: Bash, Read, Write, Glob, Grep
---

# Compose a notebook from a catalog

Answer a question by composing existing catalog helpers in a live kernel, not by writing a pipeline from scratch.
Drive the kernel with the `marimo-pair` skill; if it is not running, run `getting-started` first.

## Why compose instead of writing fresh

- **Catalog over library.** The catalog's reusable logic lives as top-level `@app.function` cells in numbered notebooks, not a package. Reuse them by importing; do not re-implement what a vignette already does, and do not reach for a `src/` package.
- **Vignettes vs composed notebooks.** The catalog's curated notebooks (vignettes) each teach one move and earn their place. What you produce here is a *composed* notebook - it only has to answer the question. Most composed notebooks stay composed; few become vignettes. This keeps the catalog small and high-signal.
- **Validate by running and looking.** Static checks pass on notebooks that return empty tables, wrong-signed correlations, or plots that render but say nothing. The result is only trustworthy once you have executed every cell and looked at the output.

## Procedure

1. **Orient from the manifest.**
   Read `catalog.toml` at the repo root for the vignette table (each notebook, its reusable `@app.function`s, and what they do), the data surface, and any auth.
   Then read the actual notebooks closest to the question - the helpers have docstrings and the cells are worked examples.
   See [references/manifest.md](references/manifest.md) for the schema.

2. **Pick the path.**

   - Parameter swap: the question is an existing vignette with different inputs -> edit inputs in place, cheapest.
   - Compose: the question needs helpers from two or more notebooks -> write a new `notebooks/<topic>.py` that imports them.
     Import helpers as plain Python; see [references/conventions.md](references/conventions.md) for the setup-block and `sys.path` recipe.

3. **See the data before the story.**
   Run the fetch and look at the actual frame before writing narrative around it.
   Do not fabricate numbers or describe outputs you have not run.

4. **Validate - run, look, check, snapshot.**
   Order matters.
   Use the `scripts/validate-notebook.sh` bundled with this skill, passing the notebook path:

   ```bash
   bash <compose-notebook-skill-dir>/scripts/validate-notebook.sh notebooks/<topic>.py
   ```

   It runs `marimo check --fix`, runs `ruff` on that notebook, and - last, after the final source edit - executes the notebook and refreshes the molab session snapshot.
   Then open the notebook and inspect the outputs yourself; static checks miss empty tables, wrong signs, and plots that render but say nothing.
   Commit the regenerated `__marimo__/session/*.json` in the same change as the `.py`.
   The snapshot `code_hash` discipline and other traps are in [references/gotchas.md](references/gotchas.md).

5. **Write outputs and an index envelope.**
   Save analysis outputs under `data/processed/<topic>/`.
   Write a `summary.json` envelope (`{description, numbers, files}`) next to them so the catalog's index notebook can pick it up - see [references/indexing.md](references/indexing.md).
   Respect the data contract in [references/data.md](references/data.md): raw is immutable, fetches are SHA-256 pinned.

6. **End with "## To extend"** - two or three concrete next questions, so the notebook is a launchpad.

7. **Decide promotion.**
   Most composed notebooks stay composed notebooks.
   A few earn catalog-vignette status, but only if they teach a reusable move and only by deliberate curation; if so, add a row to `catalog.toml`.

## References

- [conventions.md](references/conventions.md) - notebook structure, naming, imports, PEP 723, ruff
- [data.md](references/data.md) - the four-tier data contract, SHA-256 pinning, caching
- [indexing.md](references/indexing.md) - the `summary.json` envelope and the index notebook
- [gotchas.md](references/gotchas.md) - molab snapshots, altair/vega-lite, marimo cell traps
- [manifest.md](references/manifest.md) - the `catalog.toml` schema
