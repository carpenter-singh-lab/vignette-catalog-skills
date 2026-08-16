#!/usr/bin/env -S uv run --quiet --no-project --with websockets --python 3.11 python3
"""Start or stop one headless marimo edit session for a catalog notebook."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import resource
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import tomllib
from websockets.asyncio.client import connect


def catalog_root() -> Path:
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if (candidate / "catalog.toml").is_file():
            return candidate
    raise SystemExit("catalog.toml not found in this directory or its parents")


def selected_notebook(root: Path, value: str | None) -> Path:
    if value:
        path = Path(value)
        path = path if path.is_absolute() else root / path
    else:
        manifest = tomllib.loads((root / "catalog.toml").read_text())
        first = manifest.get("getting_started", {}).get("first_notebook")
        if first:
            path = root / "notebooks" / first
        else:
            matches = sorted((root / "notebooks").glob("nb*.py"))
            if not matches:
                raise SystemExit("no notebook given and no first notebook found")
            path = matches[0]
    path = path.resolve()
    if not path.is_file():
        raise SystemExit(f"notebook not found: {path}")
    return path


def dotenv_has(root: Path, key: str) -> bool:
    path = root / ".env"
    if not path.is_file():
        return False
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key and value.strip().strip("'\""):
            return True
    return False


def check_auth(root: Path) -> None:
    manifest = tomllib.loads((root / "catalog.toml").read_text())
    name = str(manifest.get("auth", {}).get("env_var", "")).strip()
    if name and not (os.environ.get(name) or dotenv_has(root, name)):
        raise SystemExit(
            f"catalog auth is unavailable: set {name} as documented by this repository"
        )


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def health(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
            return True
    except (OSError, urllib.error.URLError):
        return False


async def register(port: int, timeout: float) -> str:
    session_id = str(uuid.uuid4())
    uri = f"ws://127.0.0.1:{port}/ws?session_id={session_id}"
    async with connect(uri, max_size=None) as websocket:
        while True:
            message = await asyncio.wait_for(websocket.recv(), timeout=timeout)
            try:
                if json.loads(message).get("op") == "kernel-ready":
                    return session_id
            except (AttributeError, json.JSONDecodeError):
                continue


def state_path(root: Path, port: int) -> Path:
    catalog_id = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    return (
        Path(tempfile.gettempdir())
        / f"vignette-catalog-session-{catalog_id}-{port}.json"
    )


def stop_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def start(args: argparse.Namespace) -> int:
    root = catalog_root()
    notebook = selected_notebook(root, args.notebook)
    check_auth(root)
    if not shutil.which("uvx"):
        raise SystemExit("uvx is required; install uv as documented by this repository")

    port = args.port or free_port()
    if health(port):
        raise SystemExit(f"port already has a marimo server: {port}")

    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if hard not in (-1, resource.RLIM_INFINITY) and soft < hard:
            resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
    except (OSError, ValueError):
        pass

    log = Path(tempfile.gettempdir()) / f"marimo-{port}.log"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    command = [
        "uvx",
        "marimo",
        "edit",
        "--sandbox",
        "--no-token",
        "--headless",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        str(notebook),
    ]
    with log.open("w") as stream:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline and process.poll() is None:
        if health(port):
            break
        time.sleep(0.5)
    else:
        stop_group(process.pid)
        raise SystemExit(f"marimo did not become healthy; inspect {log}")

    try:
        session_id = asyncio.run(register(port, args.timeout))
    except Exception as exc:
        stop_group(process.pid)
        raise SystemExit(
            f"could not register a marimo session: {exc}; inspect {log}"
        ) from exc

    state = {
        "pid": process.pid,
        "pgid": process.pid,
        "port": port,
        "session": session_id,
        "notebook": str(notebook),
        "log": str(log),
        "root": str(root),
    }
    state_path(root, port).write_text(json.dumps(state, indent=2) + "\n")
    print(f"url=http://127.0.0.1:{port}")
    print(f"port={port}")
    print(f"session={session_id}")
    print(f"pid={process.pid}")
    print(f"notebook={notebook}")
    print(f"log={log}")
    return 0


def recorded_group(root: Path, port: int) -> tuple[int, Path] | None:
    path = state_path(root, port)
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text())
        pid = int(state["pid"])
        pgid = int(state["pgid"])
        notebook = str(state["notebook"])
        if state.get("root") != str(root) or pgid != pid:
            return None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    process = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if (
        process.returncode
        or "marimo" not in process.stdout
        or notebook not in process.stdout
    ):
        return None
    return pgid, path


def stop(args: argparse.Namespace) -> int:
    root = catalog_root()
    recorded = recorded_group(root, args.port)
    if recorded is None:
        print(f"no session recorded by this catalog on port {args.port}")
        return 0
    pgid, path = recorded
    if pgid == os.getpgrp():
        raise SystemExit("refusing to stop the current process group")
    stop_group(pgid)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if not health(args.port):
            path.unlink(missing_ok=True)
            print(f"stopped marimo session on port {args.port}")
            return 0
        time.sleep(0.25)
    print(f"session on port {args.port} did not stop after SIGTERM", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("notebook", nargs="?")
    start_parser.add_argument("--port", type=int)
    start_parser.add_argument("--timeout", type=float, default=60)
    start_parser.set_defaults(function=start)
    stop_parser = subparsers.add_parser("stop")
    stop_parser.add_argument("port", type=int)
    stop_parser.add_argument("--timeout", type=float, default=5)
    stop_parser.set_defaults(function=stop)
    args = parser.parse_args()
    return int(args.function(args))


if __name__ == "__main__":
    raise SystemExit(main())
