# Notebook conventions

This is the **canonical** statement of the catalog notebook and data conventions.
The `scaffold-catalog` skill's `templates.md` reproduces a scaffold-time subset of it; if the two diverge, this file wins.

**Naming:** `nbNN_<topic>.py`, two-digit zero-padded (`nb01_retrieve_profiles.py`).
The `nb` prefix is not decoration - Python cannot import a module whose name starts with a digit, so `nbNN_` makes the file a valid importable module.
Composed (non-catalog) notebooks can use a plain `<topic>.py` name.

**Dependencies:** PEP 723 inline metadata per notebook, not a shared lockfile.

```python
# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = ["marimo", "polars", "altair"]
# ///
```

Pin the upper bound `<3.14` whenever the notebook uses altair (altair 5.5+ trips `TypedDict(closed=True)` on Python 3.14).
Pin exact versions for scientific deps you have validated (e.g. `polars==1.40.1`, `rdkit==2024.9.6`).

**Structure:**

- a `with app.setup:` block holds shared imports, constants, auth, and `sys.path` setup
- top-level `@app.function` helpers are the reusable contract (pure, importable)
- `@app.cell` blocks hold narrative plus the worked example

Shared paths and constants live in the setup block of the lowest-numbered (orientation) notebook and are imported by later notebooks - do not add a separate `config` notebook or module.
The orientation notebook *is* the config; a dedicated config notebook is a holdover from the old cookiecutter layout.

**Cross-notebook imports:** add `notebooks/` to the path in the setup block, then import as plain Python.

```python
with app.setup:
    import sys
    from pathlib import Path
    NOTEBOOK_DIR = Path(__file__).resolve().parent
    if str(NOTEBOOK_DIR) not in sys.path:
        sys.path.insert(0, str(NOTEBOOK_DIR))
    from nb01_retrieve_profiles import load_profiles  # noqa: E402
```

Importing a helper inherits that notebook's whole dependency set - if `nb06` imports from `nb04`, `nb06` needs `nb04`'s deps even if it never calls them.

**Runtime:** uv, always. Launch with `--sandbox` so the PEP 723 block is provisioned:

```bash
uvx marimo edit --sandbox notebooks/nbNN_*.py
```

Do not improvise alternative launch commands. Do not add Nix or pixi to a catalog without a concrete reason.

**ruff** (identical across all catalogs; lives in `pyproject.toml`):

```toml
[tool.ruff]
line-length = 120

[tool.ruff.lint.per-file-ignores]
"notebooks/nb*.py" = ["B018", "F401", "F821", "F841"]
```

The ignores are marimo boilerplate: `B018` (bare expressions render intentionally), `F401` (cross-notebook helpers imported but unused locally), `F821` (names visible only via the setup cell), `F841` (cell-private scratch).
There is no `[project]` table - a catalog is not an installable package.

**Markdown** prose uses semantic line breaks (one sentence per line); the `line-length = 120` rule is Python only.
ASCII-only glyphs.

**End every catalog vignette with a "## To extend" section** - two or three concrete next questions.
