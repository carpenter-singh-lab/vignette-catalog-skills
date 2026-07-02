# The catalog.toml manifest

The skills in this collection are shared and dataset-agnostic.
Each catalog declares its specifics in a `catalog.toml` at its repo root.
This is what lets every catalog install the same skills instead of forking them - shared procedure, instance-local data.

```toml
name = "example-catalog"
description = "Exploration catalog for one dataset"

[data]
surface = "duckdb"        # one of: rest | duckdb | pooch | files
cache = "$CATALOG_CACHE"  # env var or path for large cached artifacts; omit if none

[auth]
env_var = ""              # required token var; empty = public
indirect_env_var = ""     # optional: var holding a secret-manager reference (e.g. an op:// item) the catalog resolves at runtime; omit if none

[getting_started]
first_notebook = "nb01_orientation.py"

# one [[vignette]] block per catalog notebook - this is the table vignette-catalog-compose-notebook reads
[[vignette]]
notebook = "nb01_orientation.py"
helpers  = ["fetch_records", "summarize_records"]
does     = "Orientation: reach the dataset and summarize one representative query"

[[vignette]]
notebook = "nb02_compare_groups.py"
helpers  = ["load_feature_matrix", "compare_groups", "plot_group_effects"]
does     = "Compare a feature across two user-defined groups"
```

How the skills use it:

- `vignette-catalog-setup` reads `[getting_started].first_notebook` and `[auth]` - auth is required when either `env_var` or `indirect_env_var` is non-empty, and passing either probe satisfies it (`env_var` first, `indirect_env_var` as fallback). An accepted alternative auth path belongs in `indirect_env_var`, not in a TOML comment, so setup can see it.
- `vignette-catalog-compose-notebook` reads the `[[vignette]]` table to pick which notebooks to import, and `[data]`/`[auth]` to know the surface.
- `vignette-catalog-scaffold` writes the initial `catalog.toml` and adds a `[[vignette]]` row when a composed notebook is promoted.

Keep `catalog.toml` the single source of the vignette table.
Do not duplicate the table into a skill or hardcode dataset names into the skills - if you are tempted to, the manifest schema is the place to extend instead.
