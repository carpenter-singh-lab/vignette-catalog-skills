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

**On a `rest` surface, pin the upstream *version*, not the bytes.**
A live API has no file to hash, but it still re-anchors when the upstream ships a new release - the same failure a SHA-256 exists to catch, and a hash cannot catch it because there is nothing to hash.
Name the version you queried and pin it wherever the API gives you a handle: a release string (`R14`, `24Q4`), a dated snapshot, or a concrete record id rather than a `latest` / `versions/latest` alias that silently re-resolves on every run.
Record it in `[data].version` in `catalog.toml` so a reader knows which upstream produced the numbers, and surface it in the orientation notebook.
Where the API offers no version handle at all, say so explicitly in the notebook and note that the results are not reproducible across upstream releases - that is a real property of the analysis, and it belongs in the notebook rather than in a reader's assumptions.

**Read the dataset's caveats before you compose against it.**
A hash catches the bytes changing.
It does not catch the bytes being fine and meaning something other than what you assume.
Every dataset carries knowledge its producers have and its files do not: which samples were dropped and repeated, which identifiers are misleading, which batch is unusable, which upstream release silently re-anchored the numbers.
Point `[data].caveats` in `catalog.toml` at wherever that lives - a URL or a repo-relative path - and read it before you compose.

What it typically contains, and why it is not optional:

- **Identifiers that do not mean what they look like.** A vendor's sample barcodes may map to in-house barcodes out of order, so joining on a sorted or zipped key silently swaps two samples. Every hash still passes.
- **Known artifacts.** A miscalibrated instrument, a contaminated batch, a channel that saturated. A finding that tracks an artifact is not a finding.
- **Trust bounds.** "Proceed, but image quality may limit conclusions" is a bound on the claim you are allowed to make from that data, written by someone who saw it collected.

It takes whatever form the source already uses - a notes file in the data repo, a known-bad-samples list, an upstream release-notes page, a long-running issue thread.
Do not invent a new format for a dataset that already has one; just point at it.

If a caveat contradicts what you inferred from the data, neither override it silently nor defer to it silently: state the contradiction in the notebook and raise it.
It was written by someone who was in the room and it is usually right, but a stale caveat that buries a real finding is the failure in the other direction, and only a human can tell those apart.

If `[data].caveats` is empty, say so in the notebook.
"The producers documented no caveats" and "nobody looked" are different claims, and a reader cannot distinguish them from silence.

**Cache large remote artifacts** under `~/.cache/<catalog>` with an env-var override (for example, `CATALOG_CACHE`); check the cache first, fall back to remote.
Commit small data (kilobytes); gitignore large data and the cache.
The `summary.json` index envelopes under `data/processed/` are small data of this kind: even on `rest`/`duckdb`/`pooch` surfaces where `data/` is gitignored, they stay tracked (the scaffold `.gitignore` allow-lists `data/processed/**/summary.json`) so the index notebook can discover them. A render-only notebook with no file outputs simply writes no envelope.

**Dataset-driven differences are intentional and explicit** - declare them in `catalog.toml`.
Use the `surface` field to choose the data access pattern:

| Surface | Use it for | Auth | Cache / data policy |
|---|---|---|---|
| `rest` | Live HTTP APIs via `httpx` or `requests` | Optional env var from `[auth]` | Prefer small, fresh responses; cache bulky or slow responses explicitly. Pin the upstream *version* in `[data].version` (a release string, dated snapshot, or concrete id - never a `latest` alias); if the API exposes no version handle, say so in the notebook |
| `duckdb` | Local DuckDB databases or parquet-backed tables | Usually none, unless remote fetches need credentials | Cache large artifacts under `~/.cache/<catalog>` or the manifest's cache env var. `LOAD httpfs` for remote parquet; DuckDB->polars (`.pl()`) needs `pyarrow` in the notebook deps |
| `pooch` | Published files fetched by URL | Usually none | Store raw downloads under gitignored `data/`; require SHA-256 pins |
| `files` | Small delivered data committed directly to the repo | None | Commit the files and do not ignore `data/`; git is the integrity mechanism |

The `files` surface covers data committed straight into the repo - received once, version-controlled (small CSVs, a hand-transcribed plate map, a delivered table of kilobytes).
There is no fetch, no cache, and no pooch hash: git *is* the integrity mechanism, so do not gitignore `data/` (see the scaffold `.gitignore` note).
Choose it when the dataset is small and delivered rather than queried; reach for `rest`/`duckdb`/`pooch` only once the data is too large to commit.
