"""Handoff Guard — risk state evaluation with deduplicated warnings."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Config, Thresholds
from .monitor import Observation
from .schema import RISK_STATES


@dataclass
class GuardDecision:
    state: str
    context_state: str
    quota_state: str
    reason: str
    should_warn: bool
    should_mechanical_checkpoint: bool
    should_prepare_handoff: bool
    warning_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "context_state": self.context_state,
            "quota_state": self.quota_state,
            "reason": self.reason,
            "should_warn": self.should_warn,
            "should_mechanical_checkpoint": self.should_mechanical_checkpoint,
            "should_prepare_handoff": self.should_prepare_handoff,
            "warning_message": self.warning_message,
        }


def _band(utilization: float | None, thresholds: Thresholds) -> str:
    if utilization is None:
        return "healthy"  # unknown does not imply elevated
    if utilization >= thresholds.critical:
        return "critical"
    if utilization >= thresholds.elevated:
        return "elevated"
    if utilization >= thresholds.early:
        return "elevated"  # early warning maps to elevated band
    return "healthy"


def evaluate_risk(
    *,
    context: Observation | None,
    quota: Observation | None,
    thresholds: Thresholds,
    session_interrupted: bool = False,
    handoff_artifacts_ready: bool = False,
    resuming: bool = False,
) -> GuardDecision:
    if resuming:
        return GuardDecision(
            state="resuming",
            context_state="healthy",
            quota_state="healthy",
            reason="resume in progress",
            should_warn=False,
            should_mechanical_checkpoint=False,
            should_prepare_handoff=False,
        )
    if session_interrupted:
        return GuardDecision(
            state="interrupted",
            context_state=_band(
                context.utilization if context and context.reliability == "valid" else None,
                thresholds,
            ),
            quota_state=(
                "critical"
                if quota and quota.reliability == "rate_limited"
                else "healthy"
            ),
            reason="session interrupted",
            should_warn=True,
            should_mechanical_checkpoint=True,
            should_prepare_handoff=True,
            warning_message="Session interrupted — use latest checkpoint/HANDOFF.md to continue elsewhere.",
        )

    ctx_state = "healthy"
    ctx_reason = "context unsupported or unknown"
    if context and context.reliability == "valid" and context.utilization is not None:
        ctx_state = _band(context.utilization, thresholds)
        pct = int(context.utilization * 100)
        ctx_reason = f"context utilization ~{pct}% ({context.source})"
    elif context and context.reliability in ("stale", "historical"):
        ctx_state = "healthy"
        ctx_reason = f"context signal {context.reliability} — not treated as live"

    quota_state = "healthy"
    quota_reason = "quota unsupported or unknown"
    if quota:
        if quota.reliability == "rate_limited" or quota.status == "rate_limited":
            quota_state = "critical"
            quota_reason = f"provider rate limit ({quota.source})"
        elif quota.reliability == "valid" and quota.status in ("exhausted", "critical"):
            quota_state = "critical"
            quota_reason = f"quota {quota.status}"
        elif quota.reliability == "valid" and quota.status == "elevated":
            quota_state = "elevated"
            quota_reason = f"quota elevated ({quota.source})"

    # Combined state: worst of context/quota, never imply quota safe from low context.
    rank = {"healthy": 0, "elevated": 1, "critical": 2}
    worst = max(ctx_state, quota_state, key=lambda s: rank.get(s, 0))
    reason = f"context: {ctx_reason}; quota: {quota_reason}"

    if handoff_artifacts_ready and worst in ("elevated", "critical"):
        state = "handoff_ready"
    else:
        state = worst if worst in RISK_STATES else "healthy"

    should_checkpoint = worst in ("elevated", "critical") or (
        context is not None and context.reliability == "unsupported"
    )
    # Always allow mechanical checkpoint on risk; also encourage proactive when unsupported.
    should_handoff = worst == "critical" or (
        handoff_artifacts_ready and worst == "elevated"
    )
    warn = worst in ("elevated", "critical")
    message = None
    if worst == "critical":
        message = (
            "Critical continuity risk (context and/or quota). "
            "Mechanical checkpoint recommended; open HANDOFF.md in another agent if needed. "
            f"Details — {reason}"
        )
    elif worst == "elevated":
        message = (
            "Elevated continuity risk. Consider refreshing the handoff soon. "
            f"Details — {reason}"
        )

    return GuardDecision(
        state=state,
        context_state=ctx_state,
        quota_state=quota_state,
        reason=reason,
        should_warn=warn,
        should_mechanical_checkpoint=should_checkpoint,
        should_prepare_handoff=should_handoff,
        warning_message=message,
    )


@dataclass
class WarningDeduper:
    path: Path
    cooldown_seconds: int
    _state: dict[str, Any] = field(default_factory=dict)

    def load(self) -> None:
        if self.path.is_file():
            try:
                self._state = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._state = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._state, indent=2) + "\n", encoding="utf-8")

    def should_emit(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        last = float(self._state.get(key, 0))
        if now - last < self.cooldown_seconds:
            return False
        self._state[key] = now
        return True


def local_state_path(workspace: Path) -> Path:
    return workspace / ".relay" / "local" / "guard-state.json"


def apply_guard_to_checkpoint(
    checkpoint: dict[str, Any], decision: GuardDecision
) -> dict[str, Any]:
    checkpoint = dict(checkpoint)
    checkpoint["risk"] = {
        "state": decision.state,
        "context_state": decision.context_state,
        "quota_state": decision.quota_state,
        "reason": decision.reason,
    }
    return checkpoint
