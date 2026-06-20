#!/usr/bin/env bash
# Stop hook: red-team any changed notebook before the turn can end, and block the
# stop (surfacing the flags) if the reasoning review finds a problem. The harness
# runs this, not the composing agent, so the research-method check cannot be
# forgotten. Wire it from a catalog's .claude/settings.json:
#
#   { "hooks": { "Stop": [ { "hooks": [ { "type": "command",
#     "command": "bash .claude/skills/vignette-catalog-compose-notebook/scripts/red-team-on-stop.sh 2>/dev/null || true" } ] } ] } }
#
# Debounced by content hash: each notebook state is reviewed once, so it does not
# re-run on every stop and cannot loop (a fix changes the hash and earns a fresh
# review; an unchanged re-stop is allowed through).
set -euo pipefail
[ -n "${RED_TEAM_RUNNING:-}" ] && exit 0   # don't fire inside our own `claude -p`

RT="$(dirname "$0")/red-team-notebook.sh"
CACHE=".claude/.red-team-cache"
mkdir -p "$CACHE"

flags=""
for nb in $(git ls-files --others --exclude-standard 'notebooks/*.py' 2>/dev/null; \
            git diff --name-only 'notebooks/*.py' 2>/dev/null | sort -u); do
  [ -f "$nb" ] || continue
  h="$(sha256sum "$nb" | cut -d' ' -f1)"
  seen="$CACHE/${nb//\//_}.sha"
  [ "$(cat "$seen" 2>/dev/null)" = "$h" ] && continue   # ponytail: hash-debounce; also stops a re-flag loop
  out="$(bash "$RT" "$nb" 2>/dev/null || true)"
  echo "$h" > "$seen"
  echo "$out" | grep -q FLAG && flags="$flags"$'\n'"## $nb"$'\n'"$out"
done

[ -z "$flags" ] && exit 0
# Block the stop and feed the flags back into the model's attention.
python3 -c 'import json,sys; print(json.dumps({"decision":"block","reason":"Red-team flagged the notebook(s) against research-method.md; address each or explicitly justify before finishing:\n"+sys.argv[1]}))' "$flags"
