#!/usr/bin/env -S uv run --quiet --with websockets --python 3.11 python3
"""Register a marimo kernel session without a browser.

marimo only creates a kernel *session* when a frontend connects to its
websocket. `marimo edit --headless` comes up with no session, so the first
`marimo-pair` `execute-code.sh` call fails with:

    No active sessions on the server. Make sure a notebook is open in the browser.

This is the browser stand-in. It opens `ws://<host>:<port>/ws?session_id=<uuid>`
the way the marimo frontend does, waits for the kernel to report ready, and
prints the session id to stdout. In `marimo edit` mode the session persists
after the websocket closes, so a one-shot connect is enough - the helper exits
and `execute-code.sh` can target the session by id or by port.

Usage:
    register-session.py --port PORT [--host HOST] [--session-id ID]
                        [--token TOKEN] [--timeout SECONDS] [--hold]

    # capture the session id a single notebook server just exposed
    SID=$(register-session.py --port "$PORT")
    bash <marimo-pair>/scripts/execute-code.sh --url "http://127.0.0.1:$PORT" -c "print('ok')"

Auth: pass --token, or set MARIMO_TOKEN, for a server started with a token.
A server launched with --no-token (what `vignette-catalog-setup` does) needs neither.

--hold keeps the websocket open and blocks instead of exiting. Use it only for
servers that close the session on disconnect (RUN mode, or `--session-ttl`).
For ordinary `marimo edit` you do not need it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus


def log(msg: str) -> None:
    """Diagnostics go to stderr; stdout is reserved for the session id."""
    print(msg, file=sys.stderr, flush=True)


async def run() -> int:
    ap = argparse.ArgumentParser(description="Register a marimo kernel session headlessly.")
    ap.add_argument("--port", required=True, help="marimo server port")
    ap.add_argument("--host", default="127.0.0.1", help="marimo server host (default 127.0.0.1)")
    ap.add_argument("--session-id", default=None, help="session id to register (default: a fresh uuid4)")
    ap.add_argument("--token", default=os.environ.get("MARIMO_TOKEN"), help="auth token (default $MARIMO_TOKEN)")
    ap.add_argument("--timeout", type=float, default=30.0, help="seconds to wait for kernel-ready (default 30)")
    ap.add_argument("--hold", action="store_true", help="hold the websocket open and block (RUN mode / --session-ttl)")
    args = ap.parse_args()

    session_id = args.session_id or str(uuid.uuid4())
    uri = f"ws://{args.host}:{args.port}/ws?session_id={session_id}"
    if args.token:
        uri += f"&access_token={args.token}"

    try:
        ws = await connect(uri, max_size=None)
    except ConnectionRefusedError:
        log(f"Could not connect to ws://{args.host}:{args.port} - is the marimo server up on that port?")
        return 1
    except InvalidStatus as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (401, 403):
            log("Websocket rejected (auth). Pass --token or set MARIMO_TOKEN, "
                "or relaunch marimo with --no-token.")
        else:
            log(f"Websocket handshake failed: {e}")
        return 1

    async with ws:
        ready = False
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=args.timeout)
                try:
                    op = json.loads(msg).get("op")
                except (json.JSONDecodeError, AttributeError):
                    continue
                if op == "kernel-ready":
                    ready = True
                    break
        except asyncio.TimeoutError:
            log(f"Connected but no kernel-ready within {args.timeout}s. "
                "The session may still have registered; check /api/sessions.")

        # The session id is the one durable thing a caller needs: emit it now,
        # before any optional --hold blocks forever.
        print(session_id, flush=True)
        if ready:
            log(f"kernel-ready: session {session_id} registered on port {args.port}")

        if args.hold:
            log("Holding websocket open (--hold). Ctrl-C or kill to release the session.")
            try:
                async for _ in ws:
                    pass
            except asyncio.CancelledError:
                pass

    return 0 if ready else 2


def main() -> None:
    try:
        sys.exit(asyncio.run(run()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
