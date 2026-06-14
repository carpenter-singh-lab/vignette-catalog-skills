# AGENTS.md - catalog-skills

Guidance for agents working **on this repository** (authoring and editing the skills themselves).
To work in a catalog that has these skills installed, read the installed skill, not this file.

## What this repo is

An installable collection of agent skills for the vignette-catalog method.
`README.md` is the human entry point and conceptual orientation.
Each skill under `skills/<name>/` is self-contained: a `SKILL.md` plus its own `references/` and (where needed) `scripts/`.
Skills are distributed via the [Agent Skills](https://agentskills.io) standard (`npx skills add carpenter-singh-lab/catalog-skills`).

## How a skill is structured (progressive disclosure)

An agent loads a skill in three levels, so put each thing at the level where it is needed:

1. **Frontmatter `name` + `description`** - always in context. The `description` is the trigger: state what the skill does AND when to use it, and lean slightly pushy (agents under-trigger skills). All "when to use" lives here, not in the body.
2. **`SKILL.md` body** - loaded when the skill triggers. Keep it lean (well under ~500 lines): the procedure, the "why" the using-agent needs to behave well, and clear pointers into `references/`.
3. **`references/` and `scripts/`** - loaded or executed on demand. Operational depth and reusable scripts go here, not in the body.

## Editing rules

- **Keep `SKILL.md` lean; push depth to `references/`.** If a body grows past ~500 lines, add a reference file and point to it. Give reference files over ~300 lines a table of contents.
- **Explain the why, don't command.** Prefer imperative instructions and explain the reasoning; avoid walls of `ALWAYS`/`NEVER`. A model that understands why a step matters generalizes better than one following rote rules.
- **Bundle repeated work as a script.** If composing a notebook keeps regenerating the same procedure (lint, check, snapshot), it belongs in a skill's `scripts/` (e.g. `validate-notebook.sh`) - written once, not reinvented per run.
- **Each skill must be self-contained.** Do not reference a sibling skill's files by relative path - `npx skills add` can install one skill without the others.
- **Skills are dataset-agnostic.** Anything dataset-specific belongs in a catalog's `catalog.toml` manifest, never hardcoded here. If you are writing "JUMP" or "FinnGen" into a skill, it belongs in the manifest schema instead.
- **This collection is the single source of truth.** Catalogs install these skills rather than copy-pasting; a change here propagates by version bump, so do not let instance-specific drift back in.

## Iterating with skill-creator

For non-trivial changes - especially tuning a `description` for better triggering, or checking a revision actually helps - use the [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator) skill: it runs with-skill vs baseline evals, a human review loop, and a description optimizer. Reach for it rather than hand-tuning when a skill's behavior or triggering is in question.

## Conventions

Prose in `.md` files uses semantic line breaks (one sentence per line).
ASCII-only glyphs - hyphens, no em/en-dashes or arrows.
Conventional Commits (`feat:`, `fix:`, `docs:`, ...).
