"""Resume preparation: reconcile checkpoint against live workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Config
from .gitinfo import collect_git_state
from .storage import (
    checkpoint_path,
    handoff_path,
    latest_valid_checkpoint,
    list_tasks,
    sanitize_task_id,
)


@dataclass
class ResumeReport:
    task_id: str
    checkpoint_path: str | None
    handoff_path: str | None
    used_fallback_history: bool
    valid: bool
    discrepancies: list[str] = field(default_factory=list)
    missing_paths: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    continuation_summary: str = ""
    checkpoint: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "checkpoint_path": self.checkpoint_path,
            "handoff_path": self.handoff_path,
            "used_fallback_history": self.used_fallback_history,
            "valid": self.valid,
            "discrepancies": self.discrepancies,
            "missing_paths": self.missing_paths,
            "next_steps": self.next_steps,
            "continuation_summary": self.continuation_summary,
        }


def discover_task_id(
    workspace: Path, config: Config, requested: str | None
) -> tuple[str | None, list[str]]:
    tasks = list_tasks(workspace, config)
    if requested:
        tid = sanitize_task_id(requested)
        if tid in tasks:
            return tid, tasks
        # Allow resume when only history/corrupt present
        if checkpoint_path(workspace, config, tid).parent.is_dir():
            return tid, tasks
        return None, tasks
    if len(tasks) == 1:
        return tasks[0], tasks
    return None, tasks


def prepare_resume(
    workspace: Path,
    config: Config,
    task_id: str | None = None,
) -> ResumeReport:
    tid, candidates = discover_task_id(workspace, config, task_id)
    if tid is None:
        msg = (
            "multiple tasks found; specify --task"
            if len(candidates) > 1
            else "no checkpoint tasks found"
        )
        return ResumeReport(
            task_id=task_id or "",
            checkpoint_path=None,
            handoff_path=None,
            used_fallback_history=False,
            valid=False,
            discrepancies=[msg, f"candidates: {', '.join(candidates) or '(none)'}"],
            continuation_summary=msg,
        )

    data, path, load_err = latest_valid_checkpoint(workspace, config, tid)
    primary = checkpoint_path(workspace, config, tid)
    used_fallback = bool(path and path != primary and data is not None)
    hp = handoff_path(workspace, config, tid)

    if data is None:
        return ResumeReport(
            task_id=tid,
            checkpoint_path=str(primary),
            handoff_path=str(hp) if hp.is_file() else None,
            used_fallback_history=False,
            valid=False,
            discrepancies=[load_err or "no valid checkpoint"],
            continuation_summary="Cannot resume: no valid checkpoint. Inspect corrupt files under history/.",
        )

    live = collect_git_state(workspace)
    recorded = data.get("repository") or {}
    discrepancies: list[str] = []
    if load_err and used_fallback:
        discrepancies.append(f"current checkpoint invalid ({load_err}); using history fallback")

    if recorded.get("branch") and live.get("branch") and recorded["branch"] != live["branch"]:
        discrepancies.append(
            f"branch changed: recorded {recorded['branch']} vs actual {live['branch']}"
        )
    if recorded.get("head") and live.get("head") and recorded["head"] != live["head"]:
        discrepancies.append(
            f"HEAD changed: recorded {recorded['head'][:12]} vs actual {live['head'][:12]}"
        )
    if recorded.get("working_tree") and live.get("working_tree"):
        if recorded["working_tree"] != live["working_tree"]:
            discrepancies.append(
                f"working tree: recorded {recorded['working_tree']} vs actual {live['working_tree']}"
            )

    missing: list[str] = []
    task = data.get("task") or {}
    for path_str in task.get("relevant_paths") or []:
        p = Path(path_str)
        if not p.is_absolute():
            p = workspace / p
        if not p.exists():
            missing.append(str(path_str))
    files = task.get("files") or {}
    for kind in ("created", "modified"):
        for path_str in files.get(kind) or []:
            p = workspace / path_str if not Path(path_str).is_absolute() else Path(path_str)
            if not p.exists():
                missing.append(str(path_str))
    if missing:
        discrepancies.append(f"missing paths: {', '.join(missing)}")

    next_steps = list(task.get("next_steps") or [])
    status = task.get("status")
    if status == "complete":
        discrepancies.append(
            "checkpoint status is complete — verify before treating work as finished"
        )

    summary_parts = [
        f"Task `{tid}` objective: {task.get('objective') or '(unset)'}",
        f"Recorded status: {status}",
        f"Discrepancies: {len(discrepancies)}",
        f"Next: {next_steps[0] if next_steps else '(none recorded — ask user)'}",
    ]
    if used_fallback:
        summary_parts.append("Loaded from history fallback; inspect corrupt current if present.")

    return ResumeReport(
        task_id=tid,
        checkpoint_path=str(path) if path else None,
        handoff_path=str(hp) if hp.is_file() else None,
        used_fallback_history=used_fallback,
        valid=True,
        discrepancies=discrepancies,
        missing_paths=missing,
        next_steps=next_steps,
        continuation_summary=" | ".join(summary_parts),
        checkpoint=data,
    )
