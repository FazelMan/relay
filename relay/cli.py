"""Relay CLI — mechanical checkpointing without LLM calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .config import EXAMPLE_TOML, load_config
from .gitinfo import collect_git_state
from .guard import (
    WarningDeduper,
    apply_guard_to_checkpoint,
    evaluate_risk,
    local_state_path,
)
from .handoff_md import render_handoff
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
from .schema import merge_checkpoint, validate_checkpoint
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
    result = {"ok": True, "path": str(path), "task_id": task_id, "trigger": args.trigger}
    if args.write_handoff:
        md = render_handoff(cp)
        hp = handoff_path(workspace, config, task_id)
        atomic_write_text(hp, md)
        result["handoff"] = str(hp)
    _print_json(result)
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    config = load_config(workspace)
    task_id = sanitize_task_id(args.task)
    data, path, err = latest_valid_checkpoint(workspace, config, task_id)
    if data is None:
        print(json.dumps({"ok": False, "error": err}), file=sys.stderr)
        return 1
    # Refresh mechanical repo state before writing handoff.
    git_state = collect_git_state(workspace)
    data = create_mechanical_checkpoint(
        workspace,
        config,
        task_id,
        git_state=git_state,
        existing=data,
        host=args.host,
        trigger="handoff",
    )
    if args.semantic_json:
        patch = json.loads(Path(args.semantic_json).read_text(encoding="utf-8"))
        data = merge_checkpoint(data, scrub(patch))
        data.setdefault("provenance", {})["kind"] = "handoff"
    save_checkpoint(workspace, config, data)
    md = render_handoff(data)
    hp = handoff_path(workspace, config, task_id)
    atomic_write_text(hp, md)
    _print_json({"ok": True, "checkpoint": str(path), "handoff": str(hp), "task_id": task_id})
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    config = load_config(workspace)
    tasks = list_tasks(workspace, config)
    legacy = [str(p) for p in list_legacy_handoffs(workspace, config)]
    report: dict[str, Any] = {
        "relay_version": __version__,
        "workspace": str(workspace),
        "storage_dir": config.storage_dir,
        "tasks": tasks,
        "legacy_handoffs": legacy,
        "monitoring": {
            "context": "host-dependent; use guard-eval with explicit metrics or Claude SessionStart tokens + context_capacity_tokens",
            "quota": "unsupported unless rate-limit signal provided",
        },
        "git": collect_git_state(workspace),
    }
    if args.task:
        tid = sanitize_task_id(args.task)
        data, path, err = latest_valid_checkpoint(workspace, config, tid)
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
    context: Observation | None = None
    quota: Observation | None = None

    if args.context_pct is not None:
        context = context_from_utilization(
            float(args.context_pct) / 100.0, source=args.source or "cli"
        )
    else:
        context = unsupported_context(source=args.source or "cli")

    if args.rate_limited:
        quota = quota_from_rate_limit(source=args.source or "cli")
    else:
        quota = unsupported_quota(source=args.source or "cli")

    decision = evaluate_risk(
        context=context,
        quota=quota,
        thresholds=config.thresholds,
        session_interrupted=args.interrupted,
        handoff_artifacts_ready=args.handoff_ready,
        resuming=args.resuming,
    )

    warn = decision.should_warn
    if warn and not args.no_dedupe:
        deduper = WarningDeduper(
            local_state_path(workspace), config.warning_cooldown_seconds
        )
        deduper.load()
        key = f"{decision.state}:{decision.context_state}:{decision.quota_state}"
        if not deduper.should_emit(key):
            warn = False
            decision.should_warn = False
            decision.warning_message = None
        else:
            deduper.save()

    if args.task and decision.should_mechanical_checkpoint:
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
            trigger="risk",
        )
        cp["context"] = context.to_dict() if context else cp.get("context")
        cp["quota"] = quota.to_dict() if quota else cp.get("quota")
        cp = apply_guard_to_checkpoint(cp, decision)
        save_checkpoint(workspace, config, cp)
        if decision.should_prepare_handoff and config.auto_handoff_on_critical:
            atomic_write_text(handoff_path(workspace, config, task_id), render_handoff(cp))

    _print_json(decision.to_dict() | {"warned": warn})
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    """Host hook entry: read JSON event from stdin; mechanical only (no LLM)."""
    workspace = resolve_workspace(args.workspace)
    config = load_config(workspace)
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        event = {}
    if not isinstance(event, dict):
        event = {}

    host = args.host
    event_name = args.event or event.get("hook_event_name") or event.get("event") or ""
    task_id = sanitize_task_id(args.task or "default")

    context = unsupported_context(source=f"{host}:{event_name}")
    quota = unsupported_quota(source=f"{host}:{event_name}")

    if host == "claude-code" and event_name == "SessionStart":
        context = parse_claude_session_start(
            event, capacity_tokens=config.context_capacity_tokens
        )

    # PreCompact / Stop → mechanical checkpoint when configured
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
        handoff_artifacts_ready=handoff_path(workspace, config, task_id).is_file(),
    )

    result: dict[str, Any] = {
        "ok": True,
        "host": host,
        "event": event_name,
        "llm_invoked": False,
        "guard": decision.to_dict(),
    }

    if do_checkpoint:
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
        cp["context"] = context.to_dict()
        cp["quota"] = quota.to_dict()
        cp = apply_guard_to_checkpoint(cp, decision)
        path = save_checkpoint(workspace, config, cp)
        result["checkpoint"] = str(path)
        # Additional context for SessionStart compact matcher (Claude): point at handoff
        hp = handoff_path(workspace, config, task_id)
        if hp.is_file() and event_name == "SessionStart":
            # stdout may be injected as context by host — keep tiny
            print(
                f"[relay] Resume artifacts: {hp} ; checkpoint: {path}",
                file=sys.stderr,
            )
            # For Claude SessionStart, stdout becomes additional context — keep bounded
            sys.stdout.write(
                f"Relay: latest handoff at {hp}. Verify git status before continuing.\n"
            )

    # Claude PreCompact: do not block compaction; only save
    if host == "claude-code" and event_name == "PreCompact":
        # Optional systemMessage via JSON on stdout is not always supported the same way;
        # keep exit 0 and mechanical save only.
        pass

    if "checkpoint" not in result:
        _print_json(result)
    elif host != "claude-code" or event_name != "SessionStart":
        _print_json(result)
    return 0


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
    sp.add_argument("--semantic-json", default=None, help="Optional agent-provided semantic patch")
    sp.add_argument("--write-handoff", action="store_true")
    sp.set_defaults(func=cmd_checkpoint)

    sp = sub.add_parser("handoff", help="Refresh checkpoint + write HANDOFF.md")
    add_ws(sp)
    sp.add_argument("--task", required=True)
    sp.add_argument("--host", default=None)
    sp.add_argument("--semantic-json", default=None)
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
    sp.add_argument("--host", required=True, choices=["claude-code", "codex", "cursor", "generic"])
    sp.add_argument("--event", default=None)
    sp.add_argument("--task", default="default")
    sp.add_argument("--force-checkpoint", action="store_true")
    sp.set_defaults(func=cmd_hook)

    sp = sub.add_parser("validate", help="Validate a checkpoint.json file")
    sp.add_argument("path")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("example-config", help="Print example relay.toml")
    sp.set_defaults(func=cmd_example_config)

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
