#!/usr/bin/env bash
set -euo pipefail

write=false
if [[ "${1:-}" == "--write" ]]; then
  write=true
  shift
fi
if [[ $# -eq 0 ]]; then
  echo "usage: validate-notebook.sh [--write] NOTEBOOK.py [...]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MARIMO_PACKAGE="marimo==0.23.16"
RUFF_PACKAGE="ruff@0.16.2"
RUFF_RULES="E4,E7,E9,F"
BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/vignette-validator.XXXXXX")"
CURRENT_NOTEBOOK=""
CURRENT_NOTEBOOK_BACKUP=""
CURRENT_SESSION=""
CURRENT_SESSION_BACKUP=""
CURRENT_SESSION_EXISTED=false

remove_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

Path(sys.argv[1]).unlink(missing_ok=True)
PY
}

restore_current() {
  [[ -n "$CURRENT_NOTEBOOK" ]] || return 0
  cp -p "$CURRENT_NOTEBOOK_BACKUP" "$CURRENT_NOTEBOOK"
  if [[ "$CURRENT_SESSION_EXISTED" == true ]]; then
    mkdir -p "$(dirname "$CURRENT_SESSION")"
    cp -p "$CURRENT_SESSION_BACKUP" "$CURRENT_SESSION"
  else
    remove_path "$CURRENT_SESSION"
  fi
}

cleanup() {
  status=$?
  restore_current
  python3 - "$BACKUP_DIR" <<'PY'
from pathlib import Path
import shutil
import sys

shutil.rmtree(Path(sys.argv[1]), ignore_errors=True)
PY
  exit "$status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

ulimit -n "$(ulimit -Hn)" 2>/dev/null || true

index=0
for notebook in "$@"; do
  if [[ ! -f "$notebook" ]]; then
    echo "not found: $notebook" >&2
    exit 2
  fi

  session="$(dirname "$notebook")/__marimo__/session/$(basename "$notebook").json"
  CURRENT_NOTEBOOK="$notebook"
  CURRENT_NOTEBOOK_BACKUP="$BACKUP_DIR/notebook-$index.py"
  CURRENT_SESSION="$session"
  CURRENT_SESSION_BACKUP="$BACKUP_DIR/session-$index.json"
  CURRENT_SESSION_EXISTED=false
  cp -p "$notebook" "$CURRENT_NOTEBOOK_BACKUP"
  if [[ -f "$session" ]]; then
    cp -p "$session" "$CURRENT_SESSION_BACKUP"
    CURRENT_SESSION_EXISTED=true
  fi

  echo "==> marimo check: $notebook"
  if [[ "$write" == true ]]; then
    uvx "$MARIMO_PACKAGE" check --fix "$notebook"
  else
    uvx "$MARIMO_PACKAGE" check "$notebook"
  fi

  echo "==> ruff: $notebook"
  uvx "$RUFF_PACKAGE" check --select "$RUFF_RULES" "$notebook"
  if [[ "$write" == true ]]; then
    uvx "$RUFF_PACKAGE" format "$notebook"
  else
    uvx "$RUFF_PACKAGE" format --check "$notebook"
  fi

  echo "==> cold execution: $notebook"
  env -u PYTHONPATH uvx "$MARIMO_PACKAGE" export session \
    --sandbox \
    --force-overwrite \
    --no-continue-on-error \
    "$notebook"
  python3 "$SCRIPT_DIR/check-session.py" "$session"

  if [[ "$write" == true ]]; then
    echo "updated source formatting and session snapshot: $notebook"
  else
    restore_current
  fi
  CURRENT_NOTEBOOK=""
  index=$((index + 1))
done

echo "OK - static checks and cold execution passed for $# notebook(s)."
