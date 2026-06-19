# Getting eyes on a rendered output

The kernel hands back a text repr. For a table that is enough; for a chart it carries no visual information, so a green check is not "looked at."
Two paths get you the actual pixels: screenshot a running server, or have a serverless export write the file.

## Running server (a `marimo-pair` session): screenshot it

With a live server and a connected session, rasterize the rendered DOM via `code_mode`. One call, same for every output type - matplotlib, vega/altair, plotly, an interactive widget:

```python
import marimo._code_mode as cm
from pathlib import Path

Path("data/processed/<topic>").mkdir(parents=True, exist_ok=True)   # screenshot won't mkdir
async with cm.get_context() as ctx:
    cid = ctx.cells[-1].id   # the cell holding the chart - target by id/index
    img = await ctx.screenshot(cid, save_to="data/processed/<topic>/<name>.png")
# then Read the PNG
```

It captures whatever the browser draws, so it catches vega-embed and widgets that a text repr or `ch.save()` would miss.

Target the chart by **cell id or index**, and screenshot a cell that is actually registered in the notebook - an object you only built in a `code_mode` scratch exec has no cell to capture.
`ctx.find_cell_defining_object(obj)` is the other way in, but it is a footgun: the scratch exec's scope does not carry notebook variables (so pass `ctx.globals["chart"]`, not a bare `chart`), it returns `None` for an unregistered object, and `screenshot(None, ...)` then silently captures the last cell instead of erroring. If you use it, assert the hit: `cid = ctx.find_cell_defining_object(ctx.globals["chart"]); assert cid is not None`.

Keep the `await ctx.screenshot(...)` inside the `async with`; it needs the live session.
Setup, once per environment: `ctx.packages.add("playwright")` (do **not** `await` it - it returns `None`) then `python -m playwright install chromium`. The first screenshot raises a `ScreenshotError` naming this exact fix if you skip it.
Heads-up: `packages.add("playwright")` writes `playwright` into the notebook's PEP 723 deps on disk. It is a compose-time capture tool, not a runtime dep - delete that line before the final gate.
Pass `as_data_url=True` for a `data:image/png` string instead of writing a file.

## No running server (the `marimo export` gate): export a file

Make the notebook itself emit the pixels, then `Read` them:

- altair: `ch.save("data/processed/<topic>/<name>.png", ppi=120)` (needs `vl-convert-python`). matplotlib already rasterizes - just `fig.savefig(...)`.
- Or read the export at `notebooks/__marimo__/session/<topic>.py.json` - it holds each cell's executed output. But a `mo.ui.altair_chart` stores its data as a base64 Apache-Arrow blob inside the vega spec, not plain rows: a grep for values finds nothing even when the chart is full. Decode the blob, or just write a PNG.

The `summary.json` envelope (compose step 6) also gives you a plain-JSON copy of the numbers to check.
