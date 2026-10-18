"""Handoff Guard — risk state evaluation with deduplicated warnings."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Thresholds
from .monitor import Observation

# Distinct context bands (thresholds early / elevated / critical).
CONTEXT_BANDS = ("healthy", "early", "elevated", "critical")
BAND_RANK = {"healthy": 0, "early": 1, "elevated": 2, "critical": 3}

# Combined user-facing risk states.
RISK_RANK = {
    "healthy": 0,
    "early": 1,
    "elevated": 2,
    "critical": 3,
    "handoff_ready": 3,
    "interrupted": 3,
    "resuming": 0,
}


@dataclass
class GuardDecision:
    state: str
    context_state: str
    quota_state: str
    warning_level: str  # healthy | early | elevated | critical
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
            "warning_level": self.warning_level,
            "reason": self.reason,
            "should_warn": self.should_warn,
            "should_mechanical_checkpoint": self.should_mechanical_checkpoint,
            "should_prepare_handoff": self.should_prepare_handoff,
            "warning_message": self.warning_message,
        }


def _band(utilization: float | None, thresholds: Thresholds) -> str:
    """Map utilization to a distinct band. Boundaries are inclusive of the higher band."""
    if utilization is None:
        return "healthy"
    if utilization >= thresholds.critical:
        return "critical"
    if utilization >= thresholds.elevated:
        return "elevated"
    if utilization >= thresholds.early:
        return "early"
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
            warning_level="healthy",
            reason="resume in progress",
            should_warn=False,
            should_mechanical_checkpoint=False,
            should_prepare_handoff=False,
        )
    if session_interrupted:
        ctx = _band(
            context.utilization if context and context.reliability == "valid" else None,
            thresholds,
        )
        q = (
            "critical"
            if quota and quota.reliability == "rate_limited"
            else "healthy"
        )
        return GuardDecision(
            state="interrupted",
            context_state=ctx,
            quota_state=q,
            warning_level="critical",
            reason="session interrupted",
            should_warn=True,
            should_mechanical_checkpoint=True,
            should_prepare_handoff=True,
            warning_message=(
                "Session interrupted — use latest checkpoint/HANDOFF.md to continue elsewhere."
            ),
        )

    ctx_state = "healthy"
    ctx_reason = "context unsupported or unknown"
    if context and context.reliability == "valid" and context.utilization is not None:
        ctx_state = _band(context.utilization, thresholds)
        pct = int(round(context.utilization * 100))
        ctx_reason = f"context utilization ~{pct}% ({context.source})"
    elif context and context.reliability in ("stale", "historical"):
        ctx_state = "healthy"
        ctx_reason = f"context signal {context.reliability} — not treated as live"
    elif context and context.reliability in ("unsupported", "unavailable", "unknown"):
        ctx_reason = f"context reliability={context.reliability} (no invented %)"

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
        elif quota.reliability == "valid" and quota.status == "early":
            quota_state = "early"
            quota_reason = f"quota early ({quota.source})"

    warning_level = max(
        [ctx_state, quota_state],
        key=lambda s: BAND_RANK.get(s, 0),
    )
    reason = f"context: {ctx_reason}; quota: {quota_reason}"

    if handoff_artifacts_ready and warning_level in ("elevated", "critical"):
        state = "handoff_ready"
    else:
        state = warning_level

    should_checkpoint = warning_level in ("early", "elevated", "critical")
    # Unsupported telemetry: still allow optional mechanical checkpoint, but do not warn.
    if (
        context is not None
        and context.reliability == "unsupported"
        and warning_level == "healthy"
    ):
        should_checkpoint = True

    should_handoff = warning_level == "critical" or (
        handoff_artifacts_ready and warning_level == "elevated"
    )
    warn = warning_level in ("early", "elevated", "critical")
    message = None
    if warning_level == "critical":
        message = (
            "Critical continuity risk (context and/or quota). "
            "Mechanical checkpoint recommended; open HANDOFF.md in another agent if needed. "
            f"Details — {reason}"
        )
    elif warning_level == "elevated":
        message = (
            "Elevated continuity risk. Refresh the handoff soon. "
            f"Details — {reason}"
        )
    elif warning_level == "early":
        message = (
            "Early continuity warning. Consider a mechanical checkpoint. "
            f"Details — {reason}"
        )

    return GuardDecision(
        state=state,
        context_state=ctx_state,
        quota_state=quota_state,
        warning_level=warning_level,
        reason=reason,
        should_warn=warn,
        should_mechanical_checkpoint=should_checkpoint,
        should_prepare_handoff=should_handoff,
        warning_message=message,
    )


@dataclass
class WarningDeduper:
    """Deduplicate warnings per task/session, but never suppress a higher risk level."""

    path: Path
    cooldown_seconds: int
    _state: dict[str, Any] = field(default_factory=dict)

    def load(self) -> None:
        if self.path.is_file():
            try:
                self._state = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._state = {}
        if "entries" not in self._state:
            # Migrate legacy flat timestamp map if present.
            legacy = {
                k: v
                for k, v in self._state.items()
                if k not in ("entries",) and isinstance(v, (int, float))
            }
            self._state = {"entries": {}}
            for k, ts in legacy.items():
                self._state["entries"][k] = {"level": "unknown", "ts": float(ts)}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._state, indent=2) + "\n", encoding="utf-8")

    def _scope_key(self, task_id: str, session_id: str | None) -> str:
        sid = session_id or "no-session"
        return f"{task_id}|{sid}"

    def should_emit(
        self,
        *,
        warning_level: str,
        task_id: str,
        session_id: str | None = None,
        now: float | None = None,
    ) -> bool:
        now = time.time() if now is None else now
        if warning_level == "healthy":
            self.note_recovery(task_id=task_id, session_id=session_id)
            return False

        entries: dict[str, Any] = self._state.setdefault("entries", {})
        key = self._scope_key(task_id, session_id)
        prev = entries.get(key) or {}
        prev_level = str(prev.get("level") or "healthy")
        prev_ts = float(prev.get("ts") or 0)
        new_rank = BAND_RANK.get(warning_level, 0)
        old_rank = BAND_RANK.get(prev_level, 0)

        # Escalation always emits (early must not suppress critical).
        if new_rank > old_rank:
            entries[key] = {"level": warning_level, "ts": now}
            return True

        # Same or lower level: respect cooldown.
        if now - prev_ts < self.cooldown_seconds:
            return False
        entries[key] = {"level": warning_level, "ts": now}
        return True

    def note_recovery(self, *, task_id: str, session_id: str | None = None) -> None:
        """Reset escalation baseline when risk returns to healthy."""
        entries: dict[str, Any] = self._state.setdefault("entries", {})
        key = self._scope_key(task_id, session_id)
        if key in entries:
            entries[key] = {"level": "healthy", "ts": time.time()}


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
        "warning_level": decision.warning_level,
        "reason": decision.reason,
    }
    return checkpoint
