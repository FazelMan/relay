#!/usr/bin/env python3
"""Cross-agent resume fixtures (portable artifacts only — no live host sessions)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from relay.config import Config
from relay.handoff_md import render_handoff
from relay.resume import prepare_resume
from relay.storage import atomic_write_text, handoff_path, save_checkpoint


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cross_agent"


class CrossAgentResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.config = Config()
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _materialize(self, name: str) -> str:
        src = FIXTURES / name
        data = json.loads((src / "checkpoint.json").read_text(encoding="utf-8"))
        task_id = data["task_id"]
        # Point relevant paths at local workspace files that exist
        data["task"]["relevant_paths"] = ["src/app.py"]
        data["repository"]["root"] = str(self.workspace)
        save_checkpoint(self.workspace, self.config, data)
        handoff_src = src / "HANDOFF.md"
        if handoff_src.is_file():
            atomic_write_text(
                handoff_path(self.workspace, self.config, task_id),
                handoff_src.read_text(encoding="utf-8"),
            )
        else:
            atomic_write_text(
                handoff_path(self.workspace, self.config, task_id),
                render_handoff(data),
            )
        return task_id

    def test_claude_to_cursor_fixture(self) -> None:
        task_id = self._materialize("claude_to_cursor")
        report = prepare_resume(self.workspace, self.config, task_id)
        self.assertTrue(report.valid)
        self.assertIn("cursor", report.host_hints)
        self.assertIn("python3 -m relay resume", report.host_hints["cursor"])
        self.assertIn("session_launch", report.host_hints)
        self.assertIn("not supported", report.host_hints["session_launch"])
        self.assertFalse(report.to_dict()["overwrite_user_changes"])
        self.assertIn("Continue task", report.continuation_instruction)
        self.assertIn(task_id, report.continuation_instruction)

    def test_claude_to_codex_fixture(self) -> None:
        task_id = self._materialize("claude_to_codex")
        report = prepare_resume(self.workspace, self.config, task_id)
        self.assertTrue(report.valid)
        self.assertIn("$handoff resume", report.host_hints["codex"])
        self.assertTrue(report.next_steps)
        self.assertIn(report.next_steps[0], report.continuation_instruction)


if __name__ == "__main__":
    unittest.main()
