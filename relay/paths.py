"""Path safety helpers."""

from __future__ import annotations

from pathlib import Path

from .storage import StorageError


def resolve_workspace(path: str | Path | None) -> Path:
    if path is None:
        return Path.cwd().resolve()
    return Path(path).expanduser().resolve()


def safe_join(base: Path, *parts: str) -> Path:
    candidate = base.joinpath(*parts).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise StorageError("path traversal blocked") from exc
    return candidate
