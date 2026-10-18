#!/usr/bin/env bash
# Thin wrapper around `python3 -m relay install|uninstall` (safe, non-destructive).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/../.." && pwd)"
export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

usage() {
  cat <<'EOF'
Usage: install.sh <claude-code|codex|cursor|uninstall> [--dest DIR] [--with-hooks]

Safe install: copies only Relay-owned files, backs up conflicts, preserves
custom files, writes .relay-install-manifest.json, and installs bin/relay-run.

Uninstall removes only files listed in the install manifest.
EOF
}

WITH_HOOKS=0
cmd="${1:-}"
shift || true
dest_override=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)
      dest_override="${2:-}"
      shift 2
      ;;
    --with-hooks)
      WITH_HOOKS=1
      shift
      ;;
    *)
      echo "unknown arg: $1" >&2
      usage
      exit 1
      ;;
  esac
done

case "$cmd" in
  claude-code|codex|cursor)
    args=(install "$cmd")
    if [[ -n "$dest_override" ]]; then
      args+=(--dest "$dest_override")
    fi
    python3 -m relay "${args[@]}"
    if [[ "$WITH_HOOKS" -eq 1 ]]; then
      printf 'Optional hooks template: %s/adapters/%s/hooks.json\n' "$ROOT" "$cmd"
      printf 'Point hook commands at <dest>/bin/relay-run (omit --task; uses active-task registry).\n'
    fi
    ;;
  uninstall)
    if [[ -n "$dest_override" ]]; then
      python3 -m relay uninstall --dest "$dest_override"
    else
      python3 -m relay uninstall
    fi
    ;;
  *)
    usage
    exit 1
    ;;
esac
