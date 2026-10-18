"""Configuration loading (TOML via stdlib tomllib when available)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11
    tomllib = None  # type: ignore


@dataclass
class Thresholds:
    early: float = 0.65
    elevated: float = 0.80
    critical: float = 0.90


@dataclass
class Config:
    storage_dir: str = "plans/handoffs"
    history_limit: int = 5
    warning_cooldown_seconds: int = 300
    thresholds: Thresholds = field(default_factory=Thresholds)
    auto_handoff_on_critical: bool = True
    mechanical_on_precompact: bool = True
    mechanical_on_stop: bool = False
    semantic_requires_agent: bool = True
    allow_paths_outside_workspace: bool = False
    context_capacity_tokens: int | None = None  # optional host-configured capacity
    log_level: str = "info"
    handoff_mode: str = "suggest"  # manual | suggest | prepare
    handoff_optimize_for: str = "balanced"  # cost | time | quality | balanced
    handoff_detail: str = "standard"  # compact | standard | full

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


DEFAULTS = Config()


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def config_from_mapping(data: dict[str, Any]) -> Config:
    thr = data.get("thresholds") or {}
    thresholds = Thresholds(
        early=float(thr.get("early", DEFAULTS.thresholds.early)),
        elevated=float(thr.get("elevated", DEFAULTS.thresholds.elevated)),
        critical=float(thr.get("critical", DEFAULTS.thresholds.critical)),
    )
    if not (0 < thresholds.early <= thresholds.elevated <= thresholds.critical <= 1):
        raise ValueError(
            "thresholds must satisfy 0 < early <= elevated <= critical <= 1"
        )
    capacity = data.get("context_capacity_tokens", DEFAULTS.context_capacity_tokens)
    if capacity is not None:
        capacity = int(capacity)
        if capacity <= 0:
            raise ValueError("context_capacity_tokens must be positive")
    handoff_mode = str(data.get("handoff_mode", DEFAULTS.handoff_mode))
    if handoff_mode not in {"manual", "suggest", "prepare"}:
        raise ValueError("handoff_mode must be manual, suggest, or prepare")
    optimize_for = str(data.get("handoff_optimize_for", DEFAULTS.handoff_optimize_for))
    if optimize_for not in {"cost", "time", "quality", "balanced"}:
        raise ValueError("handoff_optimize_for must be cost, time, quality, or balanced")
    handoff_detail = str(data.get("handoff_detail", DEFAULTS.handoff_detail))
    if handoff_detail not in {"compact", "standard", "full"}:
        raise ValueError("handoff_detail must be compact, standard, or full")
    return Config(
        storage_dir=str(data.get("storage_dir", DEFAULTS.storage_dir)),
        history_limit=int(data.get("history_limit", DEFAULTS.history_limit)),
        warning_cooldown_seconds=int(
            data.get("warning_cooldown_seconds", DEFAULTS.warning_cooldown_seconds)
        ),
        thresholds=thresholds,
        auto_handoff_on_critical=bool(
            data.get("auto_handoff_on_critical", DEFAULTS.auto_handoff_on_critical)
        ),
        mechanical_on_precompact=bool(
            data.get("mechanical_on_precompact", DEFAULTS.mechanical_on_precompact)
        ),
        mechanical_on_stop=bool(
            data.get("mechanical_on_stop", DEFAULTS.mechanical_on_stop)
        ),
        semantic_requires_agent=bool(
            data.get("semantic_requires_agent", DEFAULTS.semantic_requires_agent)
        ),
        allow_paths_outside_workspace=bool(
            data.get(
                "allow_paths_outside_workspace", DEFAULTS.allow_paths_outside_workspace
            )
        ),
        context_capacity_tokens=capacity,
        log_level=str(data.get("log_level", DEFAULTS.log_level)),
        handoff_mode=handoff_mode,
        handoff_optimize_for=optimize_for,
        handoff_detail=handoff_detail,
    )


def find_config_path(workspace: Path) -> Path | None:
    for name in ("relay.toml", ".relay.toml", "relay.json"):
        candidate = workspace / name
        if candidate.is_file():
            return candidate
    return None


def load_config(workspace: Path) -> Config:
    path = find_config_path(workspace)
    if path is None:
        return Config()
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
    else:
        if tomllib is None:
            raise RuntimeError("TOML config requires Python 3.11+ (tomllib)")
        data = tomllib.loads(text)
    if not isinstance(data, dict):
        raise ValueError("config root must be a table/object")
    # Support [relay] nesting
    if "relay" in data and isinstance(data["relay"], dict):
        data = data["relay"]
    return config_from_mapping(data)


EXAMPLE_TOML = """\
# Relay configuration (optional). Place at repository root as relay.toml.

storage_dir = "plans/handoffs"
history_limit = 5
warning_cooldown_seconds = 300
auto_handoff_on_critical = true
mechanical_on_precompact = true
mechanical_on_stop = false
handoff_mode = "suggest" # manual | suggest | prepare
handoff_optimize_for = "balanced" # cost | time | quality | balanced
handoff_detail = "standard" # compact | standard | full
# Optional: used only when a host reports absolute context_tokens.
# context_capacity_tokens = 200000

[thresholds]
early = 0.65
elevated = 0.80
critical = 0.90
"""
