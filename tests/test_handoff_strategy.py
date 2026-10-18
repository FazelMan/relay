#!/usr/bin/env python3
"""Persistent handoff strategy defaults and validation."""

from __future__ import annotations

import unittest

from relay.config import Config, config_from_mapping


class HandoffStrategyConfigTests(unittest.TestCase):
    def test_defaults_favor_cost_efficient_quality(self) -> None:
        config = Config()
        self.assertEqual(config.handoff_mode, "suggest")
        self.assertEqual(config.handoff_optimize_for, "value")
        self.assertEqual(config.handoff_detail, "standard")

    def test_user_preferences_are_loaded_and_persist_as_config(self) -> None:
        config = config_from_mapping({
            "handoff_mode": "prepare",
            "handoff_optimize_for": "quality",
            "handoff_detail": "full",
        })
        self.assertEqual(config.handoff_mode, "prepare")
        self.assertEqual(config.handoff_optimize_for, "quality")
        self.assertEqual(config.handoff_detail, "full")

    def test_invalid_preferences_are_rejected(self) -> None:
        for key, value in (
            ("handoff_mode", "automatic-agent-switch"),
            ("handoff_optimize_for", "free"),
            ("handoff_detail", "huge"),
        ):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    config_from_mapping({key: value})


if __name__ == "__main__":
    unittest.main()
