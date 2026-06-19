# AGENTS.md - vignette-catalog-skills

Guidance for agents working **on this repository** (authoring and editing the skills themselves).
To work in a catalog that has these skills installed, read the installed skill, not this file.

## What this repo is

An installable collection of agent skills for the vignette-catalog method.
`README.md` is the human entry point and conceptual orientation.
Each skill under `skills/<name>/` is self-contained: a `SKILL.md` (frontmatter + body) plus its own `references/` and, where useful, `scripts/`.
Skills are distributed via the [Agent Skills](https://agentskills.io) standard (`npx skills add carpenter-singh-lab/vignette-catalog-skills`).

## Where things go in a skill

A skill loads in three levels; put each thing where it is reached:

- **Frontmatter `name` + `description`** - always in context; the `description` is the trigger (what the skill does AND when to use it).
- **`SKILL.md` body** - loaded on trigger; the procedure and pointers into `references/`. Keep it lean (well under ~500 lines).
- **`references/` and `scripts/`** - loaded or executed on demand; operational depth and reusable scripts (e.g. `validate-notebook.sh`), not inlined in the body.

## Invariants specific to this collection

These hold no matter which agent is editing, and their failure mode ships silently to every consumer - so they live here rather than in any general guide:

- **Each skill is self-contained.** Do not reference a sibling skill's files by relative path - `npx skills add` can install one skill without the others.
- **Skills are dataset-agnostic.** Anything dataset-specific belongs in a catalog's `catalog.toml`, never hardcoded here. Writing "JUMP" or "FinnGen" into a skill is a smell - extend the manifest schema instead.
- **This collection is the single source of truth.** Catalogs install these skills rather than copy them; a change here propagates by version bump, so do not let instance-specific drift back in.

## Authoring and iterating: use skill-creator

For the craft of writing a skill - how to structure it, tune a `description` for triggering, or check that a revision actually helps (with-skill vs baseline evals, a human review loop, a description optimizer) - use the [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator) skill rather than restating its methodology here.
The floor that always applies, even when skill-creator is not at hand: prefer imperative instructions, explain the *why* behind a step (a model that understands generalizes better than one following rote `ALWAYS`/`NEVER`), and bundle repeated work into a `scripts/` file instead of reinventing it per run.

## Conventions

Prose in `.md` files uses semantic line breaks (one sentence per line).
ASCII-only glyphs - hyphens, no em/en-dashes or arrows.
Conventional Commits (`feat:`, `fix:`, `docs:`, ...).

Skill names in this collection use the shared `vignette-catalog-*` namespace.
Keep the folder name and frontmatter `name` identical, and put the precise trigger and boundary in `description`.
