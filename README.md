# vignette-catalog-skills

Installable agent skills for building and working in **vignette catalogs** - the lab's method for agent-driven data analysis.

A vignette catalog is a small, curated set of runnable [marimo](https://marimo.io) notebooks for one dataset, plus the skills in this repo that let an agent compose new analyses from them.
Each notebook is both a worked demonstration and a source of pure `@app.function` helpers that later notebooks import and reuse.
Given a question, a human and an agent pick relevant notebooks, import their helpers, compose them in a live kernel, and produce a self-contained, re-runnable notebook that answers it.

This is a general pattern for doing data analysis.
It works at one notebook and scales to many; scaling up is optional.
Four catalogs run today on this pattern: [jx](https://github.com/broadinstitute/jx) (JUMP Cell Painting), [fgx](https://github.com/broadinstitute/fgx) (FinnGen genetics), [prx](https://github.com/broadinstitute/prx) (PROSPECT chemical-genetics), [dmx](https://github.com/broadinstitute/dmx) (DepMap).

> This repo is the successor to the lab's old `workflows.md` (Cookiecutter Data Science + Snakemake/S3 pipeline SOP).
> Catalog-composition is now the default way we do data analysis; the heavy pipeline machinery is no longer where you start.

## Install

Works with any agent that supports the [Agent Skills](https://agentskills.io) open standard:

```bash
npx skills add carpenter-singh-lab/vignette-catalog-skills -y
```

This installs all three skills (they are small and work together). The three are also self-contained, so installing the collection and ignoring the ones you do not need is fine.
The skills CLI auto-detects common agents; pass `--agent <agent>` only when you need to target a specific one.

## The skills

| Skill | Use it to |
|---|---|
| [`vignette-catalog-setup`](skills/vignette-catalog-setup/SKILL.md) | Set up an existing catalog after clone: install uv + marimo-pair, launch the first notebook in a live kernel, hand off to composition. |
| [`vignette-catalog-compose-notebook`](skills/vignette-catalog-compose-notebook/SKILL.md) | Answer a question by composing a new notebook from a catalog's existing `@app.function` helpers in a live kernel, then check it with a headless gate. |
| [`vignette-catalog-scaffold`](skills/vignette-catalog-scaffold/SKILL.md) | Stand up a brand-new catalog for a new dataset - the minimum files, conventions, manifest, and orientation notebook. |

Each skill is self-contained: a `SKILL.md` plus its own `references/` (and `scripts/` where useful).
The skills are the executable contract; this page is human orientation.
The operational depth - conventions, gotchas, the data contract, the index notebook, scaffold templates - lives in each skill's `references/` and loads on demand, so it is not repeated here.

## Why this shape

- **Catalog over library.** Reusable logic lives as `@app.function` cells in numbered notebooks, imported across notebooks - not extracted into a package until repeated imports actually make it painful.
- **Vignettes vs composed notebooks.** Vignettes are the curated catalog (each teaches one move, high bar). Composed notebooks are answers to questions (they just have to work). Keeping them distinct is what keeps a catalog small and high-signal.
- **Agent-native.** The contract is skills, not a document, because the thing that acts on it is an agent. A catalog installs these skills rather than copy-pasting them, so the contract stays in one place and instances re-converge by version bump.

## When to use a catalog vs a production pipeline

Default to a catalog.
Reach for a production pipeline only when a stable subset needs scheduled, large-scale, or fully-managed reproducibility (a paper's final numbers, a recurring batch job); most analysis never crosses that line.
When it does, add a [redun](https://github.com/insitro/redun) pipeline alongside the catalog - the notebooks stay the source of the logic, the four-tier `data/` tree and SHA-256-pinned fetches carry over, and you add only the DAG (and pixi if GPU/conda deps demand it).
See [jpx](https://github.com/broadinstitute/jpx) for a worked example.

## Per-instance specifics

Each catalog declares its own vignette table, data surface, auth, and first notebook in a `catalog.toml` at its root, which the skills read - see [`skills/vignette-catalog-compose-notebook/references/manifest.md`](skills/vignette-catalog-compose-notebook/references/manifest.md).

## License

BSD 3-Clause - see [LICENSE](LICENSE).
