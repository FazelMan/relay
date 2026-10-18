#!/usr/bin/env python3
"""Resume reconciliation tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from relay.config import Config
from relay.handoff_md import render_handoff
from relay.resume import prepare_resume
from relay.schema import empty_checkpoint
from relay.storage import atomic_write_text, handoff_path, save_checkpoint


class ResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.config = Config()
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed(self, **task_overrides):
        cp = empty_checkpoint(task_id="demo", objective="Demo task")
        cp["task"].update(task_overrides)
        cp["task"]["relevant_paths"] = ["src/app.py"]
        cp["task"]["next_steps"] = ["Wire middleware", "Add tests"]
        cp["repository"]["branch"] = "main"
        cp["repository"]["head"] = "abc123"
        cp["repository"]["working_tree"] = "clean"
        save_checkpoint(self.workspace, self.config, cp)
        atomic_write_text(
            handoff_path(self.workspace, self.config, "demo"), render_handoff(cp)
        )
        return cp

    def test_successful_resume_prep(self) -> None:
        self._seed()
        report = prepare_resume(self.workspace, self.config, "demo")
        self.assertTrue(report.valid)
        self.assertEqual(report.next_steps[0], "Wire middleware")
        self.assertTrue(report.handoff_path)

    def test_missing_file(self) -> None:
        self._seed(relevant_paths=["src/missing.py"])
        # override relevant_paths properly
        cp = empty_checkpoint(task_id="demo2", objective="x")
        cp["task"]["relevant_paths"] = ["src/does-not-exist.py"]
        cp["task"]["next_steps"] = ["fix file"]
        save_checkpoint(self.workspace, self.config, cp)
        report = prepare_resume(self.workspace, self.config, "demo2")
        self.assertTrue(report.valid)
        self.assertTrue(any("missing" in d for d in report.discrepancies))

    def test_multiple_tasks_require_id(self) -> None:
        self._seed()
        cp = empty_checkpoint(task_id="other", objective="y")
        save_checkpoint(self.workspace, self.config, cp)
        report = prepare_resume(self.workspace, self.config, None)
        self.assertFalse(report.valid)
        self.assertTrue(any("multiple" in d for d in report.discrepancies))

    def test_cross_agent_portable_artifacts(self) -> None:
        self._seed()
        report = prepare_resume(self.workspace, self.config, "demo")
        self.assertTrue(Path(report.handoff_path).is_file())
        self.assertTrue(Path(report.checkpoint_path).is_file())
        text = Path(report.handoff_path).read_text(encoding="utf-8")
        self.assertIn("Validate workspace before editing", text)
        self.assertIn("Demo task", text)


if __name__ == "__main__":
    unittest.main()
