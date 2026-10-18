#!/usr/bin/env python3
from __future__ import annotations

import unittest

from relay.monitor import context_from_token_counts, parse_claude_session_start


class MonitorTests(unittest.TestCase):
    def test_token_counts(self) -> None:
        obs = context_from_token_counts(50, 100, source="t")
        self.assertEqual(obs.utilization, 0.5)
        self.assertEqual(obs.reliability, "valid")

    def test_session_start_without_capacity(self) -> None:
        obs = parse_claude_session_start({"context_tokens": 1000}, capacity_tokens=None)
        self.assertIsNone(obs.utilization)
        self.assertEqual(obs.reliability, "unknown")

    def test_session_start_with_capacity(self) -> None:
        obs = parse_claude_session_start({"context_tokens": 50}, capacity_tokens=100)
        self.assertEqual(obs.utilization, 0.5)

    def test_missing_tokens_unsupported(self) -> None:
        obs = parse_claude_session_start({}, capacity_tokens=100)
        self.assertEqual(obs.reliability, "unsupported")


if __name__ == "__main__":
    unittest.main()
