Before working in this repository, read and follow `CONSTITUTION.md`.
Direct user instructions and the more specific instructions in this file override it.

# AGENTS.md - vignette-catalog-skills

Guidance for agents working **on this repository** (authoring and editing the skills themselves).
To work in a catalog that has these skills installed, read the installed skill, not this file.

## What this repo is

An installable collection of agent skills for the vignette-catalog method.
`README.md` is the human entry point and conceptual orientation.
Each skill under `skills/<name>/` is self-contained: a `SKILL.md` plus its own assets, references, and scripts where useful.
Skills are distributed via the [Agent Skills](https://agentskills.io) standard (`npx skills add carpenter-singh-lab/vignette-catalog-skills`).

## Agent skill used to develop this repo

The project-local `marimo-pair` dependency is recorded in `skills-lock.json` and installed into gitignored directories.
After cloning, run `npx skills@1.5.20 add 'shntnu/marimo-pair#pr69-9528681' -s marimo-pair -a claude-code -a codex -y` from the repo root.
That fork tag points to upstream commit `95286810f2101f29d370859159a00a39452e78c8` because the pinned installer cannot clone a raw commit as a ref.
The lock records the ref and observed hash but not agent targets; replay the command to update and inspect `git diff -- skills-lock.json` before committing an intentional upstream change.

## Where things go in a skill

A skill loads in three levels; put each thing where it is reached:

- **Frontmatter `name` + `description`** - always in context; the `description` is the trigger (what the skill does AND when to use it).
- **`SKILL.md` body** - loaded on trigger; the procedure and pointers into `references/`.
  Keep it lean (well under ~500 lines).
- **`references/` and `scripts/`** - loaded or executed on demand; operational depth and reusable scripts (e.g.
  `validate-notebook.sh`), not inlined in the body.

## Invariants specific to this collection

These hold no matter which agent is editing, and their failure mode ships silently to every consumer - so they live here rather than in any general guide:

- **Each skill is self-contained.** Do not reference a sibling skill's files by relative path - `npx skills add` can install one skill without the others.
- **Skills are dataset-agnostic.** Anything dataset-specific belongs in a catalog's `catalog.toml`, never hardcoded here.
  Writing "JUMP" or "FinnGen" into a skill is a smell - extend the manifest schema instead.
- **This collection is the single source of truth.** Catalogs install these skills rather than copy them; a change here propagates by version bump, so do not let instance-specific drift back in.

## Authoring and iterating: use skill-creator

For the craft of writing a skill - how to structure it, tune a `description` for triggering, or check that a revision actually helps (with-skill vs baseline evals, a human review loop, a description optimizer) - use the [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator) skill rather than restating its methodology here.
The floor that always applies, even when skill-creator is not at hand: prefer imperative instructions, explain the *why* behind a step (a model that understands generalizes better than one following rote `ALWAYS`/`NEVER`), and bundle repeated work into a `scripts/` file instead of reinventing it per run.

## Conventions

Prose in `.md` files uses semantic line breaks (one sentence per line).
ASCII-only glyphs - hyphens, no em/en-dashes or arrows.
Conventional Commits (`feat:`, `fix:`, `docs:`, ...).

The collection intentionally exposes only two user-facing skills: work in an existing catalog, or scaffold one.
Skill names use the shared `vignette-catalog-*` namespace.
Keep the folder name and frontmatter `name` identical, and put the precise trigger and boundary in `description`.

<!-- BEGIN KATA (managed by `kata init --with-agents`) -->
Kata is the system of record for intent.

- Never `kata delete` or `kata purge` without explicit user authorization.

~~~dot
digraph kata {
  rankdir=TB; node [shape=box];

  arrive   [shape=diamond label="Work arrives"];
  search   [label="Search first; reuse an open issue\nor create one"];
  route    [shape=diamond label="Work it, or delegate it?"];

  subgraph cluster_work {
    label="Working a kata-tracked issue";
    claim  [label="On claim or start, mark it actively tracked:\nkata meta set <ref> work.attention ok\nIn-flight work becomes visible to coordinators\nand dashboards from the moment it is grabbed."];
    branch [label="If the work happens on a dedicated branch, stamp it once:\nkata meta set <ref> work.branch <branch>\nor bind at creation:\nkata create ... --meta work.branch=<branch> --idempotency-key <key>"];
    live   [label="Keep your live state truthful on the issue:\nkata meta set <ref> work.attention stuck|needs-human|ok\nwith a one-line kata meta set <ref> work.attention_msg \"<why>\"\nRaise stuck when you cannot proceed, needs-human when you want\ninput or review (you may keep working), and clear back to ok\nwhen unblocked."];
    claim -> branch -> live;
  }

  subgraph cluster_delegate {
    label="Delegating work as separate issues (fan-out/join)";
    fanout [label="Create each delegated child with\n--parent <epic-or-coordinating-issue>,\n--meta work.branch=..., and an idempotency key;\ncapture refs from --json (.issue.short_id).\nAdd dependency links only for actual prerequisites."];
    join   [label="Join with kata wait <refs> --until attention --any\nMatches needs-human or stuck; a close also completes the wait,\nand the reported reason distinguishes which. Use --timeout so a\nwrapper can tell timeout from satisfaction."];
    coord  [label="As coordinator you read work.* -\nyou never write it on issues you delegated."];
    fanout -> join -> coord;
  }

  done     [shape=diamond label="Verified complete?"];
  close    [label="kata close <ref> --done\nwith a message and evidence"];
  review   [label="kata label add <ref> needs-review\nplus a comment on what remains"];
  park     [shape=diamond label="Park it?"];
  schedule [label="kata schedule <ref> <date-or-time>\nsets scheduled_on; clear with -"];
  someday  [label="kata meta set <ref> someday true --json-value\nclear with kata meta unset <ref> someday"];

  arrive -> search -> route;
  route -> claim   [label="work it"];
  route -> fanout  [label="delegate it"];
  route -> park    [label="record only"];
  live  -> done;
  coord -> done;
  done -> close    [label="yes"];
  done -> park     [label="no, stopping"];
  park -> schedule [label="start date known"];
  park -> someday  [label="no date"];
  park -> review   [label="no"];

  always [shape=note label="Always: one writer per key. work.* on closed issues is meaningless -\nnever write it there, ignore it when reading. Never end a session with\nthe signal stale: before stopping, either close the issue or set the\nattention pair to reflect the hand-off."];

  relationships [shape=note label="Relationships: Parent links express containment and roll-up only;\nthey do not gate readiness, and a parent cannot close with open children.\nUse --blocks <dependent> / --blocked-by <prerequisite>\nonly for real prerequisites; those links gate kata ready.\nUse --related <ref> for context only.\nkata wait observes state; it does not require a dependency edge."];

  gate [shape=note label="A future scheduled_on or someday=true keeps an issue\nout of ready and next. kata deadline <ref> <date-or-time>\nsets deadline_on, which never gates either."];
}
~~~
<!-- END KATA -->
