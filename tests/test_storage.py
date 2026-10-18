#!/usr/bin/env python3
"""Checkpoint storage, atomic write, retention, corruption recovery."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from relay.config import Config
from relay.schema import empty_checkpoint
from relay.secrets import scrub
from relay.storage import (
    StorageError,
    checkpoint_path,
    latest_valid_checkpoint,
    load_checkpoint,
    save_checkpoint,
)


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.config = Config(storage_dir="plans/handoffs", history_limit=2)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_save_and_load(self) -> None:
        cp = empty_checkpoint(task_id="feat-a", objective="Ship A")
        path = save_checkpoint(self.workspace, self.config, cp)
        loaded = load_checkpoint(path)
        self.assertEqual(loaded["task_id"], "feat-a")
        self.assertEqual(loaded["task"]["objective"], "Ship A")

    def test_atomic_replace_keeps_history(self) -> None:
        cp = empty_checkpoint(task_id="feat-a")
        save_checkpoint(self.workspace, self.config, cp)
        cp2 = empty_checkpoint(task_id="feat-a", objective="updated")
        save_checkpoint(self.workspace, self.config, cp2)
        hist = self.workspace / "plans/handoffs/feat-a/history"
        self.assertTrue(hist.is_dir())
        self.assertGreaterEqual(len(list(hist.glob("checkpoint-*.json"))), 1)

    def test_retention(self) -> None:
        for i in range(5):
            cp = empty_checkpoint(task_id="feat-a", objective=str(i))
            save_checkpoint(self.workspace, self.config, cp)
        hist = list((self.workspace / "plans/handoffs/feat-a/history").glob("checkpoint-*.json"))
        self.assertLessEqual(len(hist), self.config.history_limit)

    def test_corrupt_fallback(self) -> None:
        cp = empty_checkpoint(task_id="feat-a", objective="good")
        save_checkpoint(self.workspace, self.config, cp)
        # Force another save so history has good copy
        cp2 = empty_checkpoint(task_id="feat-a", objective="good2")
        save_checkpoint(self.workspace, self.config, cp2)
        path = checkpoint_path(self.workspace, self.config, "feat-a")
        path.write_text("{not-json", encoding="utf-8")
        data, used_path, err = latest_valid_checkpoint(self.workspace, self.config, "feat-a")
        self.assertIsNotNone(data)
        self.assertIsNotNone(err)
        self.assertIn("history", str(used_path))

    def test_path_traversal_blocked(self) -> None:
        bad = Config(storage_dir="../outside")
        with self.assertRaises(StorageError):
            save_checkpoint(self.workspace, bad, empty_checkpoint(task_id="x"))

    def test_secret_scrub(self) -> None:
        cp = empty_checkpoint(task_id="feat-a")
        cp["task"]["blockers"] = ["token=sk-abcdefghijklmnopqrstuvwxyz123456"]
        cp["notes"] = {"api_key": "super-secret"}
        cleaned = scrub(cp)
        blob = json.dumps(cleaned)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", blob)
        self.assertNotIn("super-secret", blob)


if __name__ == "__main__":
    unittest.main()
