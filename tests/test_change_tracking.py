#!/usr/bin/env python3
"""Tests for append-only handoff change-event snapshots."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from relay.change_tracking import record_change_event
from relay.config import Config
from relay.schema import empty_checkpoint


class ChangeTrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.config = Config(storage_dir="plans/handoffs", history_limit=3)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_first_checkpoint_creates_initial_event_without_touching_project_files(self) -> None:
        project_file = self.workspace / "user-work.txt"
        project_file.write_text("keep me", encoding="utf-8")
        checkpoint = empty_checkpoint(task_id="feature-a", workspace_path=str(self.workspace))
        event_path = record_change_event(self.workspace, self.config, "feature-a", None, checkpoint)
        self.assertIsNotNone(event_path)
        event = json.loads(event_path.read_text(encoding="utf-8"))
        self.assertEqual(event["kind"], "initial_snapshot")
        self.assertEqual(project_file.read_text(encoding="utf-8"), "keep me")
        self.assertIn("limitations", event)

    def test_task_state_change_is_recorded(self) -> None:
        before = empty_checkpoint(task_id="feature-a")
        after = empty_checkpoint(task_id="feature-a")
        after["task"]["next_steps"] = ["add regression tests"]
        event_path = record_change_event(self.workspace, self.config, "feature-a", before, after)
        self.assertIsNotNone(event_path)
        event = json.loads(event_path.read_text(encoding="utf-8"))
        self.assertTrue(event["task_state"]["changed"])
        self.assertEqual(event["task_state"]["after"]["next_steps"], ["add regression tests"])

    def test_identical_checkpoint_observation_is_noop(self) -> None:
        before = empty_checkpoint(task_id="feature-a")
        before["repository"] = {
            "root": str(self.workspace), "identity": "", "branch": None, "head": None,
            "working_tree": "unknown", "changed_paths": [], "staged_paths": [],
            "unstaged_paths": [], "untracked_paths": [], "git_available": False,
        }
        after = json.loads(json.dumps(before))
        self.assertIsNone(record_change_event(self.workspace, self.config, "feature-a", before, after))


if __name__ == "__main__":
    unittest.main()
