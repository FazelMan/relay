#!/usr/bin/env bash
# Install or remove Handoff skill adapters (+ optional hooks).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage: install.sh <claude-code|codex|cursor|uninstall> [--dest DIR] [--with-hooks]

  claude-code  ~/.claude/skills/handoff
  codex        ~/.agents/skills/handoff
  cursor       ~/.cursor/skills/handoff
  uninstall    Remove default personal installs

  --with-hooks  Also print hook install hints (does not silently modify host settings)
EOF
}

install_layout() {
  local dest="$1"
  local adapter="$2"

  mkdir -p "$dest"
  cp "$ROOT/SKILL.md" "$dest/PORTABLE.md"
  cp "$adapter" "$dest/SKILL.md"
  rm -rf "$dest/references" "$dest/templates"
  cp -R "$ROOT/references" "$dest/references"
  cp -R "$ROOT/templates" "$dest/templates"
  # Point agents at the repo's relay package
  printf '%s\n' "$REPO_ROOT" >"$dest/RELAY_ROOT"
  cat >"$dest/relay-env.sh" <<EOF
# Source before python3 -m relay if Relay is not on PYTHONPATH
export PYTHONPATH="${REPO_ROOT}\${PYTHONPATH:+:\$PYTHONPATH}"
EOF
  printf 'Installed handoff skill to %s\n' "$dest"
  printf 'Set PYTHONPATH to include %s (see %s/relay-env.sh)\n' "$REPO_ROOT" "$dest"
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
  claude-code)
    dest="${dest_override:-$HOME/.claude/skills/handoff}"
    install_layout "$dest" "$ROOT/adapters/claude-code/SKILL.md"
    if [[ "$WITH_HOOKS" -eq 1 ]]; then
      printf 'Optional hooks template: %s\n' "$ROOT/adapters/claude-code/hooks.json"
      printf 'Merge into Claude Code hooks settings; keep mechanical-only.\n'
    fi
    ;;
  codex)
    dest="${dest_override:-$HOME/.agents/skills/handoff}"
    install_layout "$dest" "$ROOT/adapters/codex/SKILL.md"
    if [[ "$WITH_HOOKS" -eq 1 ]]; then
      printf 'Optional hooks template: %s\n' "$ROOT/adapters/codex/hooks.json"
      printf 'Copy to ~/.codex/hooks.json or <project>/.codex/hooks.json and trust via /hooks.\n'
    fi
    ;;
  cursor)
    dest="${dest_override:-$HOME/.cursor/skills/handoff}"
    install_layout "$dest" "$ROOT/adapters/cursor/SKILL.md"
    cp "$ROOT/adapters/cursor/relay-continuity.mdc" "$dest/relay-continuity.mdc"
    printf 'Optional: copy relay-continuity.mdc into the project .cursor/rules/\n'
    ;;
  uninstall)
    for d in \
      "$HOME/.claude/skills/handoff" \
      "$HOME/.agents/skills/handoff" \
      "$HOME/.cursor/skills/handoff"; do
      if [[ -d "$d" ]]; then
        rm -rf "$d"
        printf 'Removed %s\n' "$d"
      else
        printf 'Skip (missing): %s\n' "$d"
      fi
    done
    ;;
  *)
    usage
    exit 1
    ;;
esac
