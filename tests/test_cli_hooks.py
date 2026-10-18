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

    def test_hook_precompact_no_llm(self) -> None:
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
                    "--task",
                    "t1",
                    "--workspace",
                    str(self.workspace),
                ]
            )
        self.assertEqual(code, 0)
        out = json.loads(buf.getvalue())
        self.assertFalse(out["llm_invoked"])
        self.assertIn("checkpoint", out)

    def test_guard_eval_critical(self) -> None:
        code, data = self._run(
            "guard-eval", "--context-pct", "95", "--task", "t1", "--no-dedupe"
        )
        self.assertEqual(code, 0)
        self.assertEqual(data["context_state"], "critical")

    def test_validate_rejects_bad(self) -> None:
        bad = self.workspace / "bad.json"
        bad.write_text("{}", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["validate", str(bad)])
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
