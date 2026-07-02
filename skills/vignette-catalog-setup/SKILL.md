---
name: vignette-catalog-setup
description: >-
  Set up an existing vignette catalog after clone by reading catalog.toml,
  checking uv and auth, installing marimo-pair, launching the first marimo
  notebook under --sandbox, registering a live kernel, and handing off to
  vignette-catalog-compose-notebook. Use when someone is in a catalog repo and
  asks to get started, set up, run the catalog, launch the first notebook, or
  prepare a live kernel. Do not use to create a new catalog; use
  vignette-catalog-scaffold for that.
allowed-tools: Bash, Read
---

# Set up a vignette catalog

Bring a freshly cloned catalog to a running marimo kernel, then hand off to composition.

## Steps

1. **Read the catalog manifest.**
   Read `catalog.toml` at the repo root for `first_notebook`, `auth` (any required env var), and the catalog name.
   If there is no `catalog.toml`, fall back to the lowest-numbered notebook in `notebooks/` and check `README.md` for auth.

2. **Check the runtime.**
   Confirm `uv` is installed (`uv --version`); if missing, install it:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Install the marimo-pair skill** for the user's agent (it is how you drive a live kernel):

   ```bash
   npx skills add marimo-team/marimo-pair -y
   ```

   The skills CLI auto-detects common agents; pass `--agent <agent>` only when the project needs an explicit target.
   Skip the add if marimo-pair is already installed - check the agent's skill stores first (e.g. `~/.claude/skills/marimo-pair` or the repo's `.claude/skills/`).

4. **Check auth if the manifest declares it.**
   Auth is required when `[auth].env_var` **or** `[auth].indirect_env_var` is non-empty; if both
   are empty (or there is no `[auth]`), the catalog is public - skip this step. Confirm the token
   is *obtainable*, not merely that some variable is set. Passing **either** probe satisfies
   auth: probe `env_var` first, and fall back to `indirect_env_var`.

   - **Direct token** (`env_var`, say `CATALOG_TOKEN`): passes if `$CATALOG_TOKEN` is non-empty
     in your shell, **or** if a `.env` at the repo root contains the key - notebooks commonly
     load `.env` in-process (dotenv), so a working token may never appear in the shell
     environment.
   - **Indirect reference** (`indirect_env_var`, say `CATALOG_OP_REF`): the named var holds a
     secret-manager reference the catalog resolves at runtime (e.g. an `op://` item read via the
     1Password CLI). Resolve the var's *value* - the reference string, which may itself arrive
     via a direnv `.envrc` or shell profile - once end-to-end:
     `op read "$CATALOG_OP_REF" >/dev/null && echo ok`. Two traps here: sandboxed agent shells
     block the IPC secret-manager CLIs use to reach their desktop app, so the probe fails
     instantly - rerun it unsandboxed; and resolution may pop an interactive unlock/biometric
     prompt on the user's screen - warn the user one may appear and allow well over 30 seconds
     before calling it failed.

   If no probe passes, stop: tell the user how to unblock (unlock the secret manager, or where to
   get a token - point to the catalog's README) and hand them the exact probe command so they can
   verify it themselves before you retry. Do not proceed on an unproven token.

5. **Launch the first notebook** in a sandbox, in the background, and remember the port.
   If step 4 required auth, the launch must carry the var you probed - direnv only hooks
   interactive shells, so a var exported by `.envrc` is invisible to the non-interactive shell an
   agent launches from; do not assume inheritance. Which var, and how:

   - **Indirect auth**: thread the *reference* var into the `env` prefix
     (`CATALOG_OP_REF="$CATALOG_OP_REF"`) - the notebook resolves it in-process, and the
     reference string is not the secret, so inlining it is safe. Do NOT resolve the secret
     yourself and thread the token.
   - **Direct token in the shell**: `export` it before launching and let the launch inherit it.
     Never inline the raw secret on the command line - it leaks into logs and the process table.
   - **Token only in `.env`**: thread nothing; the notebook loads `.env` from the repo root at
     runtime.

   ```bash
   PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1])")
   MARIMO_LOG="${TMPDIR:-/tmp}/marimo-$PORT.log"
   echo "marimo port: $PORT"
   echo "marimo log: $MARIMO_LOG"
   ulimit -n "$(ulimit -Hn)" 2>/dev/null || true   # see note below: avoids os error 24 on shared Linux hosts
   # auth catalogs: extend the env prefix per above, e.g. env -u PYTHONPATH CATALOG_OP_REF="$CATALOG_OP_REF" uvx ...
   env -u PYTHONPATH uvx marimo edit --sandbox --no-token --headless --port "$PORT" notebooks/<first_notebook> > "$MARIMO_LOG" 2>&1 &
   MARIMO_PID=$!
   echo "marimo pid: $MARIMO_PID"
   for _ in $(seq 1 60); do
       curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
       sleep 1
   done
   curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null
   ```

   `--sandbox` is required so the notebook's PEP 723 dependencies are provisioned.
   `env -u PYTHONPATH` avoids a Nix-shell websockets shim that crashes startup.
   The `ulimit` line raises the open-file soft limit to the hard limit before provisioning: on a
   busy shared Linux host uv's parallel bytecode-compile can exceed a low soft limit (1024 on stock
   Ubuntu) and die with `Too many open files (os error 24)` ([astral-sh/uv#16999](https://github.com/astral-sh/uv/issues/16999)).
   Clamping to `$(ulimit -Hn)` never exceeds the hard cap, so it is a no-op where the limit is already high (macOS) and harmless everywhere.
   The trailing `&` is load-bearing: the marimo server must keep running while the setup continues.
   Keep `$PORT` - the next step needs it.

   Whether to pass `--headless` depends on who is composing:

   - **A human is pairing and a browser is available.** Remove `--headless`. marimo auto-opens
     the browser; that frontend connection both gives the user a live notebook to look at and
     registers the kernel session that step 6 needs. Skip to step 6.
   - **You are an agent, or there is no browser** (a remote/SSH host, a CI box, an agent-driven
     run). Keep `--headless` and register the session yourself in the next step - nothing connects
     to the websocket on its own, so the server comes up with **no session** and the first
     `execute-code.sh` call would fail with `No active sessions on the server. Make sure a notebook
     is open in the browser.`

6. **Ensure a kernel session exists** (headless launch only - skip if a browser already opened).
   marimo creates a kernel *session* only when a frontend connects to its websocket. With no
   browser, register one yourself:

   - **A browser exists on the host but did not auto-open** (you launched `--headless` on a
     desktop): open the URL for the user and let their browser register the session -
     `open "http://localhost:$PORT"` on macOS, `xdg-open "http://localhost:$PORT"` on Linux.
   - **Truly headless** (no browser at all): run the bundled stand-in, which connects to the
     websocket the way the frontend does, waits for the kernel to report ready, and prints the
     session id:

     ```bash
     SESSION_ID=$(<vignette-catalog-setup-skill-dir>/scripts/register-session.py --port $PORT)
     echo "registered marimo session: $SESSION_ID"
     ```

   In `marimo edit` mode the session persists after the helper exits, so this one-shot call is
   enough - keep `$SESSION_ID` and target it with `execute-code.sh --url "http://127.0.0.1:$PORT"`
   (or `--session $SESSION_ID`). The helper takes `--token`/`MARIMO_TOKEN` for token-protected
   servers, and `--hold` for the rare server that drops the session on disconnect (RUN mode or
   `--session-ttl`); plain `marimo edit` needs neither. Confirm with
   `curl -s http://127.0.0.1:$PORT/api/sessions` that a session is now listed.

7. **Run every cell, then confirm the kernel is populated.**
   marimo only auto-runs cells when a browser frontend connects, so a freshly launched kernel
   can sit with all cells stale and every notebook variable undefined. Do not rely on the
   browser - run the cells explicitly through the marimo-pair `execute-code.sh` script you installed
   in step 3, targeting `--url "http://127.0.0.1:$PORT"`:

   ```bash
   bash <marimo-pair-skill-dir>/scripts/execute-code.sh --url "http://127.0.0.1:$PORT" <<'EOF'
   import marimo._code_mode as cm

   async with cm.get_context() as ctx:
       for cell in ctx.cells:
           ctx.run_cell(cell.id)
   EOF
   ```

   This uses marimo-pair's documented code-mode path inside the running kernel; it is not local
   Python.
   Then spot-check that the kernel is genuinely usable before handing off - prefer one cheap call
   that exercises the full chain (an authenticated request through a catalog helper, or the shape
   of the notebook's main table) over merely printing a variable. An empty, unexecuted kernel and
   a half-proven auth path are the two most common "it didn't work"; this is the only step that
   proves the whole chain end-to-end.

8. **Hand off.**
   Tell the user the kernel is running on `$PORT` (and, if you registered one, that a session is
   live - the notebook is open in their browser when a browser was used) and that they can now
   ask a question - the `vignette-catalog-compose-notebook` skill takes it from here.
   This kernel runs the *first* notebook in its own `--sandbox` and is bound to that notebook.
   Hand off the port, but do not promise it serves every notebook: composing a new notebook gets
   its own `--sandbox` kernel (a relaunch of step 5 on that notebook), which
   `vignette-catalog-compose-notebook` handles.

## Stopping a kernel

When you need to tear down a kernel you launched (end of an agent run, or before relaunching on
another notebook), stop the one you started - **by its `$PORT`, never with a broad `pkill`**.
`uvx marimo edit --sandbox` is a 4-process tree (`uvx` -> python -> `uv run` -> python), so killing
the recorded `$MARIMO_PID` alone orphans the `uv run` grandchild that actually serves the socket;
and on a shared host `pkill -f marimo` kills other users' kernels and your own shell wrapper. Match
the listener on the port and kill its whole process group:

```bash
PGID=$(ps -o pgid= -p "$(lsof -ti tcp:$PORT -s tcp:LISTEN | head -1)" 2>/dev/null | tr -d ' ')
[ -n "$PGID" ] && kill -TERM -"$PGID"
curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && echo "still up - retry with kill -9 -$PGID" || echo "kernel on $PORT stopped"
```

This is why step 5 records `$MARIMO_PID` and `$PORT`: keep them for the run so teardown targets
exactly your kernel and nothing else.

## Notes

- Public catalogs often need no auth; private or authenticated catalogs declare their required env var in `catalog.toml`.
- Do not improvise alternative launch commands; the `--sandbox` flag is what makes per-notebook dependencies work.
- Do not improvise the headless session bootstrap either - the `scripts/register-session.py` stand-in is the supported way to register a kernel session without a browser. It exists so each agent does not re-derive a websocket client from scratch. Run it as an executable (the bare path in step 6) - its shebang provisions `websockets` via `uv run`. Invoking it as `python3 register-session.py` skips that and fails with `ModuleNotFoundError: websockets`; if a checkout dropped the executable bit, `chmod +x` it rather than reaching for `python3`.
- `execute-code.sh` also accepts `--port "$PORT"`, which goes through registry discovery - but discovery is occasionally flaky (especially with several servers up) and then reports `No running marimo instances found` while the server is healthy. `--url "http://127.0.0.1:$PORT"` (as used in step 7) skips discovery entirely; it is the default here because it is the reliable path for an agent.
- If the repo gitignores its skill stores (tracks only `skills-lock.json`) and the catalog skills look missing or stale, restore them - but **not** with `npx skills update`. `update` only refreshes agent stores that **already exist on disk** and has no `--agent` flag (only `-g`/`-p`/`-y`): on a fresh clone it materializes the Universal store (`.agents/`) but not an agent-specific one like Claude Code's `.claude/skills/`, so the skills can look installed while the agent sees nothing. The only command that targets a specific store is `npx skills add <source> --agent <agent> -y` (e.g. `--agent claude-code`; comma-separate or `*` for several). Once that store exists, `update` will maintain it. Either way this is a refresh once you can run a command in the repo - it is **not** the clone-time bootstrap: a cloner who has *no* catalog skills on disk cannot reach this skill to run that step, so the post-clone restore lives in the repo's tracked `AGENTS.md` / `README.md`, not here, since a skill cannot bootstrap its own install.
