---
name: getting-started
description: >-
  First-run setup for a vignette catalog (jx, fgx, prx, dmx, or any catalog
  built on the catalog-skills pattern). Use when someone has just cloned a
  catalog repo and asks to "get started", "set up", or "help me run this", or
  when a marimo catalog needs its prerequisites installed and a first notebook
  launched in a live kernel.
allowed-tools: Bash, Read
---

# Getting started in a catalog

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
   npx skills add marimo-team/marimo-pair --agent claude-code -y
   ```

4. **Check auth if the manifest declares it.**
   If `auth` names an env var (e.g. `FINNGENIE_TOKEN`), confirm a `.env` exists and the var is set.
   If not, stop and tell the user how to get the token (point to the catalog's README); do not proceed.

5. **Launch the first notebook** in a headless sandbox and confirm the kernel is ready:

   ```bash
   PORT=$(python -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1])")
   env -u PYTHONPATH uvx marimo edit --sandbox --headless --no-token --port $PORT notebooks/<first_notebook>
   ```

   `--sandbox` is required so the notebook's PEP 723 dependencies are provisioned.
   `env -u PYTHONPATH` avoids a Nix-shell websockets shim that crashes startup.

6. **Hand off.**
   Tell the user the kernel is running and that they can now ask a question - the `compose-notebook` skill takes it from here.

## Notes

- Public catalogs (e.g., jx, prx, dmx) need no auth, where some do, e.g., fgx needs `FINNGENIE_TOKEN`.
- Do not improvise alternative launch commands; the `--sandbox` flag is what makes per-notebook dependencies work.
