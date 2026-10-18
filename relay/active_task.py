"""Active-task identity resolution for hooks and CLI.

Resolution order (highest first):
1. Explicit --task / requested id
2. RELAY_TASK environment variable
3. Project-local active-task registry (.relay/active-task.json)
4. Exactly one existing task directory → use it (reported as inferred)
5. Safe mechanical fallback: unscoped-mechanical (never treated as semantic task)

Hooks must not silently write unrelated work into a semantic task named "default".
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .schema import utc_now_iso
from .storage import StorageError, list_tasks, sanitize_task_id

# Mechanical-only bucket when no active semantic task is known.
MECHANICAL_FALLBACK_ID = "unscoped-mechanical"

Source = Literal[
    "explicit",
    "env",
    "registry",
    "single_task",
    "mechanical_fallback",
]


@dataclass
class TaskResolution:
    task_id: str
    source: Source
    is_mechanical_fallback: bool
    message: str
    candidates: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "source": self.source,
            "is_mechanical_fallback": self.is_mechanical_fallback,
            "message": self.message,
            "candidates": self.candidates,
        }


def active_task_path(workspace: Path) -> Path:
    return workspace / ".relay" / "active-task.json"


def read_active_task(workspace: Path) -> str | None:
    path = active_task_path(workspace)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("task_id")
    if not raw:
        return None
    try:
        return sanitize_task_id(str(raw))
    except StorageError:
        return None


def set_active_task(workspace: Path, task_id: str, *, set_by: str = "cli") -> Path:
    tid = sanitize_task_id(task_id)
    if tid == MECHANICAL_FALLBACK_ID:
        raise StorageError(
            f"refusing to register mechanical fallback id as active semantic task: {tid}"
        )
    path = active_task_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": tid,
        "updated_at": utc_now_iso(),
        "set_by": set_by,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def clear_active_task(workspace: Path) -> bool:
    path = active_task_path(workspace)
    if path.is_file():
        path.unlink()
        return True
    return False


def resolve_task_id(
    workspace: Path,
    config: Any,
    requested: str | None = None,
    *,
    allow_mechanical_fallback: bool = True,
) -> TaskResolution:
    """Resolve which task id to use. Never silently maps unknown work to 'default'."""
    candidates = list_tasks(workspace, config)

    if requested and requested.strip():
        # Explicit empty / sentinel for "resolve without forcing default"
        if requested.strip() in ("-", "auto", "@active"):
            pass
        else:
            tid = sanitize_task_id(requested)
            mechanical = tid == MECHANICAL_FALLBACK_ID
            return TaskResolution(
                task_id=tid,
                source="explicit",
                is_mechanical_fallback=mechanical,
                message=(
                    f"using explicit mechanical fallback {tid}"
                    if mechanical
                    else f"using explicit task id {tid}"
                ),
                candidates=candidates,
            )

    env_raw = os.environ.get("RELAY_TASK", "").strip()
    if env_raw:
        tid = sanitize_task_id(env_raw)
        mechanical = tid == MECHANICAL_FALLBACK_ID
        return TaskResolution(
            task_id=tid,
            source="env",
            is_mechanical_fallback=mechanical,
            message=f"using RELAY_TASK={tid}",
            candidates=candidates,
        )

    registered = read_active_task(workspace)
    if registered and registered != MECHANICAL_FALLBACK_ID:
        return TaskResolution(
            task_id=registered,
            source="registry",
            is_mechanical_fallback=False,
            message=f"using active-task registry ({registered})",
            candidates=candidates,
        )

    semantic_candidates = [c for c in candidates if c != MECHANICAL_FALLBACK_ID]
    if len(semantic_candidates) == 1:
        only = semantic_candidates[0]
        return TaskResolution(
            task_id=only,
            source="single_task",
            is_mechanical_fallback=False,
            message=f"inferred sole semantic task directory {only}",
            candidates=candidates,
        )

    if allow_mechanical_fallback:
        msg = (
            "no active task registered; using mechanical fallback "
            f"'{MECHANICAL_FALLBACK_ID}' (will not merge unrelated semantic state). "
            "Set active task: python3 -m relay task set <id>"
        )
        if len(candidates) > 1:
            msg = (
                f"multiple tasks {candidates} and no active registry; "
                f"using mechanical fallback '{MECHANICAL_FALLBACK_ID}'. "
                "Set active task or pass --task."
            )
        return TaskResolution(
            task_id=MECHANICAL_FALLBACK_ID,
            source="mechanical_fallback",
            is_mechanical_fallback=True,
            message=msg,
            candidates=candidates,
        )

    raise StorageError(
        "task identity unknown: pass --task, set RELAY_TASK, or "
        "`python3 -m relay task set <id>`"
    )
