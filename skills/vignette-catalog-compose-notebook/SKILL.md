---
name: vignette-catalog-compose-notebook
description: >-
  Compose a marimo notebook that answers a data question by importing reusable
  @app.function helpers from an existing vignette catalog, running each step in
  a live kernel, and validating the final notebook. Use when a user asks for an
  analysis, figure, vignette, or notebook against a catalog dataset, even if
  they do not mention marimo or helper reuse - and ALSO when the ask is
  open-ended research against the catalog: exploring the data, forming and
  testing a hypothesis, hunting for a non-obvious or better result, comparing
  approaches, or "doing the best you can" on a hard question. For those, the
  skill carries research-partner principles (hypothesis-then-test, going past
  the consensus answer, calibrating confidence, fanning out subagents, adversarial
  self-critique). Do not use for generic notebook authoring outside a vignette
  catalog; run vignette-catalog-setup first if no live kernel exists.
allowed-tools: Bash, Read, Write, Glob, Grep, Task
---

# Compose a notebook from a vignette catalog

Answer a question by composing existing catalog helpers in a live marimo kernel, not by writing a pipeline from scratch and checking it headless.
The live kernel - driven by the `marimo-pair` skill - is where you compose and look; the `.py` on disk is the durable artifact you commit.
The headless `validate-notebook.sh` is the final gate, not the feedback loop.

## Why compose instead of writing fresh

- **Catalog over library.** The catalog's reusable logic lives as top-level `@app.function` cells in numbered notebooks, not a package.
  Reuse them by importing; do not re-implement what a vignette already does, and do not reach for a `src/` package.
- **Vignettes vs composed notebooks.** The catalog's curated notebooks (vignettes) each teach one move and earn their place.
  What you produce here is a *composed* notebook - it only has to answer the question.
  Most composed notebooks stay composed; few become vignettes.
  This keeps the catalog small and high-signal.
- **Compose in the kernel, not against it.** Build the notebook by editing the `.py` and running each changed cell in the live kernel, looking at the output as it lands.
  Static checks pass on notebooks that return empty tables, wrong-signed correlations, or plots that render but say nothing; only a cell you have run and looked at is trustworthy.
  Discovering what your outputs say is the kernel's job, not the headless gate's.

## When it's research, not one figure

Some asks are not "make this chart" but "what does this data say about X?", "find me a better target", "is this hypothesis right?", "do the best you can."
Then you are a **research partner**: the deliverable is an evidence-built *argument*, honest about what it shows - and you can reach past the catalog (spawn subagents, read literature, search the web, hit other live APIs).
The notebook is still where the argument lands and stays re-runnable.

Before a thread like that, read **[references/research-method.md](references/research-method.md)** - the moves that make it productive instead of a fluent restatement of the consensus (hypothesis-then-test-its-other-predictions, hunt past the consensus answer, do not confirm your own model, calibrate confidence, fan out subagents as on-demand instruments, red-team your own result, design the falsifier, confirm before outward actions).
For how to *present* the result so a reader can trust it - the hypothesis-experiment-observation loop, narrating the world rather than your own iteration, separating robust from fragile, defining instruments - read **[references/communicating-the-analysis.md](references/communicating-the-analysis.md)**.
The composition mechanics below still apply throughout.

## Procedure

1. **Ensure a live kernel.** You compose against a running marimo kernel driven by the `marimo-pair` skill.
   If none is running - no `marimo-pair` session, no port you can post cells to - run `vignette-catalog-setup` first: it installs `marimo-pair`, launches the catalog's first notebook under `--sandbox`, runs its cells, and hands back a live kernel on a known port.
   Keep that port - but know it is the *first notebook's* sandbox, bound to that notebook.
   A parameter swap (step 3) runs there directly; composing a new notebook gets its own kernel instead (step 3 explains why and how).

2. **Orient from the manifest.** Read `catalog.toml` at the repo root for the vignette table (each notebook, its reusable `@app.function`s, and what they do), the data surface, and any auth.
   Then read the actual notebooks closest to the question - the helpers have docstrings and the cells are worked examples.
   See [references/manifest.md](references/manifest.md) for the schema.

3. **Pick the path.**

   - Parameter swap: the question is an existing vignette with different inputs -> change the inputs in the live notebook and re-run, cheapest.
   - Compose: the question needs helpers from two or more notebooks -> add a new `notebooks/<topic>.py` that imports them.
     Import helpers as plain Python; see [references/conventions.md](references/conventions.md) for the setup-block and `sys.path` recipe.

**A composed notebook usually needs its own kernel - do not assume the handed-off one will do.** The kernel `vignette-catalog-setup` gives you runs the *first* notebook inside a `--sandbox` provisioned from *that* notebook's PEP 723 deps.
The moment your composed `.py` declares a dependency the first notebook lacks - a plotting or dataframe library, say - importing it in the handed-off kernel fails with `ModuleNotFoundError`, because the sandbox was never told about it and `pip install` into a uv sandbox is not the path.
So default to giving the composed notebook its own kernel: launch a fresh one *on the composed notebook* with the same recipe `vignette-catalog-setup` step 5 uses (a new port, `env -u PYTHONPATH uvx marimo edit --sandbox --no-token --headless --port <new> notebooks/<topic>.py`, then register a session and run the cells), and target that new port for every "run a cell" in step 4.
Do this even when your deps happen to match the first notebook's - the handed-off kernel is bound to *that* notebook, not yours, so reusing it is awkward and easy to get wrong.
The dependency mismatch above is just the sharpest reason; "its own kernel" is the safe default regardless.
The one case that stays on the handed-off kernel is a parameter swap: changing inputs in the existing notebook in place, not composing a new file.

Either way the `.py` on disk is the source of truth: author cells there, then run them in the kernel to see the result.
Scratch exploration can happen live, but anything the finished notebook depends on must land in the `.py`, not only in kernel state - a fresh kernel has to reproduce it.

4. **Compose in the kernel - run, look, iterate.** This is the feedback loop.
   Work one cell at a time: run the fetch first and look at the actual frame before writing any narrative around it; do not fabricate numbers or describe outputs you have not run.
   On a REST or otherwise open-ended surface, bound that first fetch - one page, a small `limit`, a single id - before you widen.
   An unbounded exploratory pull can crawl an entire table (a popular target's bioactivity set is tens of thousands of rows) and stall the loop before you have seen the shape of anything.
   Look at the bounded slice, confirm the fields are what you expect, then raise the limit deliberately if the question actually needs more.
   Then add each downstream cell, run it in the kernel via the `marimo-pair` execute scripts (targeting your port), and read the output before moving on.
   When you edit a cell's source on disk, re-running it via `marimo-pair` runs the kernel's *in-memory* cell graph, not the file you just saved - so you keep executing the stale version and chase phantom errors (a `NameError` for a variable you already added, a fix that "doesn't take").
   After editing a cell, reload it into the kernel (or relaunch the kernel on the edited `.py`) before re-running; the headless gate in step 5 sidesteps this entirely by running from a clean slate.
   For charts, looking means inspecting the rendered image, not just confirming the cell ran without error.
   In a live session, `ctx.screenshot` rasterizes the rendered DOM to a PNG - one call for matplotlib, altair/vega, plotly, or a widget alike.
   See [references/viewing-outputs.md](references/viewing-outputs.md).
   Keep going until every cell runs clean and says something true.

**Headless does not mean no kernel - get a live one first.** No browser is *not* a reason to skip the live kernel.
A headless host (remote, SSH, agent-driven) still runs the full cell-by-cell loop: `vignette-catalog-setup` launches the kernel `--headless` and registers a session with its bundled `scripts/register-session.py` - a websocket stand-in that creates the session `execute-code` attaches to, no browser and no `agent-browser`/Chrome needed.
If no kernel is running, run that setup before composing; do not default to the export-only path below just because there is no display.
The live kernel is not a nicety here: it holds your fetched data in memory, so an expensive pull (a whole drug-response screen, a big matrix) happens once and every later probe slices it instantly.
Compose against the headless export instead and you re-fetch the same data on every probe - the single biggest avoidable cost on a REST surface like this catalog.

**Genuinely no port (locked-down CI, no `claude`, no reachable kernel).** Only when you truly cannot stand up or reach a kernel, fall back to this substitute: author the cells in the `.py` (still the source of truth), run the headless gate in step 5 to execute the whole notebook from a clean slate, and look at the real outputs through an export rather than a live kernel - the tier-3 path in [references/viewing-outputs.md](references/viewing-outputs.md) (export PNGs, or read the session JSON, mindful that a `mo.ui.altair_chart`'s data is a base64 Arrow blob, not plain rows).
The rule that you must look at actual outputs, not just a green check, is unchanged; only the surface you look at differs.
Do not treat "the cell ran without error" as having looked.

5. **Final check - the headless gate.** Once the notebook reads right in the kernel, run it from a clean slate to catch what only the live session was propping up (stale kernel state, import order, a cell that never re-ran).
   Use the `scripts/validate-notebook.sh` bundled with this skill, passing the notebook path:

   ```bash
   # `npx skills add` installs to .agents/skills/ (universal) or .claude/skills/ (when it targets
   # Claude Code) - resolve whichever exists rather than hardcoding one and hitting a missing path:
   VALIDATE=$(ls .agents/skills/vignette-catalog-compose-notebook/scripts/validate-notebook.sh \
                .claude/skills/vignette-catalog-compose-notebook/scripts/validate-notebook.sh 2>/dev/null | head -1)
   bash "$VALIDATE" notebooks/<topic>.py
   ```

It runs `marimo check --fix`, runs `ruff` on that notebook, and - last, after the final source edit - executes the notebook through marimo export.
This is a CI-style gate, not where you discover what your outputs say - you already looked at those in the kernel (step 4).
It may write `__marimo__/session/*.json` as a local export artifact; treat those as gitignored generated files.
Commit them only when the repo explicitly tracks snapshots for molab/static rendering, and warn the user about that tradeoff first.
The snapshot tradeoffs and other traps are in [references/gotchas.md](references/gotchas.md).

6. **Write outputs and an index envelope.** Save analysis outputs under `data/processed/<topic>/`.
   Write a `summary.json` envelope (`{description, numbers, files}`) next to them so the catalog's index notebook can pick it up - see [references/indexing.md](references/indexing.md).
   Respect the data contract in [references/data.md](references/data.md): raw is immutable, fetches are SHA-256 pinned.

7. **End with "## To extend"** - two or three concrete next questions, so the notebook is a launchpad.

8. **Decide promotion.** Most composed notebooks stay composed notebooks.
   A few earn catalog-vignette status, but only if they teach a reusable move and only by deliberate curation; if so, add a row to `catalog.toml`.

## References

- [research-method.md](references/research-method.md) - **research-partner principles**: how to use the catalog (and subagents, literature, the web) for open-ended, hypothesis-driven research that earns trust
- [communicating-the-analysis.md](references/communicating-the-analysis.md) - **how to present the result**: the hypothesis-experiment-observation loop, narrating the world not your own iteration, robust vs fragile, defining instruments
- [conventions.md](references/conventions.md) - notebook structure, naming, imports, PEP 723, ruff
- [data.md](references/data.md) - the four-tier data contract, SHA-256 pinning, caching
- [indexing.md](references/indexing.md) - the `summary.json` envelope and the index notebook
- [gotchas.md](references/gotchas.md) - marimo snapshots, altair/vega-lite, marimo cell traps
- [manifest.md](references/manifest.md) - the `catalog.toml` schema
