#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from relay.active_task import (
    MECHANICAL_FALLBACK_ID,
    clear_active_task,
    resolve_task_id,
    set_active_task,
)
from relay.config import Config
from relay.schema import empty_checkpoint
from relay.storage import save_checkpoint


class ActiveTaskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.config = Config()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed(self, task_id: str) -> None:
        save_checkpoint(
            self.workspace, self.config, empty_checkpoint(task_id=task_id)
        )

    def test_explicit(self) -> None:
        r = resolve_task_id(self.workspace, self.config, "feat-a")
        self.assertEqual(r.source, "explicit")
        self.assertEqual(r.task_id, "feat-a")
        self.assertFalse(r.is_mechanical_fallback)

    def test_registry(self) -> None:
        set_active_task(self.workspace, "feat-b")
        r = resolve_task_id(self.workspace, self.config, None)
        self.assertEqual(r.source, "registry")
        self.assertEqual(r.task_id, "feat-b")

    def test_env(self) -> None:
        with mock.patch.dict(os.environ, {"RELAY_TASK": "from-env"}):
            r = resolve_task_id(self.workspace, self.config, None)
        self.assertEqual(r.source, "env")
        self.assertEqual(r.task_id, "from-env")

    def test_single_task_inference(self) -> None:
        self._seed("only-one")
        r = resolve_task_id(self.workspace, self.config, None)
        self.assertEqual(r.source, "single_task")
        self.assertEqual(r.task_id, "only-one")

    def test_multiple_tasks_fallback(self) -> None:
        self._seed("a")
        self._seed("b")
        r = resolve_task_id(self.workspace, self.config, None)
        self.assertTrue(r.is_mechanical_fallback)
        self.assertEqual(r.task_id, MECHANICAL_FALLBACK_ID)
        self.assertIn("multiple", r.message)

    def test_missing_identity_fallback(self) -> None:
        r = resolve_task_id(self.workspace, self.config, None)
        self.assertTrue(r.is_mechanical_fallback)
        self.assertEqual(r.task_id, MECHANICAL_FALLBACK_ID)

    def test_clear(self) -> None:
        set_active_task(self.workspace, "x")
        self.assertTrue(clear_active_task(self.workspace))
        self.assertFalse(clear_active_task(self.workspace))

    def test_never_registers_mechanical_as_active(self) -> None:
        from relay.storage import StorageError

        with self.assertRaises(StorageError):
            set_active_task(self.workspace, MECHANICAL_FALLBACK_ID)

    def test_unscoped_dir_does_not_become_semantic(self) -> None:
        self._seed(MECHANICAL_FALLBACK_ID)
        r = resolve_task_id(self.workspace, self.config, None)
        self.assertTrue(r.is_mechanical_fallback)
        self.assertEqual(r.task_id, MECHANICAL_FALLBACK_ID)


if __name__ == "__main__":
    unittest.main()
