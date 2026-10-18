"""Context and quota observation abstractions.

Never invent utilization percentages from character counts or transcript length.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schema import utc_now_iso


@dataclass
class Observation:
    kind: str  # context | quota
    utilization: float | None = None
    capacity: float | None = None
    remaining: float | None = None
    status: str | None = None
    source: str | None = None
    reliability: str = "unknown"
    observed_at: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.kind == "context":
            return {
                "utilization": self.utilization,
                "capacity": self.capacity,
                "remaining": self.remaining,
                "observed_at": self.observed_at or utc_now_iso(),
                "source": self.source,
                "reliability": self.reliability,
            }
        return {
            "status": self.status or self.reliability,
            "observed_at": self.observed_at or utc_now_iso(),
            "source": self.source,
            "reliability": self.reliability,
            "detail": self.detail,
        }


def unsupported_context(source: str | None = None) -> Observation:
    return Observation(
        kind="context",
        reliability="unsupported",
        source=source,
        observed_at=utc_now_iso(),
        detail="Host does not expose trustworthy context utilization",
    )


def unsupported_quota(source: str | None = None) -> Observation:
    return Observation(
        kind="quota",
        status="unsupported",
        reliability="unsupported",
        source=source,
        observed_at=utc_now_iso(),
        detail="Quota telemetry not available",
    )


def context_from_utilization(
    utilization: float,
    *,
    source: str,
    capacity: float | None = None,
    remaining: float | None = None,
    reliability: str = "valid",
) -> Observation:
    if utilization < 0 or utilization > 1:
        raise ValueError("utilization must be between 0 and 1")
    return Observation(
        kind="context",
        utilization=utilization,
        capacity=capacity,
        remaining=remaining,
        source=source,
        reliability=reliability,
        observed_at=utc_now_iso(),
    )


def context_from_token_counts(
    used_tokens: int,
    capacity_tokens: int,
    *,
    source: str,
) -> Observation:
    """Only when both used and capacity are known from a trusted host signal."""
    if used_tokens < 0 or capacity_tokens <= 0:
        raise ValueError("invalid token counts")
    util = min(used_tokens / capacity_tokens, 1.0)
    return Observation(
        kind="context",
        utilization=util,
        capacity=float(capacity_tokens),
        remaining=float(max(capacity_tokens - used_tokens, 0)),
        source=source,
        reliability="valid",
        observed_at=utc_now_iso(),
        detail=f"used={used_tokens} capacity={capacity_tokens}",
    )


def parse_claude_session_start(
    event: dict[str, Any], *, capacity_tokens: int | None
) -> Observation:
    """Claude SessionStart may include context_tokens on resume/fork — not continuous %."""
    tokens = event.get("context_tokens")
    if tokens is None:
        return unsupported_context(source="claude-code:SessionStart")
    if capacity_tokens is None:
        return Observation(
            kind="context",
            utilization=None,
            capacity=None,
            remaining=None,
            source="claude-code:SessionStart",
            reliability="unknown",
            observed_at=utc_now_iso(),
            detail=f"context_tokens={tokens} but capacity not configured",
        )
    try:
        return context_from_token_counts(
            int(tokens), int(capacity_tokens), source="claude-code:SessionStart"
        )
    except (TypeError, ValueError):
        return Observation(
            kind="context",
            reliability="unknown",
            source="claude-code:SessionStart",
            observed_at=utc_now_iso(),
            detail="unparseable context_tokens",
        )


def quota_from_rate_limit(*, source: str, detail: str | None = None) -> Observation:
    return Observation(
        kind="quota",
        status="rate_limited",
        reliability="rate_limited",
        source=source,
        observed_at=utc_now_iso(),
        detail=detail,
    )
