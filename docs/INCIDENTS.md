# Incident ledger

This file preserves why behavior exists without loading every workaround into the skills.
A rule belongs in a `SKILL.md` only when an agent must make a decision; deterministic handling belongs in scripts or tests.

| Failure evidence | Retained behavior | Location |
|---|---|---|
| Issues #1 and PR #2: agents claimed live composition while using only headless export | Compose and inspect through a real live kernel | Compose workflow and live-session evals |
| Issue #3: headless marimo started with no kernel session | Register a session after launch | `scripts/catalog-session.py` |
| PR #4: stale scaffold targets and more than 30 orphan kernels | Refuse non-empty targets and stop only the recorded process group | Scaffold and session scripts |
| PR #5: dataset meaning was not captured by file integrity | Read catalog-declared caveats | Compose workflow; caveats remain catalog-local |
| Issue #6 and PR #7: mutable REST and `latest` identifiers re-anchored results | Read and report the catalog's version contract | `catalog.toml` and catalog-local instructions |
| Issue #8: Ruff 0.16 expanded defaults and broke every catalog before execution | Pin Ruff and select the stable E/F correctness rules explicitly | `scripts/validate-notebook.sh` and scaffold asset |
| August 2026 audit: marimo printed failed cells but exited zero | Inspect exported session JSON for cell errors | `scripts/check-session.py` |
| Three-surface evaluations repeatedly required headless launch, health checks, and teardown | Execute the protocol once instead of restating it | `scripts/catalog-session.py` |
| Iteration 1 resolved installed scripts from the catalog root and bypassed a dependency-bearing shebang | State that paths are skill-relative and execute Python helpers directly | Compose workflow |
| Iteration 1 let uv discover the catalog project, creating `.venv` and `uv.lock` | Run the session helper under `uv --no-project` | `scripts/catalog-session.py` |
| Concurrent iteration 1 runs could stop an unrelated listener through an `lsof` fallback | Scope state to the catalog and stop only its recorded marimo process | `scripts/catalog-session.py` |
| PR #9 review: concurrent starts overwrote state and left an orphan server | Serialize each catalog-port launch and write state atomically | `scripts/catalog-session.py` and regression tests |
| PR #9 review: stale state could target a replacement process after PID reuse | Require a unique launch marker in addition to PID, birth time, command, notebook, and port | `scripts/catalog-session.py` and regression tests |
| PR #9 review: validation rewrote source and snapshots before proving success | Restore both by default and make `--write` transactional | `scripts/validate-notebook.sh` and regression tests |
| PR #9 review: scaffolding nested Git repositories and interpolated unchecked names | Prevalidate rendered assets and initialize Git only outside an existing worktree | Scaffold script and regression tests |
| PR #9 review: indirect auth was ignored and comment-only dotenv values passed | Validate both auth declarations and parse dotenv comments | `scripts/catalog-session.py` and regression tests |
| HCMI static checks passed semantically wrong outputs | Inspect real tables and rendered figures before the cold gate | Compose workflow |
| `summary.json` and an index notebook were materially used only by dmx | Do not impose indexing on every catalog | Removed from the shared contract |
| The automatic research red-team hook had no retained cache evidence across five audited catalogs | Keep research review outside this mechanical catalog skill | Hook and generic research method removed |
| A fresh YNAB worktree could not discover installed skills | Put exact restoration commands in tracked project guidance | Scaffolded `AGENTS.md`, not a self-bootstrap rule |
| ks3p: a run-only request took ~15 minutes because the compose workflow loaded research context, hand-rolled tunnels, and re-proved session state | Route by request class; run-only requests follow a fast path with one deterministic `open` command | `SKILL.md` routing and `scripts/catalog-session.py` |
| ks3p: a healthy registered session could still hold only never-run cells | `open` and `run` execute cells, wait for a terminal state, and report an explicit cell summary; readiness is never claimed without it | `scripts/catalog-session.py` and regression tests |
| ks3p: sessions bound only to 127.0.0.1 forced SSH tunnels even when the user could reach the host directly | `--host` and `--url-host` separate the bind address from the reported URL | `scripts/catalog-session.py` and the fast path |
| ks3p: a stale server could outlive a moved or trashed worktree and stay invisible from surviving checkouts | `status` lists sessions recorded by other roots; `status`/`stop` accept `--root` | `scripts/catalog-session.py` and regression tests |
| ks3p: rerunning kernel cells after an external file edit would prove old code while appearing to prove the new file | File divergence is reported with a note and never triggers a silent rerun; recorded run evidence is preserved | `scripts/catalog-session.py` and regression tests |

## Add-back test

Add shared guidance only when all of the following hold:

1. A real task fails without it.
2. The failure recurs independently, or one occurrence has severe consequences.
3. A script, schema, test, or catalog-local instruction cannot handle it more reliably.
4. It belongs to the shared catalog workflow rather than one dataset or notebook.

When a candidate revision fails an evaluation, add back the smallest mechanism that addresses that failure and rerun the old-versus-new comparison.
