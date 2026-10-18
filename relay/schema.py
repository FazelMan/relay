"""Checkpoint schema validation (stdlib only)."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = "1.0.0"

REQUIRED_TOP = (
    "schema_version",
    "checkpoint_id",
    "task_id",
    "updated_at",
    "task",
    "repository",
    "provenance",
)

TASK_STATUSES = frozenset({"in_progress", "blocked", "complete", "unknown"})
RISK_STATES = frozenset(
    {
        "healthy",
        "early",
        "elevated",
        "critical",
        "handoff_ready",
        "interrupted",
        "resuming",
    }
)
METRIC_RELIABILITY = frozenset(
    {"valid", "stale", "historical", "rate_limited", "unavailable", "unsupported", "unknown"}
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def empty_checkpoint(
    *,
    task_id: str,
    objective: str = "",
    workspace_path: str = "",
    source: str = "mechanical",
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": str(uuid4()),
        "task_id": task_id,
        "updated_at": utc_now_iso(),
        "task": {
            "objective": objective or "",
            "phase": "",
            "status": "in_progress",
            "completed": [],
            "in_progress": [],
            "decisions": [],
            "next_steps": [],
            "blockers": [],
            "unresolved": [],
            "relevant_paths": [],
            "files": {"created": [], "modified": [], "deleted": []},
            "tests": {"executed": [], "not_executed": []},
            "project_instructions": [],
        },
        "repository": {
            "root": workspace_path or "",
            "identity": "",
            "branch": None,
            "head": None,
            "working_tree": "unknown",
            "changed_paths": [],
            "staged_paths": [],
            "unstaged_paths": [],
            "untracked_paths": [],
            "git_available": False,
        },
        "context": {
            "utilization": None,
            "capacity": None,
            "remaining": None,
            "observed_at": None,
            "source": None,
            "reliability": "unsupported",
        },
        "quota": {
            "status": "unsupported",
            "observed_at": None,
            "source": None,
            "reliability": "unsupported",
            "detail": None,
        },
        "risk": {
            "state": "healthy",
            "context_state": "healthy",
            "quota_state": "healthy",
            "reason": "",
        },
        "provenance": {
            "kind": source,  # mechanical | semantic | handoff | merge
            "host": None,
            "tool": "relay",
            "notes": "",
        },
        "integrity": {
            "valid": True,
            "errors": [],
        },
    }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def validate_checkpoint(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["checkpoint must be a JSON object"]

    for key in REQUIRED_TOP:
        if key not in data:
            errors.append(f"missing required field: {key}")

    if data.get("schema_version") not in (SCHEMA_VERSION, "1.0"):
        # Accept minor alias; reject unknown major.
        ver = str(data.get("schema_version", ""))
        if not ver.startswith("1."):
            errors.append(f"unsupported schema_version: {data.get('schema_version')!r}")

    task = data.get("task")
    if not isinstance(task, dict):
        errors.append("task must be an object")
    else:
        status = task.get("status", "unknown")
        if status not in TASK_STATUSES:
            errors.append(f"invalid task.status: {status!r}")
        for list_key in (
            "completed",
            "in_progress",
            "decisions",
            "next_steps",
            "blockers",
            "unresolved",
            "relevant_paths",
            "project_instructions",
        ):
            if list_key in task and not isinstance(task[list_key], list):
                errors.append(f"task.{list_key} must be a list")

    repo = data.get("repository")
    if not isinstance(repo, dict):
        errors.append("repository must be an object")

    risk = data.get("risk")
    if isinstance(risk, dict):
        state = risk.get("state")
        if state is not None and state not in RISK_STATES:
            errors.append(f"invalid risk.state: {state!r}")

    for section in ("context", "quota"):
        block = data.get(section)
        if isinstance(block, dict):
            rel = block.get("reliability")
            if rel is not None and rel not in METRIC_RELIABILITY:
                errors.append(f"invalid {section}.reliability: {rel!r}")

    return errors


def merge_checkpoint(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Shallow-deep merge for task/repo/context updates. Preserves unknown keys."""
    out = deepcopy(base)
    for key, value in patch.items():
        if key in ("task", "repository", "context", "quota", "risk", "provenance", "integrity") and isinstance(
            value, dict
        ):
            current = out.get(key)
            if not isinstance(current, dict):
                current = {}
            merged = dict(current)
            for k, v in value.items():
                if k == "files" and isinstance(v, dict) and isinstance(merged.get("files"), dict):
                    files = dict(merged["files"])
                    for fk, fv in v.items():
                        files[fk] = _as_list(fv)
                    merged["files"] = files
                elif k == "tests" and isinstance(v, dict) and isinstance(merged.get("tests"), dict):
                    tests = dict(merged["tests"])
                    for tk, tv in v.items():
                        tests[tk] = _as_list(tv)
                    merged["tests"] = tests
                else:
                    merged[k] = v
            out[key] = merged
        else:
            out[key] = value
    out["updated_at"] = utc_now_iso()
    if "checkpoint_id" not in patch:
        out["checkpoint_id"] = str(uuid4())
    return out
