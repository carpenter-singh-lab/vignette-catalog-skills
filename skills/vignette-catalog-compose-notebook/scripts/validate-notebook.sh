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
NOTEBOOKS=("$@")
NOTEBOOK_BACKUPS=()
SESSIONS=()
SESSION_BACKUPS=()
SESSION_EXISTED=()
PRESERVE_CHANGES=false

remove_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

Path(sys.argv[1]).unlink(missing_ok=True)
PY
}

restore_all() {
  for index in "${!NOTEBOOK_BACKUPS[@]}"; do
    cp -p "${NOTEBOOK_BACKUPS[$index]}" "${NOTEBOOKS[$index]}"
    if [[ "${SESSION_EXISTED[$index]}" == true ]]; then
      mkdir -p "$(dirname "${SESSIONS[$index]}")"
      cp -p "${SESSION_BACKUPS[$index]}" "${SESSIONS[$index]}"
    else
      remove_path "${SESSIONS[$index]}"
    fi
  done
}

cleanup() {
  status=$?
  if [[ "$PRESERVE_CHANGES" != true ]]; then
    restore_all
  fi
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

for notebook in "${NOTEBOOKS[@]}"; do
  if [[ ! -f "$notebook" ]]; then
    echo "not found: $notebook" >&2
    exit 2
  fi
done

for index in "${!NOTEBOOKS[@]}"; do
  notebook="${NOTEBOOKS[$index]}"
  session="$(dirname "$notebook")/__marimo__/session/$(basename "$notebook").json"
  notebook_backup="$BACKUP_DIR/notebook-$index.py"
  session_backup="$BACKUP_DIR/session-$index.json"
  cp -p "$notebook" "$notebook_backup"
  session_existed=false
  if [[ -f "$session" ]]; then
    cp -p "$session" "$session_backup"
    session_existed=true
  fi
  NOTEBOOK_BACKUPS+=("$notebook_backup")
  SESSIONS+=("$session")
  SESSION_BACKUPS+=("$session_backup")
  SESSION_EXISTED+=("$session_existed")
done

for index in "${!NOTEBOOKS[@]}"; do
  notebook="${NOTEBOOKS[$index]}"
  session="${SESSIONS[$index]}"
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
  fi
done

PRESERVE_CHANGES="$write"
echo "OK - static checks and cold execution passed for $# notebook(s)."
