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

**Cache large remote artifacts** under `~/.cache/<catalog>` with an env-var override (e.g. `JX_CACHE`); check the cache first, fall back to remote.
Commit small data (kilobytes); gitignore large data and the cache.

**Dataset-driven differences are intentional and explicit** - declare them in `catalog.toml`. For reference, the four live catalogs:

| Catalog | Data surface | Auth | Cache / data policy |
|---|---|---|---|
| jx | DuckDB metadata, parquet profiles, S3 images, Zenodo matrices | Public, no secret | Cache large artifacts under `~/.cache/jx` or `$JX_CACHE` |
| fgx | FinnGenie `/api/v1/*` REST via `httpx` | `FINNGENIE_TOKEN` in local `.env` | Live API reads; no committed cache |
| prx | Bond et al. 2025 Figshare/Dryad via `pooch` | Public, no secret | Raw downloads under gitignored `data/`; SHA-256 pinned |
| dmx | DepMap Breadbox REST via `requests` | Public read-only, no key | Live API reads; summarize large responses before display |

A fifth surface, `files`, covers data committed straight into the repo - received once, version-controlled (small CSVs, a hand-transcribed plate map, a delivered table of kilobytes).
There is no fetch, no cache, and no pooch hash: git *is* the integrity mechanism, so do not gitignore `data/` (see the scaffold `.gitignore` note).
Choose it when the dataset is small and delivered rather than queried; reach for `rest`/`duckdb`/`pooch` only once the data is too large to commit.
