"""Safe, idempotent skill installation helpers (stdlib)."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST_NAME = ".relay-install-manifest.json"


@dataclass
class InstallResult:
    dest: Path
    written: list[str] = field(default_factory=list)
    skipped_same: list[str] = field(default_factory=list)
    backed_up: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "dest": str(self.dest),
            "written": self.written,
            "skipped_same": self.skipped_same,
            "backed_up": self.backed_up,
            "preserved": self.preserved,
            "errors": self.errors,
        }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _safe_relative_path(value: Any) -> str | None:
    """Return a normalized manifest path, rejecting absolute/traversal paths."""
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        return None
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
        return None
    normalized = candidate.as_posix()
    if normalized in ("", "."):
        return None
    return normalized


def _has_symlink_parent(dest: Path, rel: str) -> bool:
    """Do not follow symlinked directories while writing/removing owned paths."""
    current = dest
    parts = PurePosixPath(rel).parts
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def owned_file_map(skill_root: Path, adapter_skill: Path, *, include_cursor_rule: bool) -> dict[str, Path]:
    """Map relative install paths → source files owned by Relay."""
    mapping: dict[str, Path] = {
        "PORTABLE.md": skill_root / "SKILL.md",
        "SKILL.md": adapter_skill,
        "RELAY_ROOT": Path(""),  # generated
        "relay-env.sh": Path(""),  # generated
        "bin/relay-run": Path(""),  # generated
    }
    for sub in ("references", "templates"):
        src_dir = skill_root / sub
        if not src_dir.is_dir():
            continue
        for path in sorted(src_dir.rglob("*")):
            if path.is_file():
                mapping[f"{sub}/{_rel(path, src_dir)}"] = path
    if include_cursor_rule:
        rule = skill_root / "adapters" / "cursor" / "relay-continuity.mdc"
        if rule.is_file():
            mapping["relay-continuity.mdc"] = rule
    hooks = adapter_skill.parent / "hooks.json"
    if hooks.is_file():
        mapping["hooks.json"] = hooks
    return mapping


def load_manifest(dest: Path) -> dict[str, Any] | None:
    path = dest / MANIFEST_NAME
    # Never follow a user-created symlink for the ownership manifest.
    if path.is_symlink() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_manifest(dest: Path, files: list[str], meta: dict[str, Any]) -> None:
    path = dest / MANIFEST_NAME
    if path.is_symlink():
        raise OSError(f"refusing to write through symlinked manifest: {path}")
    payload = {
        "version": 1,
        "installed_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "files": sorted(set(files) | {MANIFEST_NAME}),
        **meta,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def install_adapter(
    *,
    dest: Path,
    skill_root: Path,
    repo_root: Path,
    adapter_skill: Path,
    include_cursor_rule: bool = False,
) -> InstallResult:
    result = InstallResult(dest=dest)
    if dest.is_symlink():
        result.errors.append(f"refusing symlinked install destination: {dest}")
        return result
    dest.mkdir(parents=True, exist_ok=True)
    mapping = owned_file_map(
        skill_root, adapter_skill, include_cursor_rule=include_cursor_rule
    )
    backup_root = dest / f".relay-backup-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    owned_rels: list[str] = []

    def ensure_backup(rel: str, existing: Path) -> None:
        if existing.is_symlink():
            raise OSError(f"refusing to back up symlink destination: {existing}")
        backup_root.mkdir(parents=True, exist_ok=True)
        target = backup_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(existing, target)
        result.backed_up.append(rel)

    # Generated helpers
    generated: dict[str, str] = {
        "RELAY_ROOT": str(repo_root.resolve()) + "\n",
        "relay-env.sh": (
            "# Generated by Relay install — source to put relay on PYTHONPATH\n"
            f'export PYTHONPATH="{repo_root.resolve()}${{PYTHONPATH:+:$PYTHONPATH}}"\n'
        ),
        "bin/relay-run": _relay_run_script(repo_root.resolve()),
    }

    for rel, src in mapping.items():
        safe_rel = _safe_relative_path(rel)
        if safe_rel is None:
            result.errors.append(f"unsafe install path: {rel!r}")
            continue
        owned_rels.append(safe_rel)
        out = dest / safe_rel
        if _has_symlink_parent(dest, safe_rel) or out.is_symlink():
            result.errors.append(f"refusing to write through symlink path: {safe_rel}")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        if safe_rel in generated:
            content = generated[safe_rel]
            if out.is_file():
                try:
                    if out.read_text(encoding="utf-8") == content:
                        result.skipped_same.append(safe_rel)
                        continue
                except (OSError, UnicodeError) as exc:
                    result.errors.append(f"{safe_rel}: cannot inspect existing file: {exc}")
                    continue
                manifest = load_manifest(dest)
                previously_owned = bool(manifest and safe_rel in (manifest.get("files") or []))
                if not previously_owned:
                    try:
                        ensure_backup(safe_rel, out)
                    except OSError as exc:
                        result.errors.append(f"{safe_rel}: backup failed: {exc}")
                        continue
            try:
                out.write_text(content, encoding="utf-8")
                if safe_rel == "bin/relay-run":
                    out.chmod(out.stat().st_mode | 0o111)
                result.written.append(safe_rel)
            except OSError as exc:
                result.errors.append(f"{safe_rel}: write failed: {exc}")
            continue

        if not src.is_file():
            result.errors.append(f"missing source: {src}")
            continue
        if out.is_file():
            try:
                if _sha256(out) == _sha256(src):
                    result.skipped_same.append(safe_rel)
                    continue
                manifest = load_manifest(dest)
                previously_owned = bool(manifest and safe_rel in (manifest.get("files") or []))
                if not previously_owned:
                    ensure_backup(safe_rel, out)
                shutil.copy2(src, out)
                result.written.append(safe_rel)
            except OSError as exc:
                result.errors.append(f"{safe_rel}: copy failed: {exc}")
            continue
        try:
            shutil.copy2(src, out)
            result.written.append(safe_rel)
        except OSError as exc:
            result.errors.append(f"{safe_rel}: copy failed: {exc}")

    # Preserve unrelated custom files
    manifest_prev = load_manifest(dest)
    prev_owned = set(manifest_prev.get("files") or []) if manifest_prev else set()
    for path in dest.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = _rel(path, dest)
        if rel.startswith(".relay-backup-") or rel == MANIFEST_NAME:
            continue
        if rel not in owned_rels and rel not in prev_owned:
            result.preserved.append(rel)

    try:
        save_manifest(
            dest,
            owned_rels,
            {
                "repo_root": str(repo_root.resolve()),
                "adapter": str(adapter_skill),
            },
        )
        result.written.append(MANIFEST_NAME)
    except OSError as exc:
        result.errors.append(f"manifest write failed: {exc}")
    return result


def uninstall_adapter(dest: Path) -> dict[str, Any]:
    """Remove only Relay-owned files listed in a validated install manifest."""
    manifest_path = dest / MANIFEST_NAME
    if manifest_path.is_symlink():
        return {
            "ok": False,
            "dest": str(dest),
            "error": "manifest is a symlink — refusing to follow it",
            "removed": [],
            "skipped": [],
        }
    manifest = load_manifest(dest)
    removed: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    if manifest is None:
        return {
            "ok": False,
            "dest": str(dest),
            "error": "no valid .relay-install-manifest.json — refusing to delete directory",
            "removed": [],
            "skipped": [],
        }

    files = manifest.get("files")
    if not isinstance(files, list):
        return {
            "ok": False,
            "dest": str(dest),
            "error": "invalid manifest files list — refusing to delete files",
            "removed": [],
            "skipped": [],
        }

    for entry in files:
        rel = _safe_relative_path(entry)
        if rel is None:
            errors.append(f"unsafe manifest path rejected: {entry!r}")
            continue
        path = dest / rel
        if _has_symlink_parent(dest, rel):
            errors.append(f"symlink parent rejected: {rel}")
            continue
        if not path.exists() and not path.is_symlink():
            skipped.append(rel)
            continue
        try:
            # Unlink a listed symlink itself; never follow it to its target.
            if path.is_symlink() or path.is_file():
                path.unlink()
                removed.append(rel)
            elif path.is_dir():
                skipped.append(f"{rel} (directory preserved)")
            else:
                skipped.append(rel)
        except OSError as exc:
            errors.append(f"{rel}: {exc}")

    # Remove only empty directories Relay commonly creates; never recurse-delete.
    for sub in ("references", "templates", "bin"):
        d = dest / sub
        if d.is_symlink():
            continue
        if d.is_dir():
            for p in sorted(d.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if p.is_symlink() or not p.is_dir():
                    continue
                try:
                    p.rmdir()
                except OSError:
                    pass
            try:
                d.rmdir()
            except OSError:
                pass
    try:
        if dest.is_dir() and not dest.is_symlink() and not any(dest.iterdir()):
            dest.rmdir()
    except OSError:
        pass

    return {
        "ok": not errors,
        "dest": str(dest),
        "removed": removed,
        "skipped": skipped,
        "errors": errors,
        "preserved_remaining": [
            str(p.relative_to(dest))
            for p in dest.rglob("*")
            if (p.is_file() or p.is_symlink()) and dest.exists()
        ]
        if dest.exists()
        else [],
    }


def _relay_run_script(repo_root: Path) -> str:
    # Portable wrapper: locates Relay via sibling RELAY_ROOT or embedded path.
    return f"""#!/usr/bin/env bash
# Relay hook/CLI wrapper — sets PYTHONPATH from RELAY_ROOT (no LLM).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$HERE/RELAY_ROOT" ]]; then
  ROOT="$(tr -d '\\r\\n' < "$HERE/RELAY_ROOT")"
else
  ROOT="{repo_root}"
fi
export PYTHONPATH="$ROOT${{PYTHONPATH:+:$PYTHONPATH}}"
exec python3 -m relay "$@"
"""
