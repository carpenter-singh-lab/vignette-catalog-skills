#!/usr/bin/env bash
# Final mechanical gate for a composed or edited marimo notebook: lint, static-check,
# then execute it from a clean slate via marimo export. This is the CI-style check you
# run AFTER composing and looking in a live kernel (the marimo-pair skill) - not the
# feedback loop itself.
#
# Usage: bash validate-notebook.sh notebooks/<topic>.py
set -euo pipefail

NB="${1:?usage: validate-notebook.sh notebooks/<topic>.py}"

# Raise the open-file soft limit to the hard limit before any --sandbox provisioning.
# uv's parallel bytecode-compile can exceed a low soft limit (1024 on stock Ubuntu) and die
# with "Too many open files (os error 24)" - astral-sh/uv#16999. Clamping to $(ulimit -Hn)
# never exceeds the hard cap, so it cannot itself error under set -e. uv ships its own
# auto-raise (PR #17464, uv 0.9.26+) but it is gated behind the `adjust-ulimit` preview and
# off by default, so we still do it here. Drop this once that preview graduates to on-by-default.
ulimit -n "$(ulimit -Hn)" 2>/dev/null || true

# marimo check --fix first: it auto-resolves markdown-indentation (and other) warnings on
# mo.md cells. Running it BEFORE ruff format means ruff then formats the fixed output, and the
# export below runs after both - so the committed .py is clean and execution sees
# the final source.
echo "==> marimo check --fix ($NB)"
uvx marimo check --fix "$NB"

echo "==> ruff check + format ($NB)"
uvx ruff check "$NB"
uvx ruff format "$NB"

# Executing the notebook here surfaces runtime failures that static checks miss.
# env -u PYTHONPATH avoids the Nix websockets shim.
# --force-overwrite: without it, marimo SKIPS execution when a session snapshot is already
#   up-to-date and still exits 0 - so the gate would print "OK" without re-running a thing.
#   We always want a real cold execution here, so force it.
# --no-continue-on-error: this gate checks one notebook; a failing cell must fail the gate.
echo "==> execute notebook via marimo export (failure here is a real bug in the notebook)"
env -u PYTHONPATH uvx marimo export session --sandbox --force-overwrite --no-continue-on-error "$NB"

cat <<EOF

OK - mechanical gate passed: lint, static checks, and a clean from-scratch execution.

This is the final check, not the feedback loop. By now you should have composed this
notebook in a live kernel (the marimo-pair skill) and looked at every output - static
checks do not catch empty tables, wrong sign conventions, stale endpoints, or plots
that render but say nothing. If you have not yet looked at the outputs in a live kernel,
do that before calling the notebook done:

  PORT=\$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1])")
  env -u PYTHONPATH uvx marimo edit --sandbox --no-token --port \$PORT $NB

marimo may have written __marimo__/session/*.json as a local export artifact. Treat
those as gitignored generated files; commit them only when this repo intentionally
tracks snapshots for molab/static rendering (they can carry random widget ids and
create noisy diffs).
EOF
