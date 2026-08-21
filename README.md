# vignette-catalog-skills

Agent skills for building and using vignette catalogs.

A vignette catalog is a `catalog.toml` and a curated set of self-contained [marimo](https://marimo.io) notebooks for one dataset.
Each notebook is both a worked example and a source of reusable top-level `@app.function` helpers.
An agent answers a new question by changing an existing notebook or composing those helpers in a live kernel.

## Install

Install the two catalog skills and their live-kernel dependency into the project:

```bash
npx skills@1.5.20 add carpenter-singh-lab/vignette-catalog-skills \
  -s vignette-catalog-compose-notebook \
  -s vignette-catalog-scaffold \
  -a claude-code \
  -a codex \
  -y

npx skills@1.5.20 add marimo-team/skills \
  -s marimo-notebook \
  -a claude-code \
  -a codex \
  -y

npx skills@1.5.20 add 'shntnu/marimo-pair#pr69-9528681' \
  -s marimo-pair \
  -a claude-code \
  -a codex \
  -y
```

Drop an agent flag when the project uses only one product.
Track `skills-lock.json`, ignore installer-owned skill directories, and repeat the exact commands in the catalog's `AGENTS.md` so a fresh clone can restore them.

The collection is also packaged as a Claude Code and Codex plugin when plugin installation is preferred.

## Skills

| Skill | Purpose |
|---|---|
| [`vignette-catalog-compose-notebook`](skills/vignette-catalog-compose-notebook/SKILL.md) | Set up and run an existing catalog, inspect notebooks, or answer a new question by reusing catalog helpers in a live kernel. |
| [`vignette-catalog-scaffold`](skills/vignette-catalog-scaffold/SKILL.md) | Create or adopt the minimum catalog structure and orientation notebook. |

The compose skill deliberately contains little prose.
The official `marimo-notebook` skill supplies general notebook-authoring guidance, while `marimo-pair` owns live-kernel interaction.
Operational behavior lives in the compose skill's session and validation scripts, while dataset-specific versions, auth, caches, identifiers, hashes, and caveats stay in each catalog.

## Design

- Catalog over library: keep reusable logic in notebooks until repeated use genuinely earns a package.
- Parameter change before composition: reuse the closest working path.
- Live inspection plus cold execution: neither one proves correctness alone.
- Curated vignettes stay few; one-off composed notebooks need only answer their question.
- A catalog does not require an index, `summary.json`, committed snapshots, or a production pipeline unless that instance has an actual use for them.

The current public examples are [jx](https://github.com/broadinstitute/jx), [fgx](https://github.com/broadinstitute/fgx), [prx](https://github.com/broadinstitute/prx), and [dmx](https://github.com/broadinstitute/dmx).

## Development

Behavioral regressions and the reason for each retained mechanism are recorded in [docs/INCIDENTS.md](docs/INCIDENTS.md).
The evaluation cases live with the compose skill under `evals/`.
Run the script regressions with `uv run tests/test_catalog_scripts.py`.

## License

BSD 3-Clause - see [LICENSE](LICENSE).
