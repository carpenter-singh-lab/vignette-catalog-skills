# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets==15.0.1"]
# ///
"""Regression tests for the catalog scripts."""

from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import tomllib

ROOT = Path(__file__).resolve().parents[1]
SESSION_SCRIPT = (
    ROOT
    / "skills"
    / "vignette-catalog-compose-notebook"
    / "scripts"
    / "catalog-session.py"
)
VALIDATOR = (
    ROOT
    / "skills"
    / "vignette-catalog-compose-notebook"
    / "scripts"
    / "validate-notebook.sh"
)
CHECK_SESSION = (
    ROOT
    / "skills"
    / "vignette-catalog-compose-notebook"
    / "scripts"
    / "check-session.py"
)
SCAFFOLD = ROOT / "skills" / "vignette-catalog-scaffold" / "scripts" / "scaffold.py"


def load_session_module():
    spec = importlib.util.spec_from_file_location("catalog_session", SESSION_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SESSION = load_session_module()


def hold_lock(root: str, port: int, delay: float, events) -> None:
    with SESSION.session_lock(Path(root), port):
        events.put(("enter", time.monotonic()))
        time.sleep(delay)
        events.put(("exit", time.monotonic()))


def hold_catalog_lock(root: str, delay: float, events) -> None:
    with SESSION.catalog_lock(Path(root)):
        events.put(("enter", time.monotonic()))
        time.sleep(delay)
        events.put(("exit", time.monotonic()))


def unlink_state_under_lock(root: str, port: int, delay: float, events) -> None:
    with SESSION.session_lock(Path(root), port):
        SESSION.state_path(Path(root), port).unlink(missing_ok=True)
        events.put(("locked", time.monotonic()))
        time.sleep(delay)
        events.put(("released", time.monotonic()))


class SessionTests(unittest.TestCase):
    def test_lock_serializes_same_catalog_and_port(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = multiprocessing.get_context("fork")
            events = context.Queue()
            first = context.Process(
                target=hold_lock, args=(directory, 45678, 0.5, events)
            )
            second = context.Process(
                target=hold_lock, args=(directory, 45678, 0.0, events)
            )
            first.start()
            first_enter = events.get(timeout=2)
            second.start()
            first_exit = events.get(timeout=2)
            second_enter = events.get(timeout=2)
            second_exit = events.get(timeout=2)
            first.join(timeout=2)
            second.join(timeout=2)
            self.assertEqual(first.exitcode, 0)
            self.assertEqual(second.exitcode, 0)
            self.assertEqual(
                [first_enter[0], first_exit[0], second_enter[0], second_exit[0]],
                ["enter", "exit", "enter", "exit"],
            )
            self.assertGreaterEqual(second_enter[1], first_exit[1])
            SESSION.lock_path(Path(directory), 45678).unlink(missing_ok=True)

    def test_stale_birth_identity_is_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notebook = root / "notebooks" / "nb01.py"
            notebook.parent.mkdir()
            notebook.write_text("pass\n")
            port = 45679
            path = SESSION.state_path(root, port)
            path.write_text(
                json.dumps(
                    {
                        "pid": 42,
                        "pgid": 42,
                        "port": port,
                        "notebook": str(notebook),
                        "root": str(root),
                        "process_start": "old birth",
                        "process_command": f"marimo edit --port {port} {notebook}",
                        "process_marker": "0" * 32,
                    }
                )
            )
            with (
                mock.patch.object(
                    SESSION,
                    "process_identity",
                    return_value=(
                        "new birth",
                        f"marimo edit --port {port} {notebook}",
                        42,
                    ),
                ),
                mock.patch.object(SESSION, "process_has_marker", return_value=True),
            ):
                self.assertIsNone(SESSION.recorded_group(root, port))
            self.assertFalse(path.exists())

    def test_wrong_port_identity_is_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notebook = root / "notebooks" / "nb01.py"
            notebook.parent.mkdir()
            notebook.write_text("pass\n")
            port = 45680
            command = f"marimo edit --port 9999 {notebook}"
            path = SESSION.state_path(root, port)
            path.write_text(
                json.dumps(
                    {
                        "pid": 42,
                        "pgid": 42,
                        "port": port,
                        "notebook": str(notebook),
                        "root": str(root),
                        "process_start": "birth",
                        "process_command": command,
                        "process_marker": "0" * 32,
                    }
                )
            )
            with (
                mock.patch.object(
                    SESSION,
                    "process_identity",
                    return_value=("birth", command, 42),
                ),
                mock.patch.object(SESSION, "process_has_marker", return_value=True),
            ):
                self.assertIsNone(SESSION.recorded_group(root, port))
            self.assertFalse(path.exists())

    def test_reused_pid_without_ownership_marker_is_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notebook = root / "notebooks" / "nb01.py"
            notebook.parent.mkdir()
            notebook.write_text("pass\n")
            port = 45681
            command = f"marimo edit --port {port} {notebook}"
            path = SESSION.state_path(root, port)
            path.write_text(
                json.dumps(
                    {
                        "pid": 42,
                        "pgid": 42,
                        "port": port,
                        "notebook": str(notebook),
                        "root": str(root),
                        "process_start": "birth",
                        "process_command": command,
                        "process_marker": "0" * 32,
                    }
                )
            )
            with (
                mock.patch.object(
                    SESSION,
                    "process_identity",
                    return_value=("birth", command, 42),
                ),
                mock.patch.object(SESSION, "process_has_marker", return_value=False),
            ):
                self.assertIsNone(SESSION.recorded_group(root, port))
            self.assertFalse(path.exists())

    def test_indirect_auth_and_blank_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "catalog.toml").write_text(
                '[auth]\nenv_var = "TOKEN"\nindirect_env_var = "TOKEN_REF"\n'
            )
            (root / ".env").write_text("TOKEN_REF= # unset\n")
            with (
                mock.patch.dict(os.environ, {}, clear=True),
                self.assertRaises(SystemExit),
            ):
                SESSION.check_auth(root)
            (root / ".env").write_text("TOKEN_REF=op://vault/item # comment\n")
            with mock.patch.dict(os.environ, {}, clear=True):
                SESSION.check_auth(root)


class HostTests(unittest.TestCase):
    def test_probe_host_maps_wildcards_to_loopback(self) -> None:
        self.assertEqual(SESSION.probe_host("0.0.0.0"), "127.0.0.1")
        self.assertEqual(SESSION.probe_host("::"), "127.0.0.1")
        self.assertEqual(SESSION.probe_host("127.0.0.1"), "127.0.0.1")
        self.assertEqual(SESSION.probe_host("100.64.1.2"), "100.64.1.2")

    def test_browser_url_separates_bind_from_report(self) -> None:
        self.assertEqual(
            SESSION.browser_url("127.0.0.1", None, 2718), "http://127.0.0.1:2718"
        )
        self.assertEqual(
            SESSION.browser_url("0.0.0.0", "spirit.example.ts.net", 2718),
            "http://spirit.example.ts.net:2718",
        )
        with self.assertRaises(SystemExit):
            SESSION.browser_url("0.0.0.0", None, 2718)


class CellStateTests(unittest.TestCase):
    def report(self, cells, defined=1, defs_total=1):
        return {"cells": cells, "defined": defined, "defs_total": defs_total}

    def test_summarize_cells_counts_and_errors(self) -> None:
        report = self.report(
            [
                {"id": "a", "name": "setup", "status": "idle", "errors": []},
                {"id": "b", "name": "", "status": "running", "errors": []},
                {"id": "c", "name": "plot", "status": "idle", "errors": ["boom"]},
                {"id": "d", "name": "", "status": "stale", "errors": []},
                {"id": "e", "name": "", "status": "cancelled", "errors": []},
                {"id": "f", "name": "", "status": "disabled", "errors": []},
            ]
        )
        summary = SESSION.summarize_cells(report)
        self.assertEqual(
            (
                summary["total"],
                summary["ok"],
                summary["busy"],
                summary["stale"],
                summary["disabled"],
                summary["errored"],
            ),
            (6, 2, 1, 2, 1, 1),
        )
        self.assertEqual(summary["errors"], ["plot: boom"])
        self.assertEqual(SESSION.summarize_cells(None)["total"], -1)

    def test_stale_cells_are_never_reported_ready(self) -> None:
        # marimo reports "stale" for never-run and invalidated code; treating
        # everything non-busy as ok would claim readiness on a dead kernel.
        stale_only = self.report(
            [
                {"id": "a", "name": "", "status": "stale", "errors": []},
                {"id": "b", "name": "", "status": "stale", "errors": []},
            ]
        )
        mixed = self.report(
            [
                {"id": "a", "name": "", "status": "idle", "errors": []},
                {"id": "b", "name": "", "status": "stale", "errors": []},
            ]
        )
        self.assertEqual(SESSION.summarize_cells(stale_only)["stale"], 2)
        self.assertTrue(SESSION.decide_run(stale_only))
        self.assertTrue(SESSION.decide_run(mixed))

    def test_decide_run(self) -> None:
        idle = self.report([{"id": "a", "name": "", "status": "idle", "errors": []}])
        errored = self.report(
            [{"id": "a", "name": "", "status": "idle", "errors": ["boom"]}]
        )
        self.assertTrue(SESSION.decide_run(None))
        self.assertTrue(SESSION.decide_run(errored))
        # marimo's explicit statuses are authoritative: an all-idle error-free
        # report means the cells ran, so no rerun is needed.
        self.assertFalse(SESSION.decide_run(idle))

    def test_disabled_cells_never_force_a_rerun(self) -> None:
        # marimo skips disabled and transitively disabled cells during runs,
        # so treating them as unproven would rerun the same work on every
        # open without ever changing the outcome.
        disabled_only = self.report(
            [{"id": "a", "name": "", "status": "disabled", "errors": []}]
        )
        mixed = self.report(
            [
                {"id": "a", "name": "", "status": "idle", "errors": []},
                {"id": "b", "name": "", "status": "disabled-transitively", "errors": []},
            ]
        )
        self.assertFalse(SESSION.decide_run(disabled_only))
        self.assertFalse(SESSION.decide_run(mixed))


class ReuseTests(unittest.TestCase):
    def make_state(self, root, port, notebook, **overrides):
        command = f"marimo edit --host 127.0.0.1 --port {port} {notebook}"
        state = {
            "pid": 4242,
            "pgid": 4242,
            "port": port,
            "session": "session-id",
            "notebook": str(notebook),
            "log": str(root / "marimo.log"),
            "root": str(root),
            "host": "127.0.0.1",
            "url": f"http://127.0.0.1:{port}",
            "process_start": "birth",
            "process_command": command,
            "process_marker": "0" * 32,
            "last_run": None,
            "last_run_sha": None,
        }
        state.update(overrides)
        path = SESSION.state_path(root, port)
        path.write_text(json.dumps(state))
        self.addCleanup(path.unlink, missing_ok=True)
        return state

    def live_process_mocks(self, state):
        return (
            mock.patch.object(
                SESSION,
                "process_identity",
                return_value=(
                    state["process_start"],
                    state["process_command"],
                    state["pgid"],
                ),
            ),
            mock.patch.object(SESSION, "process_has_marker", return_value=True),
            mock.patch.object(SESSION, "health", return_value=True),
        )

    def test_exact_notebook_reuse_and_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notebooks = root / "notebooks"
            notebooks.mkdir()
            target = notebooks / "nb05.py"
            other = notebooks / "nb01.py"
            target.write_text("pass\n")
            other.write_text("pass\n")
            state = self.make_state(root, 45690, target)
            identity, marker, healthy = self.live_process_mocks(state)
            with identity, marker, healthy:
                facts = SESSION.find_reusable(root, target)
                self.assertIsNotNone(facts)
                self.assertEqual(facts["port"], 45690)
                self.assertEqual(facts["notebook"], str(target))
                self.assertIsNone(SESSION.find_reusable(root, other))

    def test_missing_worktree_blocks_reuse(self) -> None:
        parent = tempfile.mkdtemp()
        root = Path(parent) / "gone"
        root.mkdir()
        notebook = root / "notebooks" / "nb01.py"
        notebook.parent.mkdir()
        notebook.write_text("pass\n")
        state = self.make_state(root, 45691, notebook)
        shutil.rmtree(root)
        identity, marker, healthy = self.live_process_mocks(state)
        with identity, marker, healthy:
            facts = SESSION.session_facts(root, 45691)
            self.assertEqual(facts["worktree"], "missing")
            self.assertEqual(facts["notebook_file"], "missing")
            self.assertFalse(SESSION.facts_reusable(facts, notebook))
        shutil.rmtree(parent, ignore_errors=True)

    def test_changed_notebook_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notebook = root / "notebooks" / "nb01.py"
            notebook.parent.mkdir()
            notebook.write_text("value = 1\n")
            state = self.make_state(
                root, 45692, notebook, last_run_sha="not-the-current-sha"
            )
            identity, marker, healthy = self.live_process_mocks(state)
            with identity, marker, healthy:
                facts = SESSION.session_facts(root, 45692)
                self.assertEqual(facts["notebook_file"], "changed-since-run")
                self.assertTrue(SESSION.facts_reusable(facts, notebook))

    def test_status_cleans_dead_and_malformed_state(self) -> None:
        import argparse
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notebook = root / "notebooks" / "nb01.py"
            notebook.parent.mkdir()
            notebook.write_text("pass\n")
            dead = self.make_state(root, 45693, notebook)
            malformed_path = SESSION.state_path(root, 45694)
            malformed_path.write_text("not json")
            self.addCleanup(malformed_path.unlink, missing_ok=True)
            arguments = argparse.Namespace(
                port=None, cells=False, json=True, root=str(root)
            )
            buffer = io.StringIO()
            with (
                mock.patch.object(SESSION, "process_identity", return_value=None),
                mock.patch.object(SESSION, "health", return_value=False),
                contextlib.redirect_stdout(buffer),
            ):
                SESSION.status(arguments)
            document = json.loads(buffer.getvalue())
            by_port = {entry["port"]: entry for entry in document["sessions"]}
            self.assertEqual(by_port[45693]["process"], "dead")
            self.assertTrue(by_port[45693]["removed_stale_state"])
            self.assertEqual(by_port[45694]["state"], "malformed")
            self.assertTrue(by_port[45694]["removed_stale_state"])
            self.assertFalse(SESSION.state_path(root, 45693).exists())
            self.assertFalse(malformed_path.exists())
            self.assertEqual(dead["port"], 45693)

    def test_valid_json_with_malformed_schema_is_reported_not_crashed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            port = 45700
            path = SESSION.state_path(root, port)
            path.write_text(json.dumps({"root": str(root), "port": "not-an-int"}))
            self.addCleanup(path.unlink, missing_ok=True)
            with mock.patch.object(SESSION, "health", return_value=False):
                facts = SESSION.session_facts(root, port)
            self.assertEqual(facts["state"], "malformed")

    def test_foreign_sessions_surface_orphaned_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "current"
            root.mkdir()
            orphan_root = Path(directory) / "orphan"
            orphan_root.mkdir()
            orphan_notebook = orphan_root / "notebooks" / "nb01.py"
            orphan_notebook.parent.mkdir()
            orphan_notebook.write_text("pass\n")
            self.make_state(orphan_root, 45695, orphan_notebook)
            shutil.rmtree(orphan_root)
            entries = SESSION.foreign_sessions(root)
            match = [
                entry
                for entry in entries
                if entry["root"] == str(orphan_root) and entry["port"] == 45695
            ]
            self.assertEqual(len(match), 1)
            self.assertEqual(match[0]["worktree"], "missing")


class LockingTests(unittest.TestCase):
    def test_catalog_lock_serializes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = multiprocessing.get_context("fork")
            events = context.Queue()
            first = context.Process(
                target=hold_catalog_lock, args=(directory, 0.5, events)
            )
            second = context.Process(
                target=hold_catalog_lock, args=(directory, 0.0, events)
            )
            first.start()
            events.get(timeout=2)
            second.start()
            first_exit = events.get(timeout=2)
            second_enter = events.get(timeout=2)
            events.get(timeout=2)
            first.join(timeout=2)
            second.join(timeout=2)
            self.assertEqual(first.exitcode, 0)
            self.assertEqual(second.exitcode, 0)
            self.assertGreaterEqual(second_enter[1], first_exit[1])
            SESSION.catalog_lock_path(Path(directory)).unlink(missing_ok=True)

    def test_update_state_cannot_resurrect_removed_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            port = 45697
            path = SESSION.state_path(root, port)
            path.write_text(json.dumps({"port": port, "root": str(root)}))
            context = multiprocessing.get_context("fork")
            events = context.Queue()
            remover = context.Process(
                target=unlink_state_under_lock, args=(directory, port, 0.5, events)
            )
            remover.start()
            locked = events.get(timeout=2)
            self.assertEqual(locked[0], "locked")
            # The state was unlinked under the lock; update_state must wait
            # for the lock and then decline to recreate the file.
            SESSION.update_state(root, port, last_run=1.0)
            released = events.get(timeout=2)
            self.assertEqual(released[0], "released")
            remover.join(timeout=2)
            self.assertFalse(path.exists())
            SESSION.lock_path(root, port).unlink(missing_ok=True)

    def test_update_state_on_missing_state_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            SESSION.update_state(root, 45698, last_run=1.0)
            self.assertFalse(SESSION.state_path(root, 45698).exists())
            SESSION.lock_path(root, 45698).unlink(missing_ok=True)


class ReusePathOpenTests(unittest.TestCase):
    def open_arguments(self, notebook: Path, run: str):
        import argparse

        return argparse.Namespace(
            notebook=str(notebook),
            host=None,
            url_host=None,
            port=None,
            timeout=60,
            run_timeout=600,
            run=run,
            json=False,
        )

    def run_open(
        self,
        run: str,
        notebook_file: str = "changed-since-run",
        report: dict | None = None,
    ) -> tuple[mock.Mock, mock.Mock, str]:
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "catalog.toml").write_text("")
            notebook = root / "notebooks" / "nb01.py"
            notebook.parent.mkdir()
            notebook.write_text("value = 1\n")
            facts = {
                "state": "ok",
                "process": "ok",
                "health": "ok",
                "worktree": "ok",
                "port": 45699,
                "host": "127.0.0.1",
                "url": "http://127.0.0.1:45699",
                "notebook": str(notebook),
                "session": "sid",
                "pid": 4242,
                "log": str(root / "marimo.log"),
                "notebook_file": notebook_file,
                "last_run_sha": "old-sha",
            }
            if report is None:
                report = {
                    "cells": [
                        {"id": "a", "name": "", "status": "idle", "errors": ["boom"]}
                    ]
                }
            run_mock = mock.Mock(return_value=report)
            record_mock = mock.Mock()
            buffer = io.StringIO()
            with (
                mock.patch.object(SESSION, "catalog_root", return_value=root),
                mock.patch.object(SESSION, "find_reusable", return_value=facts),
                mock.patch.object(SESSION, "session_facts", return_value=facts),
                mock.patch.object(SESSION, "resolve_session", return_value="sid"),
                mock.patch.object(SESSION, "wait_for_idle", return_value=report),
                mock.patch.object(SESSION, "run_all_cells", run_mock),
                mock.patch.object(SESSION, "record_run", record_mock),
                contextlib.redirect_stdout(buffer),
            ):
                SESSION.open_session(self.open_arguments(notebook, run))
            return run_mock, record_mock, buffer.getvalue()

    def test_auto_open_never_reruns_a_diverged_kernel(self) -> None:
        # An errored report would normally trigger a rerun, but after an
        # external file edit that would execute the old kernel code while
        # appearing to prove the new file.
        run_mock, record_mock, output = self.run_open("auto")
        run_mock.assert_not_called()
        record_mock.assert_not_called()
        self.assertIn("ran=skipped", output)
        self.assertIn("note=", output)

    def test_always_reruns_but_never_records_the_new_sha(self) -> None:
        run_mock, record_mock, output = self.run_open("always")
        run_mock.assert_called_once()
        record_mock.assert_called_once()
        self.assertIsNone(record_mock.call_args.args[2])
        self.assertIn("ran=all", output)

    def test_disabled_cells_do_not_rerun_a_proven_session(self) -> None:
        disabled_report = {
            "cells": [
                {"id": "a", "name": "", "status": "idle", "errors": []},
                {"id": "b", "name": "", "status": "disabled", "errors": []},
            ]
        }
        run_mock, _, output = self.run_open(
            "auto", notebook_file="ok", report=disabled_report
        )
        run_mock.assert_not_called()
        self.assertIn("ran=skipped", output)
        self.assertIn("disabled=1", output)


class ResolveSessionTests(unittest.TestCase):
    def test_lone_session_with_mismatched_filename_is_rejected(self) -> None:
        # A lone session whose filename contradicts the target notebook is a
        # replacement session; adopting it would attach run evidence to the
        # wrong kernel.
        with mock.patch.object(
            SESSION,
            "server_sessions",
            return_value={"s1": {"filename": "/x/other.py"}},
        ):
            self.assertIsNone(
                SESSION.resolve_session(1, "127.0.0.1", "gone", Path("/x/nb.py"))
            )

    def test_lone_matching_or_unnamed_session_is_adopted(self) -> None:
        with mock.patch.object(
            SESSION,
            "server_sessions",
            return_value={"s1": {"filename": "/x/nb.py"}},
        ):
            self.assertEqual(
                SESSION.resolve_session(1, "127.0.0.1", "gone", Path("/x/nb.py")),
                "s1",
            )
        with mock.patch.object(
            SESSION, "server_sessions", return_value={"s1": {}}
        ):
            self.assertEqual(
                SESSION.resolve_session(1, "127.0.0.1", "gone", Path("/x/nb.py")),
                "s1",
            )

    def test_recorded_session_wins_when_still_present(self) -> None:
        with mock.patch.object(
            SESSION,
            "server_sessions",
            return_value={"a": {"filename": "/x/nb.py"}, "b": {"filename": ""}},
        ):
            self.assertEqual(
                SESSION.resolve_session(1, "127.0.0.1", "a", Path("/x/nb.py")), "a"
            )


class RunLockTests(unittest.TestCase):
    def test_run_holds_the_port_lock_through_execution(self) -> None:
        import argparse
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notebook = root / "notebooks" / "nb01.py"
            notebook.parent.mkdir()
            notebook.write_text("value = 1\n")
            port = 45701
            facts = {
                "state": "ok",
                "process": "ok",
                "health": "ok",
                "worktree": "ok",
                "port": port,
                "host": "127.0.0.1",
                "url": f"http://127.0.0.1:{port}",
                "notebook": str(notebook),
                "session": "sid",
                "pid": 4242,
                "log": str(root / "marimo.log"),
                "notebook_file": "ok",
            }
            observed = {}

            def probe_lock(*arguments, **keywords):
                # Runs where run() resolves the session: a second process must
                # find the port lock already held, proving stop cannot
                # interleave between verification and the evidence update.
                probe_code = (
                    "import fcntl, sys\n"
                    f"stream = open({str(SESSION.lock_path(root, port))!r}, 'a+')\n"
                    "try:\n"
                    "    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
                    "    print('free')\n"
                    "except OSError:\n"
                    "    print('held')\n"
                )
                child = subprocess.run(
                    [sys.executable, "-c", probe_code],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                observed["lock"] = child.stdout.strip()
                return "sid"

            report = {"cells": [{"id": "a", "name": "", "status": "idle", "errors": []}]}
            record_mock = mock.Mock()
            arguments = argparse.Namespace(port=port, run_timeout=600, json=False)
            with (
                mock.patch.object(SESSION, "catalog_root", return_value=root),
                mock.patch.object(SESSION, "session_facts", return_value=facts),
                mock.patch.object(SESSION, "resolve_session", side_effect=probe_lock),
                mock.patch.object(SESSION, "run_all_cells", return_value=report),
                mock.patch.object(SESSION, "record_run", record_mock),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                SESSION.run(arguments)
            self.assertEqual(observed["lock"], "held")
            record_mock.assert_called_once()
            SESSION.lock_path(root, port).unlink(missing_ok=True)


class EmitTests(unittest.TestCase):
    def test_json_output_keeps_every_error_and_note(self) -> None:
        import contextlib
        import io

        pairs = [
            ("url", "http://127.0.0.1:1"),
            ("cell_error", "a: boom"),
            ("cell_error", "b: crash"),
            ("note", "n1"),
        ]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            SESSION.emit(pairs, as_json=True)
        document = json.loads(buffer.getvalue())
        self.assertEqual(document["cell_errors"], ["a: boom", "b: crash"])
        self.assertEqual(document["notes"], ["n1"])
        self.assertEqual(document["url"], "http://127.0.0.1:1")


class ScaffoldTests(unittest.TestCase):
    def run_scaffold(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCAFFOLD), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_invalid_name_has_no_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "catalog"
            result = self.run_scaffold(
                str(target), "--name", 'demo"name', "--surface", "rest"
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(target.exists())

    def test_new_scaffold_inside_repo_does_not_nest_git(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "parent"
            parent.mkdir()
            subprocess.run(
                ["git", "init", str(parent)], capture_output=True, check=True
            )
            target = parent / "catalog"
            result = self.run_scaffold(
                str(target), "--name", "demo-catalog", "--surface", "rest"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((target / ".git").exists())
            tomllib.loads((target / "catalog.toml").read_text())

    def test_adopt_preserves_files_and_does_not_initialize_git(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "catalog"
            target.mkdir()
            existing = target / "README.md"
            existing.write_text("keep me\n")
            result = self.run_scaffold(
                str(target),
                "--name",
                "demo-catalog",
                "--surface",
                "files",
                "--adopt",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(existing.read_text(), "keep me\n")
            self.assertFalse((target / ".git").exists())

    def test_new_standalone_scaffold_initializes_git(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "catalog"
            result = self.run_scaffold(
                str(target), "--name", "demo-catalog", "--surface", "pooch"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / ".git").exists())
            self.assertIn("data/\n", (target / ".gitignore").read_text())


class ValidatorTests(unittest.TestCase):
    def make_fake_uvx(self, directory: Path) -> tuple[Path, Path]:
        binary = directory / "bin"
        binary.mkdir()
        log = directory / "uvx.log"
        uvx = binary / "uvx"
        uvx.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
with Path(os.environ["FAKE_UVX_LOG"]).open("a") as stream:
    stream.write(json.dumps(args) + "\\n")
notebook = Path(args[-1])
if "check" in args and "--fix" in args:
    notebook.write_text(notebook.read_text() + "# marimo-fixed\\n")
if "format" in args and "--check" not in args:
    notebook.write_text(notebook.read_text() + "# ruff-formatted\\n")
if "export" in args and "session" in args:
    session = notebook.parent / "__marimo__" / "session" / (notebook.name + ".json")
    session.parent.mkdir(parents=True, exist_ok=True)
    outputs = []
    if (
        os.environ.get("FAKE_SESSION_ERROR") == "1"
        or os.environ.get("FAKE_FAIL_NOTEBOOK") == notebook.name
    ):
        outputs = [{"type": "error", "evalue": "boom"}]
    session.write_text(json.dumps({"cells": [{"id": "cell", "outputs": outputs}]}) + "\\n")
"""
        )
        uvx.chmod(0o755)
        return binary, log

    def run_validator(
        self, directory: Path, write: bool, fail: bool
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
        notebook = directory / "notebooks" / "nb01.py"
        session = notebook.parent / "__marimo__" / "session" / (notebook.name + ".json")
        notebook.parent.mkdir()
        session.parent.mkdir(parents=True)
        notebook.write_text("value = 1\n")
        session.write_text('{"cells": [{"id": "old", "outputs": []}]}\n')
        binary, log = self.make_fake_uvx(directory)
        environment = os.environ.copy()
        environment["PATH"] = f"{binary}{os.pathsep}{environment['PATH']}"
        environment["FAKE_UVX_LOG"] = str(log)
        environment["FAKE_SESSION_ERROR"] = "1" if fail else "0"
        command = ["bash", str(VALIDATOR)]
        if write:
            command.append("--write")
        command.append(str(notebook))
        result = subprocess.run(
            command, capture_output=True, text=True, env=environment, check=False
        )
        return result, notebook, session, log

    def test_default_success_is_non_mutating_and_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            result, notebook, session, log = self.run_validator(
                directory, write=False, fail=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(notebook.read_text(), "value = 1\n")
            self.assertEqual(
                session.read_text(), '{"cells": [{"id": "old", "outputs": []}]}\n'
            )
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertTrue(
                all(call[0] in {"marimo==0.23.16", "ruff@0.16.2"} for call in calls)
            )

    def test_default_failure_restores_source_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            result, notebook, session, _ = self.run_validator(
                Path(directory_name), write=False, fail=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(notebook.read_text(), "value = 1\n")
            self.assertEqual(
                session.read_text(), '{"cells": [{"id": "old", "outputs": []}]}\n'
            )

    def test_write_success_keeps_source_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            result, notebook, session, _ = self.run_validator(
                Path(directory_name), write=True, fail=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("# marimo-fixed", notebook.read_text())
            self.assertIn("# ruff-formatted", notebook.read_text())
            self.assertIn('"id": "cell"', session.read_text())

    def test_write_failure_is_transactional(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            result, notebook, session, _ = self.run_validator(
                Path(directory_name), write=True, fail=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(notebook.read_text(), "value = 1\n")
            self.assertEqual(
                session.read_text(), '{"cells": [{"id": "old", "outputs": []}]}\n'
            )

    def test_write_batch_failure_restores_every_notebook(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            notebooks = directory / "notebooks"
            notebooks.mkdir()
            session_directory = notebooks / "__marimo__" / "session"
            session_directory.mkdir(parents=True)
            notebook_paths = [notebooks / "nb01.py", notebooks / "nb02.py"]
            session_paths = [
                session_directory / "nb01.py.json",
                session_directory / "nb02.py.json",
            ]
            for index, notebook in enumerate(notebook_paths, start=1):
                notebook.write_text(f"value = {index}\n")
            for index, session in enumerate(session_paths, start=1):
                session.write_text(
                    json.dumps({"cells": [{"id": f"old-{index}", "outputs": []}]})
                    + "\n"
                )
            original_notebooks = [path.read_bytes() for path in notebook_paths]
            original_sessions = [path.read_bytes() for path in session_paths]
            binary, log = self.make_fake_uvx(directory)
            environment = os.environ.copy()
            environment["PATH"] = f"{binary}{os.pathsep}{environment['PATH']}"
            environment["FAKE_UVX_LOG"] = str(log)
            environment["FAKE_SESSION_ERROR"] = "0"
            environment["FAKE_FAIL_NOTEBOOK"] = "nb02.py"
            result = subprocess.run(
                [
                    "bash",
                    str(VALIDATOR),
                    "--write",
                    *(str(path) for path in notebook_paths),
                ],
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(
                [path.read_bytes() for path in notebook_paths], original_notebooks
            )
            self.assertEqual(
                [path.read_bytes() for path in session_paths], original_sessions
            )


class SessionSnapshotTests(unittest.TestCase):
    def run_check(self, content: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text(content)
            return subprocess.run(
                [sys.executable, str(CHECK_SESSION), str(path)],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_rejects_malformed_and_empty_snapshots(self) -> None:
        self.assertNotEqual(self.run_check("not json\n").returncode, 0)
        self.assertNotEqual(self.run_check('{"cells": []}\n').returncode, 0)

    def test_accepts_nonempty_snapshot_without_errors(self) -> None:
        result = self.run_check('{"cells": [{"id": "cell", "outputs": []}]}\n')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
