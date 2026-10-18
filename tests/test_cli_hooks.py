#!/usr/bin/env python3
"""CLI and hook smoke tests (no LLM, no network)."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from relay.active_task import MECHANICAL_FALLBACK_ID
from relay.cli import main


class CliHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, dict]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main([*argv, "--workspace", str(self.workspace)])
        text = buf.getvalue().strip()
        # Last JSON object if multiple / noise
        data = json.loads(text) if text.startswith("{") else {"raw": text}
        return code, data

    def test_checkpoint_and_status(self) -> None:
        code, data = self._run(
            "checkpoint", "--task", "t1", "--objective", "Obj", "--write-handoff"
        )
        self.assertEqual(code, 0)
        self.assertTrue(data["ok"])
        self.assertTrue(Path(data["handoff"]).is_file())
        code, status = self._run("status", "--task", "t1")
        self.assertEqual(code, 0)
        self.assertTrue(status["checkpoint_valid"])
        self.assertTrue(status["cross_agent_ready"])
        self.assertEqual(status["active_task"], "t1")

    def test_hook_without_task_uses_mechanical_fallback(self) -> None:
        event = json.dumps({"hook_event_name": "PreCompact", "trigger": "auto"})
        buf = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(event)), redirect_stdout(buf):
            code = main(
                [
                    "hook",
                    "--host",
                    "claude-code",
                    "--event",
                    "PreCompact",
                    "--workspace",
                    str(self.workspace),
                ]
            )
        self.assertEqual(code, 0)
        out = json.loads(buf.getvalue())
        self.assertFalse(out["llm_invoked"])
        self.assertTrue(out["ok"])
        self.assertEqual(
            out["task_resolution"]["task_id"], MECHANICAL_FALLBACK_ID
        )
        self.assertTrue(out["task_resolution"]["is_mechanical_fallback"])
        self.assertIsNotNone(out["checkpoint"])
        self.assertIn(MECHANICAL_FALLBACK_ID, out["checkpoint"])

    def test_hook_respects_active_task(self) -> None:
        self._run("task", "set", "active-feat")
        event = json.dumps({"hook_event_name": "PreCompact"})
        buf = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(event)), redirect_stdout(buf):
            code = main(
                [
                    "hook",
                    "--host",
                    "claude-code",
                    "--event",
                    "PreCompact",
                    "--workspace",
                    str(self.workspace),
                ]
            )
        self.assertEqual(code, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["task_resolution"]["task_id"], "active-feat")
        self.assertFalse(out["task_resolution"]["is_mechanical_fallback"])

    def test_hook_invalid_json_fails(self) -> None:
        buf = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("{not-json")), redirect_stdout(buf):
            code = main(
                [
                    "hook",
                    "--host",
                    "codex",
                    "--event",
                    "PreCompact",
                    "--workspace",
                    str(self.workspace),
                ]
            )
        self.assertEqual(code, 2)
        out = json.loads(buf.getvalue())
        self.assertFalse(out["ok"])
        self.assertIsNone(out["checkpoint"])

    def test_guard_eval_critical(self) -> None:
        code, data = self._run(
            "guard-eval", "--context-pct", "95", "--task", "t1", "--no-dedupe"
        )
        self.assertEqual(code, 0)
        self.assertEqual(data["context_state"], "critical")
        self.assertEqual(data["warning_level"], "critical")

    def test_validate_rejects_bad(self) -> None:
        bad = self.workspace / "bad.json"
        bad.write_text("{}", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["validate", str(bad)])
        self.assertNotEqual(code, 0)

    def test_resume_emits_continuation_instruction(self) -> None:
        self._run(
            "handoff",
            "--task",
            "resume-me",
            "--objective",
            "Do thing",
        )
        # handoff without prior checkpoint now creates base
        code, data = self._run("resume", "--task", "resume-me")
        self.assertEqual(code, 0)
        self.assertIn("continuation_instruction", data)
        self.assertIn("resume-me", data["continuation_instruction"])
        self.assertFalse(data["overwrite_user_changes"])


if __name__ == "__main__":
    unittest.main()
