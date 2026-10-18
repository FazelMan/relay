"""Relay CLI — mechanical checkpointing without LLM calls."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .active_task import (
    MECHANICAL_FALLBACK_ID,
    clear_active_task,
    read_active_task,
    resolve_task_id,
    set_active_task,
)
from .config import EXAMPLE_TOML, load_config
from .change_tracking import record_change_event
from .gitinfo import collect_git_state
from .guard import (
    WarningDeduper,
    apply_guard_to_checkpoint,
    evaluate_risk,
    local_state_path,
)
from .handoff_md import render_handoff
from .install_lib import install_adapter, uninstall_adapter
from .monitor import (
    Observation,
    context_from_utilization,
    parse_claude_session_start,
    quota_from_rate_limit,
    unsupported_context,
    unsupported_quota,
)
from .paths import resolve_workspace
from .resume import prepare_resume
from .schema import empty_checkpoint, merge_checkpoint, validate_checkpoint
from .secrets import scrub
from .storage import (
    StorageError,
    atomic_write_text,
    checkpoint_path,
    create_mechanical_checkpoint,
    handoff_path,
    latest_valid_checkpoint,
    list_legacy_handoffs,
    list_tasks,
    save_checkpoint,
    sanitize_task_id,
    try_load_checkpoint,
)


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2))


def _maybe_set_active(workspace: Path, task_id: str, *, activate: bool) -> None:
    if activate and task_id != MECHANICAL_FALLBACK_ID:
        set_active_task(workspace, task_id, set_by="cli")


def cmd_checkpoint(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    config = load_config(workspace)
    task_id = sanitize_task_id(args.task)
    existing, _, _ = latest_valid_checkpoint(workspace, config, task_id)
    git_state = collect_git_state(workspace)
    cp = create_mechanical_checkpoint(
        workspace,
        config,
        task_id,
        git_state=git_state,
        existing=existing,
        host=args.host,
        trigger=args.trigger,
    )

    if args.semantic_json:
        patch = json.loads(Path(args.semantic_json).read_text(encoding="utf-8"))
        if not isinstance(patch, dict):
            print("semantic JSON must be an object", file=sys.stderr)
            return 2
        cp = merge_checkpoint(cp, scrub(patch))
        cp.setdefault("provenance", {})["kind"] = "semantic"

    if args.objective:
        cp.setdefault("task", {})["objective"] = args.objective

    path = save_checkpoint(workspace, config, cp)
    if not getattr(args, "no_activate", False):
        _maybe_set_active(workspace, task_id, activate=True)
    result = {"ok": True, "path": str(path), "task_id": task_id, "trigger": args.trigger}
    if args.write_handoff:
        md = render_handoff(cp)
        hp = handoff_path(workspace, config, task_id)
        atomic_write_text(hp, md)
        result["handoff"] = str(hp)
    _print_json(result)
    return 0


def _stable_handoff_text(text: str) -> str:
    """Ignore the generated timestamp when checking whether a handoff changed."""
    import re
    return re.sub(r"(?m)^> \*\*Updated:\*\*.*$", "> **Updated:** <timestamp>", text).strip()


def cmd_handoff(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    config = load_config(workspace)
    if getattr(args, "handoff_command", None) == "list":
        root_tasks = list_tasks(workspace, config)
        entries = []
        for tid in root_tasks:
            hp = handoff_path(workspace, config, tid)
            if hp.is_file() and not hp.is_symlink():
                cp, _, _ = latest_valid_checkpoint(workspace, config, tid)
                entries.append({
                    "task_id": tid, "name": tid, "path": str(hp),
                    "updated_at": (cp or {}).get("updated_at"),
                })
        legacy = [
            {"name": p.name, "path": str(p), "legacy": True}
            for p in list_legacy_handoffs(workspace, config)
            if p.is_file() and not p.is_symlink()
        ]
        _print_json({"ok": True, "handoffs": entries, "legacy_handoffs": legacy, "count": len(entries) + len(legacy)})
        return 0
    if getattr(args, "handoff_command", None) == "delete":
        task_id = sanitize_task_id(args.task_id)
        hp = handoff_path(workspace, config, task_id)
        if not getattr(args, "yes", False):
            _print_json({"ok": False, "error": "confirmation required; pass --yes to delete only HANDOFF.md"})
            return 2
        if hp.is_symlink():
            _print_json({"ok": False, "error": "refusing to delete a symlink"})
            return 2
        if not hp.is_file():
            _print_json({"ok": False, "error": "handoff document not found", "task_id": task_id, "path": str(hp)})
            return 1
        hp.unlink()
        _print_json({
            "ok": True, "deleted": str(hp), "task_id": task_id,
            "preserved": [str(checkpoint_path(workspace, config, task_id)), str(hp.parent / "history"), "all project files"],
            "message": "Only HANDOFF.md was deleted; checkpoint, checkpoint history, task directory, and project work were preserved.",
        })
        return 0

    workspace = resolve_workspace(args.workspace)
    config = load_config(workspace)
    task_id = sanitize_task_id(args.task)
    data, path, err = latest_valid_checkpoint(workspace, config, task_id)
    previous_checkpoint = deepcopy(data) if data is not None else None
    previous_handoff = handoff_path(workspace, config, task_id)
    previous_text = None
    if previous_handoff.is_file() and not previous_handoff.is_symlink():
        previous_text = previous_handoff.read_text(encoding="utf-8")
    git_state = collect_git_state(workspace)
    if data is None:
        data = empty_checkpoint(task_id=task_id, workspace_path=str(workspace), source="handoff")
        if err:
            data.setdefault("provenance", {})["notes"] = f"prior load: {err}"
    data = create_mechanical_checkpoint(
        workspace, config, task_id, git_state=git_state, existing=data,
        host=args.host, trigger="handoff",
    )
    if args.semantic_json:
        patch = json.loads(Path(args.semantic_json).read_text(encoding="utf-8"))
        if not isinstance(patch, dict):
            print("semantic JSON must be an object", file=sys.stderr)
            return 2
        data = merge_checkpoint(data, scrub(patch))
        data.setdefault("provenance", {})["kind"] = "handoff"
    if args.objective:
        data.setdefault("task", {})["objective"] = args.objective
    md = render_handoff(data)
    if (previous_text is not None and _stable_handoff_text(previous_text) == _stable_handoff_text(md)\n            and previous_checkpoint is not None\n            and _stable_checkpoint_data(previous_checkpoint) == _stable_checkpoint_data(data)):
        _print_json({
            "ok": True, "unchanged": True, "task_id": task_id,
            "name": task_id, "handoff": str(previous_handoff),
            "message": f"این handoff قبلاً با نام «{task_id}» و شناسه «{task_id}» ذخیره شده؛ تغییری برای ثبت مجدد وجود ندارد.",
        })
        return 0
    path = save_checkpoint(workspace, config, data)
    change_event = record_change_event(workspace, config, task_id, previous_checkpoint, data)
    atomic_write_text(previous_handoff, md)
    if not getattr(args, "no_activate", False):
        _maybe_set_active(workspace, task_id, activate=True)
    _print_json({"ok": True, "unchanged": False, "checkpoint": str(path), "handoff": str(previous_handoff), "change_event": str(change_event) if change_event else None, "task_id": task_id, "name": task_id})
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    config = load_config(workspace)
    tasks = list_tasks(workspace, config)
    legacy = [str(p) for p in list_legacy_handoffs(workspace, config)]
    active = read_active_task(workspace)
    report: dict[str, Any] = {
        "relay_version": __version__,
        "workspace": str(workspace),
        "storage_dir": config.storage_dir,
        "active_task": active,
        "tasks": tasks,
        "legacy_handoffs": legacy,
        "monitoring": {
            "context": (
                "host-dependent; use guard-eval with explicit metrics or Claude "
                "SessionStart tokens + context_capacity_tokens"
            ),
            "quota": "unsupported unless rate-limit signal provided",
            "automatic": False,
        },
        "git": collect_git_state(workspace),
    }
    selected = args.task or active
    if selected:
        tid = sanitize_task_id(selected)
        data, _path, err = latest_valid_checkpoint(workspace, config, tid)
        report["selected_task"] = tid
        report["checkpoint_path"] = str(checkpoint_path(workspace, config, tid))
        report["handoff_path"] = str(handoff_path(workspace, config, tid))
        report["checkpoint_valid"] = data is not None
        report["checkpoint_error"] = err
        if data:
            report["updated_at"] = data.get("updated_at")
            report["task_status"] = (data.get("task") or {}).get("status")
            report["risk"] = data.get("risk")
            report["context"] = data.get("context")
            report["quota"] = data.get("quota")
            report["cross_agent_ready"] = handoff_path(workspace, config, tid).is_file()
    _print_json(report)
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    config = load_config(workspace)
    report = prepare_resume(workspace, config, args.task)
    out = report.to_dict()
    out["ok"] = report.valid
    _print_json(out)
    return 0 if report.valid else 1


def cmd_guard_eval(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    config = load_config(workspace)
    resolution = resolve_task_id(
        workspace,
        config,
        args.task,
        allow_mechanical_fallback=True,
    )
    task_id = resolution.task_id

    if args.context_pct is not None:
        context: Observation | None = context_from_utilization(
            float(args.context_pct) / 100.0, source=args.source or "cli"
        )
    else:
        context = unsupported_context(source=args.source or "cli")

    if args.rate_limited:
        quota: Observation | None = quota_from_rate_limit(source=args.source or "cli")
    else:
        quota = unsupported_quota(source=args.source or "cli")

    decision = evaluate_risk(
        context=context,
        quota=quota,
        thresholds=config.thresholds,
        session_interrupted=args.interrupted,
        handoff_artifacts_ready=handoff_path(workspace, config, task_id).is_file()
        if not resolution.is_mechanical_fallback
        else False,
        resuming=args.resuming,
    )

    warn = decision.should_warn
    if warn and not args.no_dedupe:
        deduper = WarningDeduper(
            local_state_path(workspace), config.warning_cooldown_seconds
        )
        deduper.load()
        if not deduper.should_emit(
            warning_level=decision.warning_level,
            task_id=task_id,
            session_id=args.session_id,
        ):
            warn = False
            decision.should_warn = False
            decision.warning_message = None
        else:
            deduper.save()
    elif not warn and not args.no_dedupe:
        deduper = WarningDeduper(
            local_state_path(workspace), config.warning_cooldown_seconds
        )
        deduper.load()
        deduper.note_recovery(task_id=task_id, session_id=args.session_id)
        deduper.save()

    checkpoint_written = None
    if decision.should_mechanical_checkpoint:
        # Mechanical fallback: never merge semantic fields from unrelated tasks.
        existing = None
        if not resolution.is_mechanical_fallback:
            existing, _, _ = latest_valid_checkpoint(workspace, config, task_id)
        elif latest_valid_checkpoint(workspace, config, task_id)[0] is not None:
            existing, _, _ = latest_valid_checkpoint(workspace, config, task_id)

        git_state = collect_git_state(workspace)
        cp = create_mechanical_checkpoint(
            workspace,
            config,
            task_id,
            git_state=git_state,
            existing=existing,
            host=args.host,
            trigger="risk",
        )
        if resolution.is_mechanical_fallback:
            cp.setdefault("provenance", {})["notes"] = resolution.message
        cp["context"] = context.to_dict() if context else cp.get("context")
        cp["quota"] = quota.to_dict() if quota else cp.get("quota")
        cp = apply_guard_to_checkpoint(cp, decision)
        checkpoint_written = str(save_checkpoint(workspace, config, cp))
        if (
            decision.should_prepare_handoff
            and config.auto_handoff_on_critical
            and not resolution.is_mechanical_fallback
        ):
            atomic_write_text(
                handoff_path(workspace, config, task_id), render_handoff(cp)
            )

    _print_json(
        decision.to_dict()
        | {
            "warned": warn,
            "task_resolution": resolution.to_dict(),
            "checkpoint": checkpoint_written,
        }
    )
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    """Host hook entry: read JSON event from stdin; mechanical only (no LLM)."""
    workspace = resolve_workspace(args.workspace)
    config = load_config(workspace)
    try:
        raw_stdin = sys.stdin.read()
        event = json.loads(raw_stdin) if raw_stdin.strip() else {}
    except json.JSONDecodeError as exc:
        _print_json(
            {
                "ok": False,
                "error": f"invalid hook JSON on stdin: {exc}",
                "llm_invoked": False,
                "checkpoint": None,
            }
        )
        return 2
    if not isinstance(event, dict):
        event = {}

    host = args.host
    event_name = args.event or event.get("hook_event_name") or event.get("event") or ""
    # Explicit --task wins; otherwise resolve (never silent "default").
    requested = args.task  # may be None
    resolution = resolve_task_id(
        workspace, config, requested, allow_mechanical_fallback=True
    )
    task_id = resolution.task_id
    session_id = (
        event.get("session_id")
        or event.get("conversation_id")
        or args.session_id
    )

    context = unsupported_context(source=f"{host}:{event_name}")
    quota = unsupported_quota(source=f"{host}:{event_name}")

    if host == "claude-code" and event_name == "SessionStart":
        context = parse_claude_session_start(
            event, capacity_tokens=config.context_capacity_tokens
        )

    do_checkpoint = False
    if event_name == "PreCompact" and config.mechanical_on_precompact:
        do_checkpoint = True
    if event_name == "Stop" and config.mechanical_on_stop:
        do_checkpoint = True
    if event_name in ("SessionEnd",) or args.force_checkpoint:
        do_checkpoint = True

    decision = evaluate_risk(
        context=context,
        quota=quota,
        thresholds=config.thresholds,
        handoff_artifacts_ready=(
            handoff_path(workspace, config, task_id).is_file()
            if not resolution.is_mechanical_fallback
            else False
        ),
    )

    result: dict[str, Any] = {
        "ok": True,
        "host": host,
        "event": event_name,
        "llm_invoked": False,
        "guard": decision.to_dict(),
        "task_resolution": resolution.to_dict(),
        "checkpoint": None,
    }

    if do_checkpoint:
        try:
            existing = None
            if not resolution.is_mechanical_fallback:
                existing, _, _ = latest_valid_checkpoint(workspace, config, task_id)
            else:
                # Only continue the mechanical fallback stream itself.
                existing, _, _ = latest_valid_checkpoint(workspace, config, task_id)
            git_state = collect_git_state(workspace)
            cp = create_mechanical_checkpoint(
                workspace,
                config,
                task_id,
                git_state=git_state,
                existing=existing,
                host=host,
                trigger="mechanical",
            )
            if resolution.is_mechanical_fallback:
                cp.setdefault("provenance", {})["notes"] = resolution.message
                # Keep semantic fields empty-ish for fallback identity
                if existing is None:
                    cp["task"]["objective"] = (
                        cp["task"].get("objective")
                        or "(unscoped mechanical snapshot — set active task)"
                    )
            cp["context"] = context.to_dict()
            cp["quota"] = quota.to_dict()
            cp = apply_guard_to_checkpoint(cp, decision)
            path = save_checkpoint(workspace, config, cp)
            result["checkpoint"] = str(path)
        except StorageError as exc:
            result["ok"] = False
            result["error"] = str(exc)
            _print_json(result)
            return 2

        hp = handoff_path(workspace, config, task_id)
        if (
            hp.is_file()
            and event_name == "SessionStart"
            and not resolution.is_mechanical_fallback
        ):
            print(
                f"[relay] Resume artifacts: {hp} ; checkpoint: {result['checkpoint']}",
                file=sys.stderr,
            )
            sys.stdout.write(
                f"Relay: latest handoff at {hp}. Verify git status before continuing.\n"
            )
            return 0

    # Warning dedupe for hooks (stderr only; do not fail the hook)
    if decision.should_warn:
        deduper = WarningDeduper(
            local_state_path(workspace), config.warning_cooldown_seconds
        )
        deduper.load()
        if deduper.should_emit(
            warning_level=decision.warning_level,
            task_id=task_id,
            session_id=str(session_id) if session_id else None,
        ):
            deduper.save()
            if decision.warning_message:
                print(f"[relay] {decision.warning_message}", file=sys.stderr)
        result["warned"] = True
    else:
        result["warned"] = False

    if not (
        result.get("checkpoint")
        and host == "claude-code"
        and event_name == "SessionStart"
        and not resolution.is_mechanical_fallback
    ):
        _print_json(result)
    return 0 if result.get("ok", True) else 2


def cmd_task(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    if args.task_command == "set":
        path = set_active_task(workspace, args.task_id, set_by="cli")
        _print_json({"ok": True, "active_task": args.task_id, "path": str(path)})
        return 0
    if args.task_command == "get":
        active = read_active_task(workspace)
        config = load_config(workspace)
        resolution = resolve_task_id(
            workspace, config, None, allow_mechanical_fallback=True
        )
        _print_json(
            {
                "ok": True,
                "active_task": active,
                "resolution": resolution.to_dict(),
            }
        )
        return 0
    if args.task_command == "clear":
        cleared = clear_active_task(workspace)
        _print_json({"ok": True, "cleared": cleared})
        return 0
    return 2


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.path)
    data, err = try_load_checkpoint(path)
    if err:
        _print_json({"ok": False, "error": err})
        return 1
    errors = validate_checkpoint(data)
    _print_json({"ok": not errors, "errors": errors})
    return 0 if not errors else 1


def cmd_example_config(_: argparse.Namespace) -> int:
    sys.stdout.write(EXAMPLE_TOML)
    return 0


def _skill_paths() -> tuple[Path, Path]:
    # relay/ -> repo root
    repo = Path(__file__).resolve().parents[1]
    skill = repo / "skills" / "handoff"
    return repo, skill


def cmd_install(args: argparse.Namespace) -> int:
    repo, skill = _skill_paths()
    host = args.host
    adapters = {
        "claude-code": skill / "adapters" / "claude-code" / "SKILL.md",
        "codex": skill / "adapters" / "codex" / "SKILL.md",
        "cursor": skill / "adapters" / "cursor" / "SKILL.md",
    }
    defaults = {
        "claude-code": Path.home() / ".claude" / "skills" / "handoff",
        "codex": Path.home() / ".agents" / "skills" / "handoff",
        "cursor": Path.home() / ".cursor" / "skills" / "handoff",
    }
    dest = Path(args.dest).expanduser() if args.dest else defaults[host]
    result = install_adapter(
        dest=dest,
        skill_root=skill,
        repo_root=repo,
        adapter_skill=adapters[host],
        include_cursor_rule=(host == "cursor"),
    )
    out = result.to_dict()
    out["host"] = host
    out["wrapper"] = str(dest / "bin" / "relay-run")
    out["hook_hint"] = (
        f"Use {dest / 'bin' / 'relay-run'} hook --host {host} --event <Event> "
        "(omit --task to resolve active-task registry)"
    )
    _print_json(out)
    return 0 if result.ok else 2


def cmd_uninstall(args: argparse.Namespace) -> int:
    defaults = {
        "claude-code": Path.home() / ".claude" / "skills" / "handoff",
        "codex": Path.home() / ".agents" / "skills" / "handoff",
        "cursor": Path.home() / ".cursor" / "skills" / "handoff",
    }
    if args.dest:
        dests = [Path(args.dest).expanduser()]
    elif args.host:
        dests = [defaults[args.host]]
    else:
        dests = list(defaults.values())
    results = []
    ok = True
    for dest in dests:
        if not dest.exists():
            results.append({"ok": True, "dest": str(dest), "skipped": "missing"})
            continue
        r = uninstall_adapter(dest)
        results.append(r)
        if not r.get("ok", False):
            ok = False
    _print_json({"ok": ok, "results": results})
    return 0 if ok else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="relay", description="Relay continuity toolkit")
    p.add_argument("--version", action="version", version=f"relay {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_ws(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--workspace", default=".", help="Project root")

    sp = sub.add_parser("checkpoint", help="Write mechanical checkpoint (no LLM)")
    add_ws(sp)
    sp.add_argument("--task", required=True)
    sp.add_argument("--trigger", default="mechanical")
    sp.add_argument("--host", default=None)
    sp.add_argument("--objective", default=None)
    sp.add_argument("--semantic-json", default=None)
    sp.add_argument("--write-handoff", action="store_true")
    sp.add_argument("--no-activate", action="store_true")
    sp.set_defaults(func=cmd_checkpoint)

    sp = sub.add_parser("handoff", help="Save, list, or delete handoff documents")
    add_ws(sp)
    hsub = sp.add_subparsers(dest="handoff_command")
    hlist = hsub.add_parser("list", help="List saved handoff documents")
    add_ws(hlist)
    hlist.set_defaults(func=cmd_handoff)
    hdelete = hsub.add_parser("delete", help="Delete only a task's HANDOFF.md document")
    add_ws(hdelete)
    hdelete.add_argument("task_id")
    hdelete.add_argument("--yes", action="store_true", help="Confirm deletion of HANDOFF.md only")
    hdelete.set_defaults(func=cmd_handoff)
    sp.add_argument("--task", default=None)
    sp.add_argument("--host", default=None)
    sp.add_argument("--objective", default=None)
    sp.add_argument("--semantic-json", default=None)
    sp.add_argument("--no-activate", action="store_true")
    sp.set_defaults(func=cmd_handoff)

    sp = sub.add_parser("status", help="Show tasks and recovery readiness")
    add_ws(sp)
    sp.add_argument("--task", default=None)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("resume", help="Reconcile checkpoint vs workspace (no writes)")
    add_ws(sp)
    sp.add_argument("--task", default=None)
    sp.set_defaults(func=cmd_resume)

    sp = sub.add_parser("guard-eval", help="Evaluate risk from explicit metrics")
    add_ws(sp)
    sp.add_argument("--task", default=None)
    sp.add_argument("--session-id", default=None)
    sp.add_argument("--context-pct", type=float, default=None)
    sp.add_argument("--rate-limited", action="store_true")
    sp.add_argument("--interrupted", action="store_true")
    sp.add_argument("--handoff-ready", action="store_true")
    sp.add_argument("--resuming", action="store_true")
    sp.add_argument("--source", default=None)
    sp.add_argument("--host", default=None)
    sp.add_argument("--no-dedupe", action="store_true")
    sp.set_defaults(func=cmd_guard_eval)

    sp = sub.add_parser("hook", help="Host lifecycle hook (stdin JSON, no LLM)")
    add_ws(sp)
    sp.add_argument(
        "--host", required=True, choices=["claude-code", "codex", "cursor", "generic"]
    )
    sp.add_argument("--event", default=None)
    sp.add_argument(
        "--task",
        default=None,
        help="Optional. If omitted, resolve via RELAY_TASK / active-task registry / fallback",
    )
    sp.add_argument("--session-id", default=None)
    sp.add_argument("--force-checkpoint", action="store_true")
    sp.set_defaults(func=cmd_hook)

    tsp = sub.add_parser("task", help="Manage project-local active task registry")
    tsub = tsp.add_subparsers(dest="task_command", required=True)
    tset = tsub.add_parser("set", help="Set active task id")
    add_ws(tset)
    tset.add_argument("task_id")
    tset.set_defaults(func=cmd_task)
    tget = tsub.add_parser("get", help="Show active task and resolution")
    add_ws(tget)
    tget.set_defaults(func=cmd_task)
    tclr = tsub.add_parser("clear", help="Clear active task")
    add_ws(tclr)
    tclr.set_defaults(func=cmd_task)

    sp = sub.add_parser("validate", help="Validate a checkpoint.json file")
    sp.add_argument("path")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("example-config", help="Print example relay.toml")
    sp.set_defaults(func=cmd_example_config)

    sp = sub.add_parser("install", help="Safe skill adapter install")
    sp.add_argument("host", choices=["claude-code", "codex", "cursor"])
    sp.add_argument("--dest", default=None)
    sp.set_defaults(func=cmd_install)

    sp = sub.add_parser("uninstall", help="Remove only Relay-owned install files")
    sp.add_argument("--host", choices=["claude-code", "codex", "cursor"], default=None)
    sp.add_argument("--dest", default=None)
    sp.set_defaults(func=cmd_uninstall)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except StorageError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
