#!/usr/bin/env python3
"""Guard risk transitions and warning dedupe."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from relay.config import Thresholds
from relay.guard import WarningDeduper, evaluate_risk
from relay.monitor import (
    Observation,
    context_from_utilization,
    quota_from_rate_limit,
    unsupported_context,
    unsupported_quota,
)


class GuardTests(unittest.TestCase):
    def test_distinct_thresholds_and_boundaries(self) -> None:
        thr = Thresholds(0.65, 0.80, 0.90)

        def band(pct: float) -> str:
            return evaluate_risk(
                context=context_from_utilization(pct / 100.0, source="t"),
                quota=unsupported_quota(),
                thresholds=thr,
            ).context_state

        self.assertEqual(band(64.9), "healthy")
        self.assertEqual(band(65.0), "early")
        self.assertEqual(band(79.9), "early")
        self.assertEqual(band(80.0), "elevated")
        self.assertEqual(band(89.9), "elevated")
        self.assertEqual(band(90.0), "critical")

    def test_early_warning_message(self) -> None:
        thr = Thresholds(0.65, 0.80, 0.90)
        d = evaluate_risk(
            context=context_from_utilization(0.70, source="t"),
            quota=unsupported_quota(),
            thresholds=thr,
        )
        self.assertEqual(d.warning_level, "early")
        self.assertTrue(d.should_warn)
        self.assertIn("Early", d.warning_message or "")

    def test_quota_separate_from_context(self) -> None:
        thr = Thresholds(0.65, 0.80, 0.90)
        decision = evaluate_risk(
            context=context_from_utilization(0.10, source="t"),
            quota=quota_from_rate_limit(source="provider"),
            thresholds=thr,
        )
        self.assertEqual(decision.context_state, "healthy")
        self.assertEqual(decision.quota_state, "critical")
        self.assertEqual(decision.warning_level, "critical")

    def test_unsupported_does_not_fake_pct(self) -> None:
        thr = Thresholds(0.65, 0.80, 0.90)
        decision = evaluate_risk(
            context=unsupported_context(source="t"),
            quota=None,
            thresholds=thr,
        )
        self.assertEqual(decision.context_state, "healthy")
        self.assertEqual(decision.warning_level, "healthy")
        # Must not claim a numeric utilization percentage
        self.assertNotRegex(decision.reason, r"utilization ~\d+%")

    def test_stale_signal_ignored(self) -> None:
        thr = Thresholds(0.65, 0.80, 0.90)
        stale = Observation(
            kind="context",
            utilization=0.95,
            reliability="stale",
            source="old",
        )
        decision = evaluate_risk(
            context=stale, quota=unsupported_quota(), thresholds=thr
        )
        self.assertEqual(decision.context_state, "healthy")
        self.assertEqual(decision.warning_level, "healthy")

    def test_early_does_not_suppress_critical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guard.json"
            d = WarningDeduper(path, cooldown_seconds=300)
            d.load()
            self.assertTrue(
                d.should_emit(
                    warning_level="early", task_id="t1", session_id="s1", now=1000
                )
            )
            d.save()
            d2 = WarningDeduper(path, cooldown_seconds=300)
            d2.load()
            # Same early within cooldown suppressed
            self.assertFalse(
                d2.should_emit(
                    warning_level="early", task_id="t1", session_id="s1", now=1100
                )
            )
            # Critical always escalates
            self.assertTrue(
                d2.should_emit(
                    warning_level="critical", task_id="t1", session_id="s1", now=1101
                )
            )

    def test_dedupe_scoped_by_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guard.json"
            d = WarningDeduper(path, cooldown_seconds=300)
            d.load()
            self.assertTrue(
                d.should_emit(warning_level="elevated", task_id="a", now=1000)
            )
            self.assertTrue(
                d.should_emit(warning_level="elevated", task_id="b", now=1001)
            )

    def test_recovery_resets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guard.json"
            d = WarningDeduper(path, cooldown_seconds=300)
            d.load()
            d.should_emit(warning_level="critical", task_id="t", now=1000)
            d.note_recovery(task_id="t")
            # After recovery, early is an escalation from healthy
            self.assertTrue(
                d.should_emit(warning_level="early", task_id="t", now=1001)
            )


if __name__ == "__main__":
    unittest.main()
