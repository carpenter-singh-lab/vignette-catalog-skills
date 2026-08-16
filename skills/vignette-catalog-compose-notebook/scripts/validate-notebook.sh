#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "usage: validate-notebook.sh NOTEBOOK.py [...]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUFF_RULES="E4,E7,E9,F"

ulimit -n "$(ulimit -Hn)" 2>/dev/null || true

for notebook in "$@"; do
  if [[ ! -f "$notebook" ]]; then
    echo "not found: $notebook" >&2
    exit 2
  fi

  echo "==> marimo check: $notebook"
  uvx marimo check --fix "$notebook"

  echo "==> ruff: $notebook"
  uvx ruff@0.16.2 check --select "$RUFF_RULES" "$notebook"
  uvx ruff@0.16.2 format "$notebook"

  echo "==> cold execution: $notebook"
  env -u PYTHONPATH uvx marimo export session \
    --sandbox \
    --force-overwrite \
    --no-continue-on-error \
    "$notebook"

  session="$(dirname "$notebook")/__marimo__/session/$(basename "$notebook").json"
  python3 "$SCRIPT_DIR/check-session.py" "$session"
done

echo "OK - static checks and cold execution passed for $# notebook(s)."
