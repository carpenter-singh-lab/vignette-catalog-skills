#!/usr/bin/env python3
"""Fail when a marimo session snapshot contains a cell error."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check-session.py SNAPSHOT.json", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"missing session snapshot: {path}", file=sys.stderr)
        return 1

    document = json.loads(path.read_text())
    failures: list[str] = []
    for cell in document.get("cells", []):
        for output in cell.get("outputs", []):
            if output.get("type") == "error":
                failures.append(
                    f"cell {cell.get('id', '?')}: "
                    f"{output.get('evalue') or output.get('ename') or 'unknown error'}"
                )

    if failures:
        print(f"cold execution failed: {path}", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"session has no cell errors: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
