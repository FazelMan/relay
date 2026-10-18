#!/usr/bin/env python3
"""Schema validation tests."""

from __future__ import annotations

import unittest

from relay.schema import empty_checkpoint, merge_checkpoint, validate_checkpoint


class SchemaTests(unittest.TestCase):
    def test_empty_valid(self) -> None:
        cp = empty_checkpoint(task_id="demo")
        self.assertEqual(validate_checkpoint(cp), [])

    def test_missing_required(self) -> None:
        errs = validate_checkpoint({"schema_version": "1.0.0"})
        self.assertTrue(any("missing" in e for e in errs))

    def test_bad_status(self) -> None:
        cp = empty_checkpoint(task_id="demo")
        cp["task"]["status"] = "nope"
        self.assertTrue(any("status" in e for e in validate_checkpoint(cp)))

    def test_merge_preserves_and_updates(self) -> None:
        base = empty_checkpoint(task_id="demo", objective="A")
        merged = merge_checkpoint(base, {"task": {"objective": "B", "completed": ["x"]}})
        self.assertEqual(merged["task"]["objective"], "B")
        self.assertEqual(merged["task"]["completed"], ["x"])
        self.assertNotEqual(merged["checkpoint_id"], base["checkpoint_id"])


if __name__ == "__main__":
    unittest.main()
