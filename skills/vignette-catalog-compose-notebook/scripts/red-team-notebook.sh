#!/usr/bin/env bash
# Adversarial reasoning review of a composed notebook against research-method.md.
# Fires a fresh `claude -p` sub-agent so the check runs OUTSIDE the composing
# agent's own attention - the reasoning analog of validate-notebook.sh (which is
# only lint). Prints the reviewer's verdict to stdout.
set -euo pipefail
NB="${1:?usage: red-team-notebook.sh <notebook.py>}"
METHOD="$(dirname "$0")/../references/research-method.md"
command -v claude >/dev/null || { echo "red-team: claude CLI not found" >&2; exit 2; }
[ -f "$METHOD" ] || { echo "red-team: research-method.md not found at $METHOD" >&2; exit 2; }

# Guard: the inner `claude -p` runs its own Stop hooks; this env var tells
# red-team-on-stop.sh to no-op so we do not recurse.
export RED_TEAM_RUNNING=1

{
  cat <<'ASK'
You are an adversarial reviewer. Below are research-method principles and a research notebook.
For EACH task/section in the notebook, check and cite the specific cell or line:
- #13 self-confirming model: does an "experiment" just re-run the author's own model instead of independent data?
- #14 consensus-as-finding: is a result foregrounded that the author would have predicted before looking? Is one well-known fact echoing across sections and read as convergence?
- #10 unstated instrument limits; #3 uncalibrated confidence; #7 unverified load-bearing claims.
Output one line per task: PASS or FLAG + one-line evidence. End with "BIGGEST RISK: ...".
Be terse and specific; do not restate the notebook.
ASK
  echo "=== RESEARCH METHOD ==="
  cat "$METHOD"
  echo "=== NOTEBOOK ==="
  cat "$NB"
} | claude -p --model claude-opus-4-8
