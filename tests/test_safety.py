#!/usr/bin/env python3
"""Safety: path traversal, malformed instructions, no git mutation helpers."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

import relay.gitinfo as gitinfo
import relay.storage as storage
from relay.config import Config
from relay.paths import safe_join
from relay.schema import empty_checkpoint
from relay.storage import StorageError, save_checkpoint


class SafetyTests(unittest.TestCase):
    def test_safe_join_blocks_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with self.assertRaises(StorageError):
                safe_join(base, "..", "etc", "passwd")

    def test_gitinfo_has_no_mutating_commands(self) -> None:
        src = inspect.getsource(gitinfo)
        # Only read-only git invocations are allowed.
        allowed = {"rev-parse", "status", "config"}
        for match in __import__("re").findall(r'_run\(\s*[^,]+,\s*"([^"]+)"', src):
            self.assertIn(match, allowed)
        for banned in ("reset", "checkout", "commit", "push", "stash", "clean"):
            self.assertNotIn(f', "{banned}"', src)
            self.assertNotIn(f", '{banned}'", src)

    def test_storage_does_not_invoke_git_write(self) -> None:
        src = inspect.getsource(storage)
        self.assertNotIn("subprocess", src)

    def test_malformed_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            with self.assertRaises(StorageError):
                save_checkpoint(
                    workspace, Config(), empty_checkpoint(task_id="../evil")
                )


if __name__ == "__main__":
    unittest.main()
