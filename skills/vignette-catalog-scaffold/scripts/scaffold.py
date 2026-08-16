#!/usr/bin/env python3
"""Copy the minimal vignette-catalog assets into a new or existing directory."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def rendered(source: Path, name: str, surface: str) -> str:
    data_ignore = "" if surface == "files" else "data/\n"
    return (
        source.read_text()
        .replace("<CATALOG_NAME>", name)
        .replace("<DATA_SURFACE>", surface)
        .replace("<DATA_IGNORE>", data_ignore)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--surface", required=True, choices=("rest", "duckdb", "pooch", "files")
    )
    parser.add_argument("--adopt", action="store_true")
    args = parser.parse_args()

    target = args.target.expanduser().resolve()
    if target.exists() and any(target.iterdir()) and not args.adopt:
        parser.error(
            f"{target} is non-empty; use --adopt to preserve an existing repository"
        )
    target.mkdir(parents=True, exist_ok=True)

    assets = Path(__file__).resolve().parent.parent / "assets" / "catalog"
    created: list[Path] = []
    skipped: list[Path] = []
    for source in sorted(assets.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(assets)
        if relative.name.endswith(".template"):
            relative = relative.with_name(relative.name.removesuffix(".template"))
        destination = target / relative
        if destination.exists():
            skipped.append(relative)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered(source, args.name, args.surface))
        created.append(relative)

    if not (target / ".git").exists():
        subprocess.run(["git", "init", str(target)], check=True, capture_output=True)

    print(f"catalog={target}")
    for path in created:
        print(f"created={path}")
    for path in skipped:
        print(f"preserved={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
