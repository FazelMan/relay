#!/usr/bin/env python3
"""CLI tests for handoff history management and duplicate detection."""

from __future__ import annotations

import unittest

from relay.cli import _stable_handoff_text, build_parser


class HandoffCliTests(unittest.TestCase):
    def test_timestamp_does_not_make_handoff_look_changed(self) -> None:
        first = "# Handoff: task\n\n> **Updated:** 2026-10-18T10:00:00Z\n> **Task ID:** `abc`"
        second = "# Handoff: task\n\n> **Updated:** 2026-10-18T10:05:00Z\n> **Task ID:** `abc`"
        self.assertEqual(_stable_handoff_text(first), _stable_handoff_text(second))

    def test_real_content_change_is_detected(self) -> None:
        first = "# Handoff: task\n\n> **Updated:** 2026-10-18T10:00:00Z\n\nNext: A"
        second = "# Handoff: task\n\n> **Updated:** 2026-10-18T10:05:00Z\n\nNext: B"
        self.assertNotEqual(_stable_handoff_text(first), _stable_handoff_text(second))

    def test_legacy_handoff_save_cli_still_parses(self) -> None:
        args = build_parser().parse_args(["handoff", "--task", "abc"])
        self.assertEqual(args.command, "handoff")
        self.assertEqual(args.task, "abc")
        self.assertIsNone(args.handoff_command)

    def test_list_and_delete_commands_parse(self) -> None:
        parser = build_parser()
        listed = parser.parse_args(["handoff", "list"])
        deleted = parser.parse_args(["handoff", "delete", "abc", "--yes"])
        self.assertEqual(listed.handoff_command, "list")
        self.assertEqual(deleted.handoff_command, "delete")
        self.assertEqual(deleted.task_id, "abc")
        self.assertTrue(deleted.yes)


if __name__ == "__main__":
    unittest.main()
