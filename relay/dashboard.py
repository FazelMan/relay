"""Local, read-only Relay dashboard server (stdlib only)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import webbrowser
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .config import load_config
from .gitinfo import collect_git_state
from .paths import resolve_workspace
from .storage import handoff_path, latest_valid_checkpoint, list_tasks, history_dir, checkpoint_path, save_checkpoint, ensure_within, storage_root
from .active_task import read_active_task, clear_active_task


def serve_dashboard(workspace_arg: str = ".", host: str = "127.0.0.1", port: int = 8765, *, open_browser: bool = True) -> None:
    workspace = resolve_workspace(workspace_arg)
    config = load_config(workspace)
    # Reuse a live dashboard only when its reported workspace exactly matches.
    if host in ("127.0.0.1", "localhost"):
        for candidate in range(port, min(port + 32, 65536)):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{candidate}/api/overview", timeout=0.2) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if payload.get("workspace") == str(workspace):
                    url = f"http://127.0.0.1:{candidate}/"
                    print(f"Relay Dashboard already running: {url}")
                    if open_browser: webbrowser.open(url)
                    return
            except (OSError, ValueError, urllib.error.URLError):
                pass
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

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/handoff/action":
                self._json({"ok": False, "error": "Not found."}, 404)
                return
            origin = self.headers.get("Origin", "")
            expected = f"http://{self.headers.get('Host', '')}"
            if origin and origin != expected:
                self._json({"ok": False, "error": "Cross-origin request rejected."}, 403)
                return
            if self.client_address[0] not in ("127.0.0.1", "::1"):
                self._json({"ok": False, "error": "Local requests only."}, 403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 4096: raise ValueError("Invalid request size.")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                action, tid = payload.get("action"), str(payload.get("task_id", ""))
                if action not in ("done", "delete") or not tid or "/" in tid or chr(92) in tid or ".." in tid:
                    raise ValueError("Invalid action or task id.")
                hp = handoff_path(workspace, config, tid)
                if hp.is_symlink() or hp.parent.is_symlink():
                    self._json({"ok": False, "error": "Refusing to operate through a symlink."}, 400); return
                ensure_within(storage_root(workspace, config), hp)
                if not hp.is_file(): self._json({"ok": False, "error": "Handoff document not found."}, 404); return
                if action == "done":
                    data, _, err = latest_valid_checkpoint(workspace, config, tid)
                    if data is None: self._json({"ok": False, "error": err or "Valid checkpoint not found."}, 409); return
                    from datetime import datetime, timezone
                    data.setdefault("task", {})["status"] = "complete"
                    data.setdefault("provenance", {})["handoff_done_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                    save_checkpoint(workspace, config, data)
                hp.unlink()
                active_cleared = False
                if action == "done" and read_active_task(workspace) == tid: active_cleared = clear_active_task(workspace)
                self._json({"ok": True, "action": action, "task_id": tid, "active_task_cleared": active_cleared})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._json({"ok": False, "error": str(exc) or "Invalid request."}, 400)
            except OSError:
                self._json({"ok": False, "error": "Could not update the handoff file."}, 500)

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
                        "test_count": len((task.get("tests") or {}).get("executed") or []) if isinstance(task.get("tests"), dict) else 0,
                        "history_count": len(list(histories.glob("checkpoint-*.json"))) if histories.is_dir() else 0,
                        "next_steps": task.get("next_steps") or cp.get("next_steps") or [],
                        "decisions": task.get("decisions") or cp.get("decisions") or [],
                    })
                    events.append({"task_id": tid, "time": cp.get("updated_at"), "type": "checkpoint", "title": "Checkpoint updated", "detail": str(cp_path) if cp_path else ""})
                    if handoff.is_file() and not handoff.is_symlink():
                        events.append({"task_id": tid, "time": handoff.stat().st_mtime, "type": "handoff", "title": "Handoff available", "detail": handoff.name})
                events.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
                memory_path = workspace / "PROJECT_MEMORY.md"
                memory_text = memory_path.read_text(encoding="utf-8") if memory_path.is_file() and not memory_path.is_symlink() else ""
                self._json({"ok": True, "workspace": str(workspace), "version": "1.0", "git": collect_git_state(workspace), "tasks": tasks, "events": events[:40], "project_memory": memory_text, "project_memory_path": str(memory_path)})
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

    server = None
    last_error = None
    candidates = [port] if host not in ("127.0.0.1", "localhost") else range(port, min(port + 32, 65536))
    for candidate in candidates:
        try:
            server = ThreadingHTTPServer((host, candidate), Handler)
            break
        except OSError as exc:
            last_error = exc
    if server is None:
        raise RuntimeError(f"No available dashboard port in range {port}-{min(port + 31, 65535)}: {last_error}")
    actual_port = int(server.server_address[1])
    url = f"http://{host}:{actual_port}/"
    print(f"Relay Dashboard: {url}")
    print(f"Workspace: {workspace}")
    print("Read-only local dashboard. Press Ctrl+C to stop.")
    if open_browser: webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
