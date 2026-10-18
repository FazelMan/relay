"""Append-only, bounded handoff change-event snapshots.

These records describe observed deltas; they never modify project files.
Git status is observational and cannot prove content-level changes for files
that were never tracked by Git.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config
from .gitinfo import collect_git_state
from .storage import ensure_within, storage_root, task_dir


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _task_state(checkpoint: dict[str, Any]) -> dict[str, Any]:
    task = checkpoint.get("task") or {}
    keys = (
        "objective", "phase", "status", "completed", "in_progress",
        "decisions", "next_steps", "blockers", "unresolved", "relevant_paths",
        "files", "tests", "project_instructions",
    )
    return {key: task.get(key) for key in keys if key in task}


def _path_status(git_state: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in git_state.get("changed_paths") or []:
        # porcelain status can contain rename arrows; gitinfo already resolves
        # the destination path. Status is intentionally conservative.
        result[str(path)] = "changed"
    for path in git_state.get("untracked_paths") or []:
        result[str(path)] = "created_or_untracked"
    return result


def record_change_event(
    workspace: Path,
    config: Config,
    task_id: str,
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> Path | None:
    """Write a deduplicated observation of Git/task-state changes."""
    live = collect_git_state(workspace)
    old_repo = (previous or {}).get("repository") or {}
    old_paths = set(old_repo.get("changed_paths") or [])
    new_status = _path_status(live)
    new_paths = set(new_status)
    # These are transitions between checkpoint observations, not a claim that
    # every file change since the last checkpoint has been reconstructed.
    git_delta = {
        "currently_changed": sorted(new_paths),
        "no_longer_reported_changed": sorted(old_paths - new_paths),
        "newly_reported_changed": sorted(new_paths - old_paths),
        "untracked": sorted(live.get("untracked_paths") or []),
        "staged": sorted(live.get("staged_paths") or []),
        "unstaged": sorted(live.get("unstaged_paths") or []),
        "working_tree": live.get("working_tree", "unknown"),
        "head": live.get("head"),
        "branch": live.get("branch"),
        "git_available": live.get("git_available", False),
    }
    old_task = _task_state(previous or {})
    new_task = _task_state(current)
    task_changed = _canonical(old_task) != _canonical(new_task)
    git_changed = _canonical({
        "changed_paths": sorted(old_paths),
        "head": old_repo.get("head"),
        "branch": old_repo.get("branch"),
        "working_tree": old_repo.get("working_tree"),
    }) != _canonical({
        "changed_paths": sorted(new_paths),
        "head": live.get("head"),
        "branch": live.get("branch"),
        "working_tree": live.get("working_tree"),
    })
    if previous is not None and not task_changed and not git_changed:
        return None

    event = {
        "event_schema_version": "1.0",
        "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "task_id": task_id,
        "from_checkpoint_id": (previous or {}).get("checkpoint_id"),
        "to_checkpoint_id": current.get("checkpoint_id"),
        "kind": "initial_snapshot" if previous is None else "checkpoint_delta",
        "git": git_delta,
        "task_state": {
            "changed": task_changed,
            "before": old_task if task_changed else None,
            "after": new_task if task_changed else None,
        },
        "limitations": [
            "Git path changes are observations at checkpoint time, not a complete file-content diff.",
            "A path no longer reported changed is not proof it was deleted; inspect Git history/status.",
            "No project files are changed by this event recorder.",
        ],
    }
    digest = hashlib.sha256(_canonical(event).encode("utf-8")).hexdigest()[:16]
    event["event_id"] = digest
    folder = task_dir(workspace, config, task_id) / "changes"
    path = folder / f"change-{event['observed_at'].replace(':', '').replace('-', '')}-{digest}.json"
    ensure_within(storage_root(workspace, config), path)
    folder.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(event, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    # Keep newest 100 event files to avoid unbounded growth.
    events = sorted(folder.glob("change-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for old in events[100:]:
        old.unlink(missing_ok=True)
    return path
