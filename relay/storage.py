"""Atomic checkpoint persistence and retention."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .config import Config
from .schema import empty_checkpoint, utc_now_iso, validate_checkpoint
from .secrets import scrub

TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class StorageError(Exception):
    pass


def sanitize_task_id(task_id: str) -> str:
    raw = task_id.strip()
    if not raw or ".." in raw or "/" in raw or "\\" in raw:
        raise StorageError(f"invalid task_id: {task_id!r}")
    slug = raw.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9_-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-_")
    if not slug or not TASK_ID_RE.match(slug):
        raise StorageError(f"invalid task_id: {task_id!r}")
    return slug


def storage_root(workspace: Path, config: Config) -> Path:
    root = (workspace / config.storage_dir).resolve()
    workspace_resolved = workspace.resolve()
    if not config.allow_paths_outside_workspace:
        try:
            root.relative_to(workspace_resolved)
        except ValueError as exc:
            raise StorageError("storage_dir escapes workspace") from exc
    return root


def task_dir(workspace: Path, config: Config, task_id: str) -> Path:
    tid = sanitize_task_id(task_id)
    return storage_root(workspace, config) / tid


def checkpoint_path(workspace: Path, config: Config, task_id: str) -> Path:
    return task_dir(workspace, config, task_id) / "checkpoint.json"


def handoff_path(workspace: Path, config: Config, task_id: str) -> Path:
    return task_dir(workspace, config, task_id) / "HANDOFF.md"


def history_dir(workspace: Path, config: Config, task_id: str) -> Path:
    return task_dir(workspace, config, task_id) / "history"


def ensure_within(base: Path, target: Path) -> Path:
    resolved = target.resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise StorageError(f"path escapes authorized storage: {target}") from exc
    return resolved


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".checkpoint-", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".handoff-", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            if not text.endswith("\n"):
                fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def load_checkpoint(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except FileNotFoundError as exc:
        raise StorageError(f"checkpoint not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StorageError(f"corrupted checkpoint JSON: {path}: {exc}") from exc
    errors = validate_checkpoint(data)
    if errors:
        raise StorageError(f"invalid checkpoint: {'; '.join(errors)}")
    return data


def try_load_checkpoint(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return load_checkpoint(path), None
    except StorageError as exc:
        return None, str(exc)


def save_checkpoint(
    workspace: Path,
    config: Config,
    checkpoint: dict[str, Any],
    *,
    retain_history: bool = True,
) -> Path:
    task_id = sanitize_task_id(str(checkpoint.get("task_id", "")))
    checkpoint = scrub(checkpoint)
    checkpoint["task_id"] = task_id
    checkpoint["updated_at"] = checkpoint.get("updated_at") or utc_now_iso()
    errors = validate_checkpoint(checkpoint)
    if errors:
        raise StorageError(f"refusing to save invalid checkpoint: {'; '.join(errors)}")

    path = checkpoint_path(workspace, config, task_id)
    ensure_within(storage_root(workspace, config), path)

    # Preserve last known-good into history before replace.
    if retain_history and path.is_file():
        prev, err = try_load_checkpoint(path)
        if prev is not None:
            _archive(workspace, config, task_id, prev)
        elif err:
            # Keep corrupt file for diagnosis under history.
            hist = history_dir(workspace, config, task_id)
            hist.mkdir(parents=True, exist_ok=True)
            corrupt_dest = hist / f"corrupt-{utc_now_iso().replace(':', '')}.json"
            try:
                path.replace(corrupt_dest)
            except OSError:
                pass

    atomic_write_json(path, checkpoint)
    if retain_history:
        _apply_retention(workspace, config, task_id)
    return path


def _archive(workspace: Path, config: Config, task_id: str, data: dict[str, Any]) -> None:
    hist = history_dir(workspace, config, task_id)
    hist.mkdir(parents=True, exist_ok=True)
    stamp = str(data.get("updated_at") or utc_now_iso()).replace(":", "").replace("+00:00", "Z")
    cid = str(data.get("checkpoint_id", "unknown"))[:8]
    dest = hist / f"checkpoint-{stamp}-{cid}.json"
    atomic_write_json(dest, data)


def _apply_retention(workspace: Path, config: Config, task_id: str) -> None:
    hist = history_dir(workspace, config, task_id)
    if not hist.is_dir():
        return
    files = sorted(
        [p for p in hist.glob("checkpoint-*.json") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in files[config.history_limit :]:
        try:
            old.unlink()
        except OSError:
            pass


def list_tasks(workspace: Path, config: Config) -> list[str]:
    root = storage_root(workspace, config)
    if not root.is_dir():
        return []
    tasks = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "checkpoint.json").is_file():
            tasks.append(child.name)
    # Legacy flat HANDOFF_*.md discovery (read-only awareness).
    return tasks


def list_legacy_handoffs(workspace: Path, config: Config) -> list[Path]:
    root = storage_root(workspace, config)
    if not root.is_dir():
        return []
    return sorted(root.glob("HANDOFF_*.md"))


def latest_valid_checkpoint(
    workspace: Path, config: Config, task_id: str
) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    """Return current valid checkpoint, or fall back to newest valid history entry."""
    path = checkpoint_path(workspace, config, task_id)
    data, err = try_load_checkpoint(path)
    if data is not None:
        return data, path, None

    hist = history_dir(workspace, config, task_id)
    if hist.is_dir():
        candidates = sorted(
            hist.glob("checkpoint-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for candidate in candidates:
            hist_data, hist_err = try_load_checkpoint(candidate)
            if hist_data is not None:
                return hist_data, candidate, err or hist_err

    return None, None, err or "no valid checkpoint"


def create_mechanical_checkpoint(
    workspace: Path,
    config: Config,
    task_id: str,
    *,
    git_state: dict[str, Any],
    existing: dict[str, Any] | None = None,
    host: str | None = None,
    trigger: str = "mechanical",
) -> dict[str, Any]:
    if existing is None:
        cp = empty_checkpoint(
            task_id=task_id,
            workspace_path=str(workspace.resolve()),
            source=trigger,
        )
    else:
        from .schema import merge_checkpoint

        cp = merge_checkpoint(existing, {})
        cp["provenance"] = dict(cp.get("provenance") or {})
        cp["provenance"]["kind"] = trigger

    cp["repository"] = {**(cp.get("repository") or {}), **git_state}
    if host:
        cp.setdefault("provenance", {})["host"] = host
    cp["updated_at"] = utc_now_iso()
    return cp
