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

- `vignette-catalog-setup` reads `[getting_started].first_notebook` and `[auth].env_var`.
- `vignette-catalog-compose-notebook` reads the `[[vignette]]` table to pick which notebooks to import, and `[data]`/`[auth]` to know the surface.
- `vignette-catalog-scaffold` writes the initial `catalog.toml` and adds a `[[vignette]]` row when a composed notebook is promoted.

Keep `catalog.toml` the single source of the vignette table.
Do not duplicate the table into a skill or hardcode dataset names into the skills - if you are tempted to, the manifest schema is the place to extend instead.
