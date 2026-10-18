"""Conservative Git inspection. Never mutates the repository."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _run(cwd: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return 1, ""
    out = (proc.stdout or "").strip()
    return proc.returncode, out


def repo_root(workspace: Path) -> Path | None:
    code, out = _run(workspace, "rev-parse", "--show-toplevel")
    if code != 0 or not out:
        return None
    return Path(out)


def collect_git_state(workspace: Path, *, path_limit: int = 200) -> dict[str, Any]:
    root = repo_root(workspace)
    if root is None:
        return {
            "root": str(workspace.resolve()),
            "identity": "",
            "branch": None,
            "head": None,
            "working_tree": "unknown",
            "changed_paths": [],
            "staged_paths": [],
            "unstaged_paths": [],
            "untracked_paths": [],
            "git_available": False,
        }

    _, branch = _run(root, "rev-parse", "--abbrev-ref", "HEAD")
    _, head = _run(root, "rev-parse", "HEAD")
    _, remote = _run(root, "config", "--get", "remote.origin.url")

    _, status = _run(root, "status", "--porcelain")
    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []
    changed: list[str] = []
    for line in status.splitlines():
        if len(line) < 3:
            continue
        x, y, path = line[0], line[1], line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[-1]
        changed.append(path)
        if x == "?" and y == "?":
            untracked.append(path)
        else:
            if x != " " and x != "?":
                staged.append(path)
            if y != " ":
                unstaged.append(path)

    def trim(paths: list[str]) -> list[str]:
        return paths[:path_limit]

    dirty = bool(changed)
    return {
        "root": str(root),
        "identity": remote or root.name,
        "branch": branch or None,
        "head": head or None,
        "working_tree": "dirty" if dirty else "clean",
        "changed_paths": trim(changed),
        "staged_paths": trim(staged),
        "unstaged_paths": trim(unstaged),
        "untracked_paths": trim(untracked),
        "git_available": True,
    }
