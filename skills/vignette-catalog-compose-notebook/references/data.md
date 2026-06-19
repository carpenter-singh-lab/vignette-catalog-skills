# The data contract

The four-tier tree and one-direction flow carry over from the old lab workflow unchanged:

- `data/external/` - public prior knowledge cached locally
- `data/raw/` - as-delivered, immutable inputs
- `data/interim/` - tidy or derived tables you produced from a source
- `data/processed/` - analysis outputs (composed-notebook outputs and `summary.json` envelopes go here)

The test for where a file goes: did you *receive* it (raw) or *compute* it (interim/processed)?
Raw is immutable - never edit a raw file in place.

**Pin a SHA-256 on every fetched artifact.**
Use [pooch](https://www.fueled.com/the-cache/posts/python/pooch/) with `known_hash` so a CDN swap or silent upstream change is caught, not absorbed:

```python
pooch.retrieve(url=URL, known_hash="sha256:abe99e71a47b...", path="data/external/<source>", fname=NAME)
```

On first run pooch prints the hash; paste it into the constant and commit it.

**When the serialization is non-deterministic, pin the extracted content, not the raw bytes.**
Some sources re-serialize on every fetch even when the data has not changed: a Google Sheets / Docs export embeds an export timestamp, and zip and gzip carry mtimes and metadata.
Hashing the raw download then false-alarms download-to-download (two fetches seconds apart match; one an hour later does not).
Pin the SHA-256 of the *canonical extracted content* instead - the parsed table, or the values you actually consume - so the check fires on a real upstream change and ignores cosmetic churn.

**Cache large remote artifacts** under `~/.cache/<catalog>` with an env-var override (for example, `CATALOG_CACHE`); check the cache first, fall back to remote.
Commit small data (kilobytes); gitignore large data and the cache.

**Dataset-driven differences are intentional and explicit** - declare them in `catalog.toml`.
Use the `surface` field to choose the data access pattern:

| Surface | Use it for | Auth | Cache / data policy |
|---|---|---|---|
| `rest` | Live HTTP APIs via `httpx` or `requests` | Optional env var from `[auth]` | Prefer small, fresh responses; cache bulky or slow responses explicitly |
| `duckdb` | Local DuckDB databases or parquet-backed tables | Usually none, unless remote fetches need credentials | Cache large artifacts under `~/.cache/<catalog>` or the manifest's cache env var |
| `pooch` | Published files fetched by URL | Usually none | Store raw downloads under gitignored `data/`; require SHA-256 pins |
| `files` | Small delivered data committed directly to the repo | None | Commit the files and do not ignore `data/`; git is the integrity mechanism |

The `files` surface covers data committed straight into the repo - received once, version-controlled (small CSVs, a hand-transcribed plate map, a delivered table of kilobytes).
There is no fetch, no cache, and no pooch hash: git *is* the integrity mechanism, so do not gitignore `data/` (see the scaffold `.gitignore` note).
Choose it when the dataset is small and delivered rather than queried; reach for `rest`/`duckdb`/`pooch` only once the data is too large to commit.
