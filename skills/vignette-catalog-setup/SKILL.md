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

4. **Check auth if the manifest declares it.**
   If `auth` names an env var, confirm a `.env` exists and the var is set.
   If not, stop and tell the user how to get the token (point to the catalog's README); do not proceed.

5. **Launch the first notebook** in a sandbox, in the background, and remember the port:

   ```bash
   PORT=$(python -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1])")
   echo "marimo port: $PORT"
   env -u PYTHONPATH uvx marimo edit --sandbox --no-token --port $PORT notebooks/<first_notebook>
   ```

   `--sandbox` is required so the notebook's PEP 723 dependencies are provisioned.
   `env -u PYTHONPATH` avoids a Nix-shell websockets shim that crashes startup.
   Run it in the background so it does not block, and keep `$PORT` - the next step needs it.

   Whether to pass `--headless` depends on who is composing:

   - **A human is pairing and a browser is available.** Omit `--headless`. marimo auto-opens
     the browser; that frontend connection both gives the user a live notebook to look at and
     registers the kernel session that step 6 needs. Skip to step 6.
   - **You are an agent, or there is no browser** (a `--headless` server on a remote/SSH host,
     a CI box, an agent-driven run). Pass `--headless` and register the session yourself in the
     next step - nothing connects to the websocket on its own, so the server comes up with **no
     session** and the first `execute-code.sh` call would fail with `No active sessions on the
     server. Make sure a notebook is open in the browser.`

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
   enough - keep `$SESSION_ID` and target it with `execute-code.sh --port $PORT` (or
   `--session $SESSION_ID`). The helper takes `--token`/`MARIMO_TOKEN` for token-protected
   servers, and `--hold` for the rare server that drops the session on disconnect (RUN mode or
   `--session-ttl`); plain `marimo edit` needs neither. Confirm with
   `curl -s http://127.0.0.1:$PORT/api/sessions` that a session is now listed.

7. **Run every cell, then confirm the kernel is populated.**
   marimo only auto-runs cells when a browser frontend connects, so a freshly launched kernel
   can sit with all cells stale and every notebook variable undefined. Do not rely on the
   browser - run the cells explicitly via the marimo-pair scripts you installed in step 3
   (`scripts/execute-code.sh`, targeting `--port $PORT`):

   ```python
   import marimo._code_mode as cm
   async with cm.get_context() as ctx:
       for c in ctx.cells:
           ctx.run_cell(c.id)
   ```

   Then spot-check that a key variable resolved (e.g. print the shape of the notebook's main
   table) before handing off. An empty, unexecuted kernel is the most common "it didn't work".

8. **Hand off.**
   Tell the user the kernel is running on `$PORT` (and, if you registered one, that a session is
   live - the notebook is open in their browser when a browser was used) and that they can now
   ask a question - the `vignette-catalog-compose-notebook` skill takes it from here.

## Notes

- Public catalogs often need no auth; private or authenticated catalogs declare their required env var in `catalog.toml`.
- Do not improvise alternative launch commands; the `--sandbox` flag is what makes per-notebook dependencies work.
- Do not improvise the headless session bootstrap either - the `scripts/register-session.py` stand-in is the supported way to register a kernel session without a browser. It exists so each agent does not re-derive a websocket client from scratch.
- If the repo gitignores its skill stores (tracks only `skills-lock.json`) and the catalog skills look missing or stale, `npx skills update` reconstitutes them from the lock. This is a refresh once the skills are already present - it is **not** the clone-time bootstrap. A cloner who has *no* catalog skills on disk cannot reach this skill to run that step; the post-clone restore therefore lives in the repo's tracked `AGENTS.md` / `README.md`, not here, since a skill cannot bootstrap its own install.
