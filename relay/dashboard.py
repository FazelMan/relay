"""Local, read-only Relay dashboard server (stdlib only)."""
from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .config import load_config
from .gitinfo import collect_git_state
from .paths import resolve_workspace
from .storage import handoff_path, latest_valid_checkpoint, list_tasks, history_dir, checkpoint_path


def serve_dashboard(workspace_arg: str = ".", host: str = "127.0.0.1", port: int = 8765) -> None:
    workspace = resolve_workspace(workspace_arg)
    config = load_config(workspace)
    ui_root = Path(__file__).resolve().parents[1] / "ui"
    if not (ui_root / "index.html").is_file():
        raise RuntimeError("Dashboard assets are missing; reinstall or update Relay.")

    class Handler(BaseHTTPRequestHandler):
        server_version = "RelayDashboard/1.0"

        def log_message(self, fmt: str, *args: object) -> None:
            # Avoid logging task content or query values.
            return

        def _json(self, data: object, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/overview":
                ids = list_tasks(workspace, config)
                tasks = []
                events = []
                for tid in ids:
                    cp, cp_path, err = latest_valid_checkpoint(workspace, config, tid)
                    if cp is None:
                        tasks.append({"id": tid, "valid": False, "error": err})
                        continue
                    task = cp.get("task") or {}
                    repo = cp.get("repository") or {}
                    tests = cp.get("verification") or cp.get("tests") or {}
                    handoff = handoff_path(workspace, config, tid)
                    histories = history_dir(workspace, config, tid)
                    tasks.append({
                        "id": tid,
                        "objective": task.get("objective") or tid,
                        "status": task.get("status") or "in_progress",
                        "updated_at": cp.get("updated_at"),
                        "valid": True,
                        "has_handoff": handoff.is_file() and not handoff.is_symlink(),
                        "checkpoint": str(cp_path) if cp_path else None,
                        "branch": repo.get("branch"),
                        "changed_paths": repo.get("changed_paths") or [],
                        "untracked_paths": repo.get("untracked_paths") or [],
                        "test_status": tests.get("status") if isinstance(tests, dict) else None,
                        "history_count": len(list(histories.glob("checkpoint-*.json"))) if histories.is_dir() else 0,
                        "next_steps": task.get("next_steps") or cp.get("next_steps") or [],
                        "decisions": task.get("decisions") or cp.get("decisions") or [],
                    })
                    events.append({"task_id": tid, "time": cp.get("updated_at"), "type": "checkpoint", "title": "Checkpoint updated", "detail": str(cp_path) if cp_path else ""})
                    if handoff.is_file() and not handoff.is_symlink():
                        events.append({"task_id": tid, "time": handoff.stat().st_mtime, "type": "handoff", "title": "Handoff available", "detail": handoff.name})
                events.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
                self._json({"ok": True, "workspace": str(workspace), "version": "1.0", "git": collect_git_state(workspace), "tasks": tasks, "events": events[:40]})
                return
            if parsed.path == "/api/task":
                from urllib.parse import parse_qs
                tid = (parse_qs(parsed.query).get("id") or [""])[0]
                if not tid or any(x in tid for x in ("/", "\\\\", "..")):
                    self._json({"ok": False, "error": "A valid task id is required."}, 400)
                    return
                cp, path, err = latest_valid_checkpoint(workspace, config, tid)
                if cp is None:
                    self._json({"ok": False, "error": err or "Task not found."}, 404)
                    return
                hp = handoff_path(workspace, config, tid)
                handoff = hp.read_text(encoding="utf-8") if hp.is_file() and not hp.is_symlink() else ""
                hist = history_dir(workspace, config, tid)
                self._json({"ok": True, "task_id": tid, "checkpoint": cp, "handoff": handoff, "history": len(list(hist.glob("checkpoint-*.json"))) if hist.is_dir() else 0})
                return
            rel = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
            target = (ui_root / rel).resolve()
            try:
                target.relative_to(ui_root.resolve())
            except ValueError:
                self.send_error(404)
                return
            if not target.is_file() or target.is_symlink():
                self.send_error(404)
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(body)

    print(f"Relay Dashboard: http://{host}:{port}")
    print(f"Workspace: {workspace}")
    print("Read-only local dashboard. Press Ctrl+C to stop.")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
