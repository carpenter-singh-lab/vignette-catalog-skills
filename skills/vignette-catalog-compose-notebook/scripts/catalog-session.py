#!/usr/bin/env -S uv run --quiet --no-project --with websockets==15.0.1 --python 3.11 python3
"""Start or stop one headless marimo edit session for a catalog notebook."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import fcntl
import hashlib
import json
import os
import re
import resource
import shlex
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

MARIMO_PACKAGE = "marimo==0.23.16"
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
SESSION_MARKER_ENV = "VIGNETTE_CATALOG_SESSION_MARKER"
SESSION_MARKER = re.compile(r"[0-9a-f]{32}\Z")


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
        if name.strip() != key:
            continue
        try:
            values = shlex.split(value, comments=True, posix=True)
        except ValueError:
            return False
        return bool(values and values[0].strip())
    return False


def check_auth(root: Path) -> None:
    manifest = tomllib.loads((root / "catalog.toml").read_text())
    auth = manifest.get("auth", {})
    if not isinstance(auth, dict):
        raise SystemExit("catalog auth must be a TOML table")
    names: list[str] = []
    for field in ("env_var", "indirect_env_var"):
        value = auth.get(field, "")
        if not isinstance(value, str):
            raise SystemExit(f"catalog auth.{field} must be a string")
        name = value.strip()
        if name and not ENV_NAME.fullmatch(name):
            raise SystemExit(f"catalog auth.{field} is not a valid environment name")
        if name:
            names.append(name)
    if names and not any(
        os.environ.get(name, "").strip() or dotenv_has(root, name) for name in names
    ):
        choices = " or ".join(names)
        raise SystemExit(
            f"catalog auth is unavailable: set {choices} as documented by this repository"
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


def catalog_id(root: Path) -> str:
    return hashlib.sha256(str(root).encode()).hexdigest()[:12]


def state_path(root: Path, port: int) -> Path:
    return (
        Path(tempfile.gettempdir())
        / f"vignette-catalog-session-{catalog_id(root)}-{port}.json"
    )


def lock_path(root: Path, port: int) -> Path:
    return (
        Path(tempfile.gettempdir())
        / f"vignette-catalog-session-{catalog_id(root)}-{port}.lock"
    )


@contextlib.contextmanager
def session_lock(root: Path, port: int):
    with lock_path(root, port).open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def stop_group(pgid: int, sig: signal.Signals = signal.SIGTERM) -> None:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def stop_spawned_process(process: subprocess.Popen, timeout: float = 5) -> None:
    stop_group(process.pid)
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop_group(process.pid, signal.SIGKILL)
        process.wait(timeout=timeout)


def process_identity(pid: int) -> tuple[str, str, int] | None:
    fields: list[str] = []
    for field in ("lstart", "command"):
        result = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", f"{field}="],
            capture_output=True,
            text=True,
            check=False,
        )
        value = result.stdout.strip()
        if result.returncode or not value:
            return None
        fields.append(value)
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return None
    return fields[0], fields[1], pgid


def process_has_marker(pid: int, marker: str) -> bool:
    if not SESSION_MARKER.fullmatch(marker):
        return False
    expected = f"{SESSION_MARKER_ENV}={marker}".encode()
    try:
        environment = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except OSError:
        result = subprocess.run(
            ["ps", "eww", "-p", str(pid), "-o", "command="],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0 and expected in result.stdout.split()
    return expected in environment


def write_state(path: Path, state: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def start(args: argparse.Namespace) -> int:
    root = catalog_root()
    notebook = selected_notebook(root, args.notebook)
    check_auth(root)
    if not shutil.which("uvx"):
        raise SystemExit("uvx is required; install uv as documented by this repository")

    port = args.port or free_port()
    with session_lock(root, port):
        recorded_group(root, port)
        if health(port):
            raise SystemExit(f"port already has a marimo server: {port}")

        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            if hard not in (-1, resource.RLIM_INFINITY) and soft < hard:
                resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
        except (OSError, ValueError):
            pass

        log = (
            Path(tempfile.gettempdir())
            / f"marimo-{catalog_id(root)}-{port}-{uuid.uuid4().hex[:8]}.log"
        )
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        process_marker = uuid.uuid4().hex
        environment[SESSION_MARKER_ENV] = process_marker
        command = [
            "uvx",
            MARIMO_PACKAGE,
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
                time.sleep(0.25)
                if process.poll() is None and health(port):
                    break
            time.sleep(0.25)
        else:
            stop_spawned_process(process)
            raise SystemExit(f"marimo did not become healthy; inspect {log}")

        try:
            session_id = asyncio.run(register(port, args.timeout))
        except Exception as exc:
            stop_spawned_process(process)
            raise SystemExit(
                f"could not register a marimo session: {exc}; inspect {log}"
            ) from exc

        identity = process_identity(process.pid)
        if (
            identity is None
            or identity[2] != process.pid
            or not process_has_marker(process.pid, process_marker)
        ):
            stop_spawned_process(process)
            raise SystemExit(f"could not verify the marimo process; inspect {log}")
        process_start, process_command, _ = identity
        if (
            "marimo" not in process_command
            or str(notebook) not in process_command
            or f"--port {port}" not in process_command
        ):
            stop_spawned_process(process)
            raise SystemExit(f"marimo process identity did not match; inspect {log}")

        state = {
            "pid": process.pid,
            "pgid": process.pid,
            "port": port,
            "session": session_id,
            "notebook": str(notebook),
            "log": str(log),
            "root": str(root),
            "process_start": process_start,
            "process_command": process_command,
            "process_marker": process_marker,
        }
        write_state(state_path(root, port), state)
    print(f"url=http://127.0.0.1:{port}")
    print(f"port={port}")
    print(f"session={session_id}")
    print(f"pid={process.pid}")
    print(f"notebook={notebook}")
    print(f"log={log}")
    return 0


def recorded_group(root: Path, port: int) -> tuple[int, int, str, str, Path] | None:
    path = state_path(root, port)
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text())
        pid = int(state["pid"])
        pgid = int(state["pgid"])
        recorded_port = int(state["port"])
        notebook = str(state["notebook"])
        process_start = str(state["process_start"])
        process_command = str(state["process_command"])
        process_marker = str(state["process_marker"])
        if state.get("root") != str(root) or pgid != pid or recorded_port != port:
            path.unlink(missing_ok=True)
            return None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return None

    identity = process_identity(pid)
    if (
        identity is None
        or identity[0] != process_start
        or identity[1] != process_command
        or identity[2] != pgid
        or not process_has_marker(pid, process_marker)
        or "marimo" not in process_command
        or notebook not in process_command
        or f"--port {port}" not in process_command
    ):
        path.unlink(missing_ok=True)
        return None
    return pid, pgid, process_start, process_marker, path


def stop(args: argparse.Namespace) -> int:
    root = catalog_root()
    with session_lock(root, args.port):
        recorded = recorded_group(root, args.port)
        if recorded is None:
            print(f"no session recorded by this catalog on port {args.port}")
            return 0
        pid, pgid, process_start, process_marker, path = recorded
        if pgid == os.getpgrp():
            raise SystemExit("refusing to stop the current process group")
        stop_group(pgid)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            identity = process_identity(pid)
            if (
                identity is None
                or identity[0] != process_start
                or not process_has_marker(pid, process_marker)
            ):
                path.unlink(missing_ok=True)
                print(f"stopped marimo session on port {args.port}")
                return 0
            time.sleep(0.25)
        identity = process_identity(pid)
        if (
            identity is not None
            and identity[0] == process_start
            and process_has_marker(pid, process_marker)
        ):
            stop_group(pgid, signal.SIGKILL)
            time.sleep(0.25)
        identity = process_identity(pid)
        if (
            identity is None
            or identity[0] != process_start
            or not process_has_marker(pid, process_marker)
        ):
            path.unlink(missing_ok=True)
            print(f"stopped marimo session on port {args.port}")
            return 0
        print(f"session on port {args.port} did not stop", file=sys.stderr)
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
