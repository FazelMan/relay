#!/usr/bin/env python3
"""CLI tests for handoff history management and duplicate detection."""

from __future__ import annotations

import unittest

from relay.cli import _stable_checkpoint_data, _stable_handoff_text, build_parser


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

    def test_generated_checkpoint_identity_does_not_count_as_state_change(self) -> None:
        first = {"checkpoint_id": "one", "updated_at": "t1", "task": {"status": "in_progress"}}
        second = {"checkpoint_id": "two", "updated_at": "t2", "task": {"status": "in_progress"}}
        self.assertEqual(_stable_checkpoint_data(first), _stable_checkpoint_data(second))

    def test_repository_state_change_counts_as_real_change(self) -> None:
        first = {"task": {"status": "in_progress"}, "repository": {"changed_paths": ["a.py"]}}
        second = {"task": {"status": "in_progress"}, "repository": {"changed_paths": ["b.py"]}}
        self.assertNotEqual(_stable_checkpoint_data(first), _stable_checkpoint_data(second))


if __name__ == "__main__":
    unittest.main()
