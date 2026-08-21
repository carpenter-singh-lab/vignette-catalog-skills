#!/usr/bin/env -S uv run --quiet --no-project --with websockets==15.0.1 --python 3.11 python3
"""Start, reuse, inspect, run, and stop headless marimo sessions for a catalog.

Commands:
  open [notebook]   reuse a healthy session for that exact notebook or start one,
                    ensure cells ran, and print url/session/cell state (fast path)
  start [notebook]  always start a new session
  status            report every session this catalog owns, with diagnostics
  run PORT          run all cells in a recorded session and wait for idle or error
  stop PORT         stop a session this helper started

Output is stable key=value lines (or --json where offered) so agents never
reconstruct state from pgrep, ss, curl, or /api/sessions by hand.
"""

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
WILDCARD_HOSTS = {"0.0.0.0", "::", ""}
# marimo 0.23.16 cell statuses: "idle" is the only ran-and-settled state;
# "stale" covers never-run and invalidated code; disabled cells never run.
OK_STATUSES = {"idle"}
BUSY_STATUSES = {"queued", "running", "pending"}
DISABLED_STATUSES = {"disabled", "disabled-transitively"}
LOG_TAIL_LINES = 40
DIVERGED_NOTE = (
    "notebook file changed since the last recorded run; the kernel still holds "
    "the code it loaded at start - stop and reopen for a fresh kernel of the "
    "current file"
)

CELL_REPORT_CODE = """
import json as _json
import marimo._code_mode as _cm

async with _cm.get_context() as _ctx:
    _cells = []
    for _cid in list(_ctx.cells.keys()):
        _cell = _ctx.cells[_cid]
        _status = getattr(_cell.status, "value", _cell.status)
        _cells.append(
            {
                "id": str(_cid),
                "name": str(_cell.name or ""),
                "status": str(_status).lower(),
                "errors": [str(_error) for _error in (_cell.errors or [])],
            }
        )
print("VCS_CELLS" + _json.dumps({"cells": _cells}))
"""

RUN_ALL_CODE = """
import marimo._code_mode as _cm

async with _cm.get_context() as _ctx:
    for _cid in list(_ctx.cells.keys()):
        _ctx.run_cell(_cid)
print("VCS_RUN_SUBMITTED")
"""


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
        if not isinstance(first, str) or not first:
            raise SystemExit("no notebook given and no [getting_started].first_notebook found")
        path = root / "notebooks" / first
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


def probe_host(host: str) -> str:
    return "127.0.0.1" if host in WILDCARD_HOSTS else host


def checked_host(host: str | None) -> str | None:
    if host is not None and not host.strip():
        raise SystemExit("--host must not be empty")
    return host


def browser_url(host: str, url_host: str | None, port: int) -> str:
    reported = url_host or host
    if reported in WILDCARD_HOSTS:
        raise SystemExit(
            "binding a wildcard address needs --url-host to report a reachable URL"
        )
    return f"http://{reported}:{port}"


def free_port(host: str) -> int:
    with socket.socket() as sock:
        sock.bind((probe_host(host), 0))
        return int(sock.getsockname()[1])


def base_url(host: str, port: int) -> str:
    return f"http://{probe_host(host)}:{port}"


def health(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with urllib.request.urlopen(f"{base_url(host, port)}/health", timeout=1):
            return True
    except (OSError, urllib.error.URLError):
        return False


async def register(port: int, timeout: float, host: str = "127.0.0.1") -> str:
    session_id = str(uuid.uuid4())
    uri = f"ws://{probe_host(host)}:{port}/ws?session_id={session_id}"
    async with connect(uri, max_size=None) as websocket:
        while True:
            message = await asyncio.wait_for(websocket.recv(), timeout=timeout)
            try:
                if json.loads(message).get("op") == "kernel-ready":
                    return session_id
            except (AttributeError, json.JSONDecodeError):
                continue


def server_sessions(port: int, host: str) -> dict[str, dict]:
    with urllib.request.urlopen(f"{base_url(host, port)}/api/sessions", timeout=3) as r:
        document = json.loads(r.read().decode())
    return document if isinstance(document, dict) else {}


def execute_code(
    port: int, host: str, session_id: str, code: str, timeout: float
) -> tuple[bool, str, str]:
    """Run code in the session scratchpad; return (success, stdout, error)."""
    request = urllib.request.Request(
        f"{base_url(host, port)}/api/kernel/execute",
        data=json.dumps({"code": code}).encode(),
        headers={
            "Content-Type": "application/json",
            "Marimo-Session-Id": session_id,
        },
        method="POST",
    )
    stdout_parts: list[str] = []
    event = ""
    deadline = time.monotonic() + timeout
    try:
        with urllib.request.urlopen(request, timeout=max(timeout, 5)) as response:
            for raw in response:
                if time.monotonic() > deadline:
                    return False, "".join(stdout_parts), "kernel execute timed out"
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    try:
                        payload = json.loads(line.split(":", 1)[1].strip())
                    except json.JSONDecodeError:
                        continue
                    if event == "stdout":
                        stdout_parts.append(str(payload.get("data", "")))
                    elif event == "done":
                        if payload.get("success") is False:
                            message = (payload.get("error") or {}).get(
                                "msg"
                            ) or "execution failed"
                            return False, "".join(stdout_parts), str(message)
                        return True, "".join(stdout_parts), ""
    except (OSError, urllib.error.URLError) as exc:
        return False, "".join(stdout_parts), f"kernel API unreachable: {exc}"
    return False, "".join(stdout_parts), "kernel stream ended without completion"


def cell_report(port: int, host: str, session_id: str, timeout: float) -> dict | None:
    ok, stdout, _ = execute_code(port, host, session_id, CELL_REPORT_CODE, timeout)
    if not ok:
        return None
    for line in reversed(stdout.splitlines()):
        if line.startswith("VCS_CELLS"):
            try:
                document = json.loads(line[len("VCS_CELLS") :])
            except json.JSONDecodeError:
                return None
            if isinstance(document, dict) and isinstance(document.get("cells"), list):
                return document
    return None


def summarize_cells(report: dict | None) -> dict[str, object]:
    """Count cells by explicit status; anything unrecognized counts as stale.

    Readiness must never be inferred from "not busy": marimo reports "stale"
    for never-run and invalidated code, and other non-terminal states exist
    (cancelled, interrupted, marimo-error), so only "idle" counts as ok.
    """
    if report is None:
        return {
            "total": -1,
            "ok": -1,
            "busy": -1,
            "stale": -1,
            "disabled": -1,
            "errored": -1,
            "errors": [],
        }
    cells = report["cells"]
    ok = busy = stale = disabled = 0
    for cell in cells:
        status = cell.get("status")
        if status in OK_STATUSES:
            ok += 1
        elif status in BUSY_STATUSES:
            busy += 1
        elif status in DISABLED_STATUSES:
            disabled += 1
        else:
            stale += 1
    errored = [c for c in cells if c.get("errors")]
    errors = [
        f"{cell.get('name') or cell.get('id')}: {error}"
        for cell in errored
        for error in cell["errors"]
    ]
    return {
        "total": len(cells),
        "ok": ok,
        "busy": busy,
        "stale": stale,
        "disabled": disabled,
        "errored": len(errored),
        "errors": errors,
    }


def cells_line(summary: dict[str, object]) -> str:
    return (
        f"total={summary['total']} ok={summary['ok']} busy={summary['busy']} "
        f"stale={summary['stale']} disabled={summary['disabled']} "
        f"errored={summary['errored']}"
    )


def report_is_busy(report: dict | None) -> bool:
    return report is not None and any(
        cell.get("status") in BUSY_STATUSES for cell in report["cells"]
    )


def decide_run(report: dict | None) -> bool:
    """Whether cells need an explicit run to make readiness truthful.

    marimo's explicit statuses are authoritative: "stale" marks never-run and
    invalidated code, so an all-idle error-free report needs no rerun, and
    disabled cells are excluded because marimo will never run them.
    Callers gate this on the notebook file not having diverged: the kernel
    still holds the code it loaded at start, so an automatic rerun after an
    external file edit would prove the old code while looking like it proved
    the new file. Divergence is reported, never silently rerun.
    """
    if report is None:
        return True
    summary = summarize_cells(report)
    return bool(summary["errored"] or summary["stale"])


def notebook_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def catalog_id(root: Path) -> str:
    return hashlib.sha256(str(root).encode()).hexdigest()[:12]


def state_path(root: Path, port: int) -> Path:
    return (
        Path(tempfile.gettempdir())
        / f"vignette-catalog-session-{catalog_id(root)}-{port}.json"
    )


def state_ports(root: Path) -> list[int]:
    pattern = re.compile(
        rf"vignette-catalog-session-{catalog_id(root)}-(\d+)\.json\Z"
    )
    ports = []
    for path in Path(tempfile.gettempdir()).glob(
        f"vignette-catalog-session-{catalog_id(root)}-*.json"
    ):
        match = pattern.fullmatch(path.name)
        if match:
            ports.append(int(match.group(1)))
    return sorted(ports)


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


@contextlib.contextmanager
def try_session_lock(root: Path, port: int):
    """Non-blocking port lock; yields False when another operation holds it.

    status uses this so it stays responsive while a long open or run holds a
    port lock through cell execution.
    """
    with lock_path(root, port).open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def catalog_lock_path(root: Path) -> Path:
    return (
        Path(tempfile.gettempdir())
        / f"vignette-catalog-catalog-{catalog_id(root)}.lock"
    )


@contextlib.contextmanager
def catalog_lock(root: Path):
    """Serialize find-or-create decisions for one catalog.

    Two concurrent opens of the same notebook must not both conclude that no
    session exists and start duplicate kernels; the second waits here and then
    sees the first launch's state. Lock order is always catalog before port.
    """
    with catalog_lock_path(root).open("a+") as stream:
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


def update_state_locked(root: Path, port: int, **fields: object) -> None:
    """Read-modify-write one state file; the caller must hold its port lock.

    The existence re-check stops this from resurrecting a state file that a
    concurrent stop or status cleanup has just removed.
    """
    path = state_path(root, port)
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    state.update(fields)
    if path.is_file():
        write_state(path, state)


def record_run_locked(root: Path, port: int, record_sha: str | None) -> None:
    """Record run evidence while the caller holds this port's lock."""
    fields: dict[str, object] = {"last_run": time.time()}
    if record_sha:
        fields["last_run_sha"] = record_sha
    update_state_locked(root, port, **fields)


def read_state(root: Path, port: int) -> dict | None:
    path = state_path(root, port)
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return state if isinstance(state, dict) else None


def verify_process(state: dict) -> str:
    """Non-destructive process check: 'ok', 'dead', or 'mismatch'."""
    try:
        pid = int(state["pid"])
        pgid = int(state["pgid"])
        process_start = str(state["process_start"])
        process_command = str(state["process_command"])
        process_marker = str(state["process_marker"])
        notebook = str(state["notebook"])
        port = int(state["port"])
    except (KeyError, TypeError, ValueError):
        return "mismatch"
    identity = process_identity(pid)
    if identity is None:
        return "dead"
    if (
        identity[0] != process_start
        or identity[1] != process_command
        or identity[2] != pgid
        or pgid != pid
        or not process_has_marker(pid, process_marker)
        or "marimo" not in process_command
        or notebook not in process_command
        or f"--port {port}" not in process_command
    ):
        return "mismatch"
    return "ok"


def session_facts(root: Path, port: int) -> dict[str, object]:
    """Everything known about one recorded session, without side effects."""
    facts: dict[str, object] = {"port": port, "state_path": str(state_path(root, port))}
    state = read_state(root, port)
    if state is None:
        facts["state"] = "malformed"
        return facts
    facts["state"] = "ok"
    host = str(state.get("host", "127.0.0.1"))
    facts.update(
        {
            "host": host,
            "url": str(state.get("url", f"http://{host}:{port}")),
            "notebook": str(state.get("notebook", "")),
            "session": str(state.get("session", "")),
            "pid": state.get("pid"),
            "log": str(state.get("log", "")),
            "root": str(state.get("root", "")),
            "last_run": state.get("last_run"),
            "last_run_sha": state.get("last_run_sha"),
        }
    )
    try:
        recorded_port = int(state.get("port", -1))
    except (TypeError, ValueError):
        facts["state"] = "malformed"
        return facts
    if state.get("root") != str(root) or recorded_port != port:
        facts["state"] = "mismatched"
        return facts
    facts["process"] = verify_process(state)
    facts["health"] = "ok" if health(port, host) else "unreachable"
    facts["worktree"] = "ok" if Path(str(state.get("root", ""))).is_dir() else "missing"
    notebook = Path(str(state.get("notebook", "")))
    if not notebook.is_file():
        facts["notebook_file"] = "missing"
    elif state.get("last_run_sha") and state["last_run_sha"] != notebook_sha(notebook):
        facts["notebook_file"] = "changed-since-run"
    else:
        facts["notebook_file"] = "ok"
    return facts


def facts_reusable(facts: dict[str, object], notebook: Path) -> bool:
    return (
        facts.get("state") == "ok"
        and facts.get("process") == "ok"
        and facts.get("health") == "ok"
        and facts.get("worktree") == "ok"
        and facts.get("notebook_file") != "missing"
        and facts.get("notebook") == str(notebook)
    )


def find_reusable(root: Path, notebook: Path) -> dict[str, object] | None:
    for port in state_ports(root):
        facts = session_facts(root, port)
        if facts_reusable(facts, notebook):
            return facts
    return None


def resolve_session(port: int, host: str, state_session: str, notebook: Path) -> str | None:
    """Pick the live session id for a healthy server, preferring the recorded one."""
    try:
        sessions = server_sessions(port, host)
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return state_session or None
    if state_session and state_session in sessions:
        return state_session
    matches = [
        key
        for key, value in sessions.items()
        if isinstance(value, dict)
        and str(value.get("filename", "")) in (str(notebook), notebook.name)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(sessions) == 1:
        # Adopt a lone session only when it does not contradict the target
        # notebook; a mismatched filename means a replacement session.
        key, value = next(iter(sessions.items()))
        filename = str(value.get("filename", "")) if isinstance(value, dict) else ""
        if not filename:
            return key
    return None


def log_tail(log: str | Path, lines: int = LOG_TAIL_LINES) -> str:
    try:
        content = Path(log).read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])


def fail(message: str, log: str | Path | None = None) -> SystemExit:
    if log:
        tail = log_tail(log)
        if tail:
            message = f"{message}\n--- last lines of {log} ---\n{tail}"
    return SystemExit(message)


def wait_for_idle(
    port: int, host: str, session_id: str, timeout: float
) -> dict | None:
    deadline = time.monotonic() + timeout
    report = cell_report(port, host, session_id, timeout=30)
    while report_is_busy(report) and time.monotonic() < deadline:
        time.sleep(1)
        report = cell_report(port, host, session_id, timeout=30)
    return report


def run_all_cells(
    port: int, host: str, session_id: str, timeout: float
) -> dict | None:
    """Run every cell and wait for a terminal state; writes no state.

    Callers record run evidence themselves so execution and its evidence update
    happen under one port lock and can never stamp a replacement session.
    """
    ok, _, error = execute_code(port, host, session_id, RUN_ALL_CODE, timeout)
    report = wait_for_idle(port, host, session_id, timeout)
    if report is None and not ok:
        # The execute call reports failure when a triggered cell raises, so a
        # failed submission only matters when no cell state can be read either.
        raise SystemExit(f"could not run notebook cells: {error}")
    if report_is_busy(report):
        summary = summarize_cells(report)
        raise SystemExit(
            f"cells still running after {timeout:.0f}s "
            f"({summary['busy']} of {summary['total']}); "
            f"inspect with: catalog-session.py status"
        )
    return report


def emit(pairs: list[tuple[str, object]], as_json: bool) -> None:
    if as_json:
        document: dict[str, object] = {}
        for key, value in pairs:
            if key in ("cell_error", "note"):
                document.setdefault(f"{key}s", []).append(value)
            else:
                document[key] = value
        print(json.dumps(document, indent=2))
    else:
        for key, value in pairs:
            print(f"{key}={value}")


def session_result(
    facts_or_state: dict[str, object],
    reused: bool,
    ran: str,
    report: dict | None,
    notes: tuple[str, ...] = (),
) -> list[tuple[str, object]]:
    summary = summarize_cells(report)
    pairs: list[tuple[str, object]] = [
        ("url", facts_or_state["url"]),
        ("port", facts_or_state["port"]),
        ("session", facts_or_state["session"]),
        ("pid", facts_or_state["pid"]),
        ("notebook", facts_or_state["notebook"]),
        ("log", facts_or_state["log"]),
        ("reused", str(reused).lower()),
        ("ran", ran),
        ("cells", cells_line(summary)),
    ]
    for error in summary["errors"]:
        pairs.append(("cell_error", error))
    for note in notes:
        pairs.append(("note", note))
    return pairs


def launch(
    root: Path,
    notebook: Path,
    port: int,
    host: str,
    url_host: str | None,
    timeout: float,
) -> dict[str, object]:
    """Start one marimo server and register a session; caller holds the lock."""
    url = browser_url(host, url_host, port)
    if not shutil.which("uvx"):
        raise SystemExit("uvx is required; install uv as documented by this repository")
    if health(port, host):
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
        host,
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

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and process.poll() is None:
        if health(port, host):
            time.sleep(0.25)
            if process.poll() is None and health(port, host):
                break
        time.sleep(0.25)
    else:
        stop_spawned_process(process)
        raise fail("marimo did not become healthy", log)

    try:
        session_id = asyncio.run(register(port, timeout, host))
    except Exception as exc:
        stop_spawned_process(process)
        raise fail(f"could not register a marimo session: {exc}", log) from exc

    identity = process_identity(process.pid)
    if (
        identity is None
        or identity[2] != process.pid
        or not process_has_marker(process.pid, process_marker)
    ):
        stop_spawned_process(process)
        raise fail("could not verify the marimo process", log)
    process_start, process_command, _ = identity
    if (
        "marimo" not in process_command
        or str(notebook) not in process_command
        or f"--port {port}" not in process_command
    ):
        stop_spawned_process(process)
        raise fail("marimo process identity did not match", log)

    state = {
        "pid": process.pid,
        "pgid": process.pid,
        "port": port,
        "session": session_id,
        "notebook": str(notebook),
        "log": str(log),
        "root": str(root),
        "host": host,
        "url": url,
        "process_start": process_start,
        "process_command": process_command,
        "process_marker": process_marker,
        "last_run": None,
        "last_run_sha": None,
    }
    write_state(state_path(root, port), state)
    return state


def start(args: argparse.Namespace) -> int:
    root = catalog_root()
    notebook = selected_notebook(root, args.notebook)
    check_auth(root)
    checked_host(args.host)
    current_sha = notebook_sha(notebook)
    port = args.port or free_port(args.host)
    started = time.monotonic()
    with session_lock(root, port):
        recorded_group(root, port)
        state = launch(root, notebook, port, args.host, args.url_host, args.timeout)
    startup_seconds = time.monotonic() - started
    ran = "none"
    report = None
    run_seconds = 0.0
    if args.run:
        started = time.monotonic()
        report = fresh_session_run(
            root,
            port,
            args.host,
            str(state["session"]),
            notebook,
            current_sha,
            args.run_timeout,
        )
        run_seconds = time.monotonic() - started
        ran = "all"
    pairs = session_result(state, reused=False, ran=ran, report=report)
    pairs.append(("startup_seconds", f"{startup_seconds:.1f}"))
    pairs.append(("run_seconds", f"{run_seconds:.1f}"))
    emit(pairs, args.json)
    return 0


def fresh_session_run(
    root: Path,
    port: int,
    host: str,
    session_id: str,
    notebook: Path,
    record_sha: str,
    run_timeout: float,
) -> dict | None:
    """First run of a just-launched session, serialized with stop and status.

    The launch lock was released, so re-verify under the port lock that the
    recorded state still describes exactly the session we started - same
    session id and same notebook - before running and recording evidence.
    A concurrent stop plus relaunch on this port is otherwise healthy and
    verified too, and must never be run with our session id or stamped with
    our notebook's sha. record_sha is the notebook sha captured before
    launch - the code the kernel actually loaded.
    """
    with session_lock(root, port):
        facts = session_facts(root, port)
        if (
            facts.get("state") != "ok"
            or facts.get("process") != "ok"
            or facts.get("session") != session_id
            or facts.get("notebook") != str(notebook)
        ):
            raise SystemExit(
                f"session on port {port} was replaced or stopped before its "
                f"first run; rerun open or inspect with: catalog-session.py status"
            )
        report = run_all_cells(port, host, session_id, run_timeout)
        if report is not None:
            record_run_locked(root, port, record_sha)
    return report


def open_session(args: argparse.Namespace) -> int:
    root = catalog_root()
    notebook = selected_notebook(root, args.notebook)
    check_auth(root)
    args.host = checked_host(args.host)
    current_sha = notebook_sha(notebook)

    # The find-or-create decision is serialized per catalog so two concurrent
    # opens of the same notebook cannot both launch a kernel; the second one
    # waits and then reuses the first launch's recorded state.
    state = None
    startup_seconds = 0.0
    with catalog_lock(root):
        facts = find_reusable(root, notebook)
        if facts is None:
            host = args.host or "127.0.0.1"
            port = args.port or free_port(host)
            started = time.monotonic()
            with session_lock(root, port):
                recorded_group(root, port)
                state = launch(
                    root, notebook, port, host, args.url_host, args.timeout
                )
            startup_seconds = time.monotonic() - started

    if facts is not None:
        port = int(facts["port"])
        if args.host is not None and args.host != str(facts["host"]):
            print(
                f"note: reusing the existing session bound to {facts['host']}; "
                f"stop port {port} first to rebind to {args.host}",
                file=sys.stderr,
            )
        # Hold the port lock through session resolution, execution, and the
        # evidence update so a concurrent stop-and-relaunch can neither be
        # stamped with this notebook's run evidence nor be misreported.
        with session_lock(root, port):
            facts = session_facts(root, port)
            if not facts_reusable(facts, notebook):
                raise SystemExit(
                    f"session on port {port} changed while opening; rerun open "
                    f"or inspect with: catalog-session.py status"
                )
            host = str(facts["host"])
            session_id = resolve_session(port, host, str(facts["session"]), notebook)
            if session_id is None:
                session_id = asyncio.run(register(port, args.timeout, host))
            if session_id != facts["session"]:
                update_state_locked(root, port, session=session_id)
                facts["session"] = session_id
            report = wait_for_idle(port, host, session_id, args.run_timeout)
            ran = "skipped"
            diverged = facts.get("notebook_file") == "changed-since-run"
            if args.run == "always" or (
                args.run == "auto" and not diverged and decide_run(report)
            ):
                report = run_all_cells(port, host, session_id, args.run_timeout)
                if report is not None:
                    record_run_locked(root, port, None if diverged else current_sha)
                ran = "all"
        notes = (DIVERGED_NOTE,) if diverged else ()
        emit(
            session_result(facts, reused=True, ran=ran, report=report, notes=notes),
            args.json,
        )
        return 0

    ran = "none"
    report = None
    run_seconds = 0.0
    if args.run != "never":
        started = time.monotonic()
        report = fresh_session_run(
            root,
            int(state["port"]),
            str(state["host"]),
            str(state["session"]),
            notebook,
            current_sha,
            args.run_timeout,
        )
        run_seconds = time.monotonic() - started
        ran = "all"
    pairs = session_result(state, reused=False, ran=ran, report=report)
    pairs.append(("startup_seconds", f"{startup_seconds:.1f}"))
    pairs.append(("run_seconds", f"{run_seconds:.1f}"))
    emit(pairs, args.json)
    return 0


def foreign_sessions(root: Path) -> list[dict[str, object]]:
    """State files recorded by other catalog roots (moved or trashed worktrees)."""
    marker = f"vignette-catalog-session-{catalog_id(root)}-"
    entries: list[dict[str, object]] = []
    for path in Path(tempfile.gettempdir()).glob("vignette-catalog-session-*.json"):
        if path.name.startswith(marker):
            continue
        try:
            state = json.loads(path.read_text())
            other_root = str(state["root"])
            other_port = int(state["port"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        entries.append(
            {
                "root": other_root,
                "port": other_port,
                "worktree": "ok" if Path(other_root).is_dir() else "missing",
            }
        )
    return entries


def requested_root(args: argparse.Namespace) -> Path:
    return Path(args.root) if getattr(args, "root", None) else catalog_root()


def status(args: argparse.Namespace) -> int:
    root = requested_root(args)
    ports = [args.port] if args.port else state_ports(root)
    blocks: list[dict[str, object]] = []
    for port in ports:
        # Re-verify and clean under the port lock so a session that start or
        # stop is concurrently touching is not misjudged or unlinked from
        # under them; never block on a lock a long-running open or run holds.
        with try_session_lock(root, port) as acquired:
            if not acquired:
                blocks.append(
                    {
                        "port": port,
                        "state": "busy",
                        "note": (
                            "another helper operation holds this session's "
                            "lock; retry shortly"
                        ),
                    }
                )
                continue
            facts = session_facts(root, port)
            if facts.get("state") == "malformed" or facts.get("process") in (
                "dead",
                "mismatch",
            ):
                Path(str(facts["state_path"])).unlink(missing_ok=True)
                facts["removed_stale_state"] = True
                blocks.append(facts)
                continue
        if facts.get("health") == "ok" and args.cells:
            session_id = resolve_session(
                port,
                str(facts["host"]),
                str(facts["session"]),
                Path(str(facts["notebook"])),
            )
            if session_id:
                summary = summarize_cells(
                    cell_report(port, str(facts["host"]), session_id, timeout=30)
                )
                facts["cells"] = cells_line(summary)
                facts["cell_errors"] = summary["errors"]
        blocks.append(facts)
    others = foreign_sessions(root)
    if args.json:
        print(json.dumps({"sessions": blocks, "other_catalogs": others}, indent=2))
    else:
        if not blocks:
            print("no sessions recorded by this catalog")
        for index, facts in enumerate(blocks):
            if index:
                print()
            for key, value in facts.items():
                if key in ("state_path", "root", "last_run_sha", "cell_errors"):
                    continue
                print(f"{key}={value}")
            for error in facts.get("cell_errors", []):
                print(f"cell_error={error}")
        for other in others:
            print(
                f"other_catalog root={other['root']} port={other['port']} "
                f"worktree={other['worktree']}"
            )
        if any(other["worktree"] == "missing" for other in others):
            print(
                "hint: recover an orphaned session with "
                "status/stop --root <recorded root>"
            )
    return 0


def run(args: argparse.Namespace) -> int:
    root = catalog_root()
    # Everything from verification through the evidence update happens under
    # the port lock, so a concurrent stop-and-relaunch on this port can never
    # receive run evidence from the session this command verified.
    with session_lock(root, args.port):
        facts = session_facts(root, args.port)
        if facts.get("state") != "ok" or facts.get("process") != "ok":
            raise SystemExit(
                f"no verified session on port {args.port}; "
                f"run: catalog-session.py status"
            )
        if facts.get("health") != "ok":
            raise fail(
                f"session on port {args.port} is not answering its health endpoint",
                str(facts.get("log") or ""),
            )
        notebook = Path(str(facts["notebook"]))
        if not notebook.is_file():
            raise SystemExit(
                f"notebook no longer exists: {notebook} (worktree moved or "
                f"trashed?); stop the session with: catalog-session.py stop "
                f"{args.port}"
            )
        host = str(facts["host"])
        session_id = resolve_session(args.port, host, str(facts["session"]), notebook)
        if session_id is None:
            session_id = asyncio.run(register(args.port, 30, host))
            update_state_locked(root, args.port, session=session_id)
        diverged = facts.get("notebook_file") == "changed-since-run"
        report = run_all_cells(args.port, host, session_id, args.run_timeout)
        if report is not None:
            record_run_locked(
                root, args.port, None if diverged else notebook_sha(notebook)
            )
    summary = summarize_cells(report)
    notes = (DIVERGED_NOTE,) if diverged else ()
    emit(
        session_result(facts, reused=True, ran="all", report=report, notes=notes),
        args.json,
    )
    return 1 if summary["errored"] else 0


def recorded_group(root: Path, port: int) -> tuple[int, int, str, str, Path] | None:
    path = state_path(root, port)
    state = read_state(root, port)
    try:
        if state is None:
            raise ValueError
        pid = int(state["pid"])
        pgid = int(state["pgid"])
        recorded_port = int(state["port"])
        process_start = str(state["process_start"])
        process_marker = str(state["process_marker"])
    except (KeyError, TypeError, ValueError):
        path.unlink(missing_ok=True)
        return None
    if (
        state.get("root") != str(root)
        or recorded_port != port
        or verify_process(state) != "ok"
    ):
        path.unlink(missing_ok=True)
        return None
    return pid, pgid, process_start, process_marker, path


def stop(args: argparse.Namespace) -> int:
    root = requested_root(args)
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
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser(
        "open", help="reuse an exact-notebook session or start one, and run cells"
    )
    open_parser.add_argument("notebook", nargs="?")
    open_parser.add_argument("--port", type=int)
    open_parser.add_argument(
        "--host",
        default=None,
        help="bind address for a new server (default 127.0.0.1); "
        "use a Tailscale or LAN address for direct access without a tunnel",
    )
    open_parser.add_argument(
        "--url-host", help="hostname to report in the URL when it differs from --host"
    )
    open_parser.add_argument("--timeout", type=float, default=60)
    open_parser.add_argument("--run-timeout", type=float, default=600)
    open_parser.add_argument(
        "--run",
        choices=["auto", "always", "never"],
        default="auto",
        help="run cells: auto runs only when state is stale, errored, or unproven",
    )
    open_parser.add_argument("--json", action="store_true")
    open_parser.set_defaults(function=open_session)

    start_parser = subparsers.add_parser("start", help="always start a new session")
    start_parser.add_argument("notebook", nargs="?")
    start_parser.add_argument("--port", type=int)
    start_parser.add_argument("--host", default="127.0.0.1")
    start_parser.add_argument("--url-host")
    start_parser.add_argument("--timeout", type=float, default=60)
    start_parser.add_argument("--run", action="store_true")
    start_parser.add_argument("--run-timeout", type=float, default=600)
    start_parser.add_argument("--json", action="store_true")
    start_parser.set_defaults(function=start)

    status_parser = subparsers.add_parser(
        "status", aliases=["list"], help="report every session this catalog owns"
    )
    status_parser.add_argument("--port", type=int)
    status_parser.add_argument(
        "--cells", action="store_true", help="include a live cell-state summary"
    )
    status_parser.add_argument(
        "--root",
        help="inspect sessions recorded by another catalog root "
        "(for example a moved or trashed worktree)",
    )
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(function=status)

    run_parser = subparsers.add_parser(
        "run", help="run all cells and wait for idle or error"
    )
    run_parser.add_argument("port", type=int)
    run_parser.add_argument("--run-timeout", type=float, default=600)
    run_parser.add_argument("--json", action="store_true")
    run_parser.set_defaults(function=run)

    stop_parser = subparsers.add_parser(
        "stop",
        help="stop a session this helper owns "
        "(waits for any in-flight open or run on that port)",
    )
    stop_parser.add_argument("port", type=int)
    stop_parser.add_argument("--timeout", type=float, default=5)
    stop_parser.add_argument(
        "--root",
        help="stop a session recorded by another catalog root "
        "(for example a moved or trashed worktree)",
    )
    stop_parser.set_defaults(function=stop)

    args = parser.parse_args()
    return int(args.function(args))


if __name__ == "__main__":
    raise SystemExit(main())
