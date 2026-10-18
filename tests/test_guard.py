#!/usr/bin/env python3
"""Guard risk transitions and warning dedupe."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from relay.config import Thresholds
from relay.guard import WarningDeduper, evaluate_risk
from relay.monitor import context_from_utilization, quota_from_rate_limit, unsupported_quota


class GuardTests(unittest.TestCase):
    def test_thresholds(self) -> None:
        thr = Thresholds(0.65, 0.80, 0.90)
        healthy = evaluate_risk(
            context=context_from_utilization(0.50, source="t"),
            quota=unsupported_quota(),
            thresholds=thr,
        )
        self.assertEqual(healthy.state, "healthy")

        elevated = evaluate_risk(
            context=context_from_utilization(0.70, source="t"),
            quota=unsupported_quota(),
            thresholds=thr,
        )
        self.assertEqual(elevated.context_state, "elevated")
        self.assertTrue(elevated.should_warn)

        critical = evaluate_risk(
            context=context_from_utilization(0.95, source="t"),
            quota=unsupported_quota(),
            thresholds=thr,
        )
        self.assertEqual(critical.context_state, "critical")
        self.assertTrue(critical.should_prepare_handoff)

    def test_quota_separate_from_context(self) -> None:
        thr = Thresholds(0.65, 0.80, 0.90)
        decision = evaluate_risk(
            context=context_from_utilization(0.10, source="t"),
            quota=quota_from_rate_limit(source="provider"),
            thresholds=thr,
        )
        self.assertEqual(decision.context_state, "healthy")
        self.assertEqual(decision.quota_state, "critical")
        self.assertEqual(decision.state, "critical")

    def test_unsupported_does_not_fake_pct(self) -> None:
        thr = Thresholds(0.65, 0.80, 0.90)
        decision = evaluate_risk(
            context=None,
            quota=None,
            thresholds=thr,
        )
        self.assertEqual(decision.context_state, "healthy")

    def test_warning_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guard.json"
            d = WarningDeduper(path, cooldown_seconds=60)
            d.load()
            self.assertTrue(d.should_emit("critical", now=1000))
            d.save()
            d2 = WarningDeduper(path, cooldown_seconds=60)
            d2.load()
            self.assertFalse(d2.should_emit("critical", now=1030))
            self.assertTrue(d2.should_emit("critical", now=1070))


if __name__ == "__main__":
    unittest.main()
