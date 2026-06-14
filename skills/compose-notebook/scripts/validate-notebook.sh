#!/usr/bin/env bash
# Validate a composed or edited marimo notebook: lint, static-check, then execute and
# refresh its molab session snapshot. The mechanical half of the validation rule -
# you still have to open the notebook and look at the outputs afterward.
#
# Usage: bash validate-notebook.sh notebooks/<topic>.py
set -euo pipefail

NB="${1:?usage: validate-notebook.sh notebooks/<topic>.py}"
DIR="$(dirname "$NB")"

# marimo check --fix first: it auto-resolves markdown-indentation (and other) warnings on
# mo.md cells. Running it BEFORE ruff format means ruff then formats the fixed output, and the
# snapshot below is regenerated after both - so the committed .py is clean and its hash is stable.
echo "==> marimo check --fix ($NB)"
uvx marimo check --fix "$NB"

echo "==> ruff check + format ($DIR)"
uvx ruff check "$DIR"
uvx ruff format "$DIR"

# Snapshot must be regenerated AFTER the final source/formatter edit (above), or molab
# strips outputs on a code_hash mismatch. Executing the notebook here also surfaces
# runtime failures that static checks miss. env -u PYTHONPATH avoids the Nix websockets shim.
echo "==> execute + refresh molab session snapshot (failure here is a real bug in the notebook)"
env -u PYTHONPATH uvx marimo export session --sandbox "$NB"

cat <<EOF

OK - mechanical checks passed and the snapshot is refreshed.
Commit the regenerated __marimo__/session/*.json in the same change as the .py.

NOW open the notebook and inspect the outputs yourself. Static checks do not catch
empty tables, wrong sign conventions, stale endpoints, or plots that render but say nothing:

  PORT=\$(python -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1])")
  env -u PYTHONPATH uvx marimo edit --sandbox --headless --no-token --port \$PORT $NB
EOF
