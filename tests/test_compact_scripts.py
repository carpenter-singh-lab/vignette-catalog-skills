# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets==15.0.1"]
# ///
"""Regression tests for the compact catalog scripts."""

from __future__ import annotations

import importlib.util
import json
import multiprocessing
import os
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
