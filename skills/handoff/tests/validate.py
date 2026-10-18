#!/usr/bin/env python3
"""Dependency-free validation for the handoff skill package + relay layout."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]

REQUIRED_FILES = [
    ROOT / "SKILL.md",
    ROOT / "README.md",
    ROOT / "templates" / "HANDOFF.md",
    ROOT / "references" / "handoff-format.md",
    ROOT / "references" / "safety-and-validation.md",
    ROOT / "references" / "checkpoint-schema.md",
    ROOT / "adapters" / "claude-code" / "SKILL.md",
    ROOT / "adapters" / "claude-code" / "hooks.json",
    ROOT / "adapters" / "codex" / "SKILL.md",
    ROOT / "adapters" / "codex" / "hooks.json",
    ROOT / "adapters" / "cursor" / "SKILL.md",
    ROOT / "adapters" / "generic" / "SKILL.md",
    ROOT / "examples" / "save-feature-handoff.md",
    ROOT / "examples" / "resume-verification-notes.md",
    ROOT / "examples" / "checkpoint.example.json",
    ROOT / "scripts" / "install.sh",
    REPO / "README.md",
    REPO / "LICENSE",
    REPO / "docs" / "installation.md",
    REPO / "docs" / "compatibility.md",
    REPO / "docs" / "auto-checkpoint.md",
    REPO / "docs" / "handoff-guard.md",
    REPO / "docs" / "cross-agent.md",
    REPO / "docs" / "configuration.md",
    REPO / "CONTRIBUTING.md",
    REPO / "relay" / "__main__.py",
    REPO / "relay" / "cli.py",
    REPO / "relay" / "schema.py",
    REPO / "relay" / "storage.py",
    REPO / "relay" / "guard.py",
]

TEMPLATE_SECTIONS = [
    "## 1. Task objective",
    "## 2. Current status",
    "## 3. Completed",
    "## 4. Unfinished",
    "## 5. Important decisions",
    "## 6. Relevant files and changes",
    "## 7. Tests and results",
    "## 8. Blockers and risks",
    "## 9. Next recommended action",
    "## 10. Validate workspace before editing",
]

SAFETY_PATTERNS = [
    r"secret|credential|api keys?|tokens?|private keys?",
    r"reset|clean|force-push|destructive",
    r"commit|push|deploy",
]

FAKE_PASS_PATTERNS = [
    r"(?i)tests?\s+(all\s+)?passed",
    r"(?i)typecheck\s+passed",
    r"(?i)full test suite\s*\|\s*yes\s*\|\s*pass",
]

ZERO_LLM_PATTERNS = [
    r"must not invoke an LLM|without LLM|no LLM|llm_invoked",
]


def parse_frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---"):
        return None
    match = re.match(r"^---\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return None
    data: dict[str, str] = {}
    key = None
    buf: list[str] = []
    for line in match.group(1).splitlines():
        if re.match(r"^[a-zA-Z0-9_-]+:\s*", line) and not line.startswith(" "):
            if key is not None:
                data[key] = "\n".join(buf).strip().strip("\"'")
            key, _, rest = line.partition(":")
            key = key.strip()
            rest = rest.strip()
            if rest in (">", "|"):
                buf = []
            else:
                buf = [rest] if rest else []
        elif key is not None:
            buf.append(line.strip())
    if key is not None:
        data[key] = "\n".join(buf).strip().strip("\"'")
    return data


def check_name(name: str) -> str | None:
    if not name or len(name) > 64:
        return f"invalid name length: {name!r}"
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        return f"invalid name charset: {name!r}"
    return None


def resolve_md_links(file_path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
        if link.startswith(("http://", "https://", "mailto:")):
            continue
        if link.startswith("#"):
            continue
        target = link.split("#", 1)[0]
        if not target or target in ("PORTABLE.md", "hooks.json"):
            continue
        if target.startswith(("references/", "templates/")) and "adapters" in str(file_path):
            alt = ROOT / target
            if alt.is_file():
                continue
        resolved = (file_path.parent / target).resolve()
        if not resolved.exists():
            errors.append(f"{file_path.relative_to(REPO)}: broken link {link}")
    return errors


def main() -> int:
    errors: list[str] = []

    for path in REQUIRED_FILES:
        if not path.is_file():
            errors.append(f"missing required file: {path}")

    skill_files = [
        ROOT / "SKILL.md",
        ROOT / "adapters" / "claude-code" / "SKILL.md",
        ROOT / "adapters" / "codex" / "SKILL.md",
        ROOT / "adapters" / "cursor" / "SKILL.md",
        ROOT / "adapters" / "generic" / "SKILL.md",
    ]
    for path in skill_files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm is None:
            errors.append(f"{path}: missing/invalid YAML frontmatter")
            continue
        if "name" not in fm or "description" not in fm:
            errors.append(f"{path}: frontmatter requires name and description")
        else:
            name_err = check_name(fm["name"])
            if name_err:
                errors.append(f"{path}: {name_err}")
            if len(fm["description"]) > 1024:
                errors.append(f"{path}: description exceeds 1024 chars")
        errors.extend(resolve_md_links(path, text))

    template = (ROOT / "templates" / "HANDOFF.md").read_text(encoding="utf-8")
    for section in TEMPLATE_SECTIONS:
        if section not in template:
            errors.append(f"template missing section: {section}")

    safety_blob = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (
            ROOT / "SKILL.md",
            ROOT / "references" / "safety-and-validation.md",
            REPO / "docs" / "installation.md",
            REPO / "docs" / "auto-checkpoint.md",
        )
        if p.is_file()
    )
    for pat in SAFETY_PATTERNS:
        if not re.search(pat, safety_blob, re.I):
            errors.append(f"safety docs missing expected guidance pattern: {pat}")
    if not any(re.search(p, safety_blob, re.I) for p in ZERO_LLM_PATTERNS):
        errors.append("docs must state mechanical checkpointing does not call an LLM")

    example = (ROOT / "examples" / "save-feature-handoff.md").read_text(encoding="utf-8")
    for pat in FAKE_PASS_PATTERNS:
        if re.search(pat, example):
            errors.append(f"example claims successful tests unexpectedly: {pat}")
    if "not run" not in example.lower():
        errors.append("example should record checks as not run")

    install_docs = (REPO / "docs" / "installation.md").read_text(encoding="utf-8")
    for needle in (
        "~/.claude/skills/handoff",
        "~/.agents/skills/handoff",
        "~/.cursor/skills/handoff",
        "install.sh",
        "uninstall",
    ):
        if needle not in install_docs:
            errors.append(f"installation.md missing expected path/command: {needle}")

    install_sh = ROOT / "scripts" / "install.sh"
    if install_sh.is_file() and not install_sh.stat().st_mode & 0o111:
        errors.append("scripts/install.sh is not executable")

    for path in (
        ROOT / "SKILL.md",
        ROOT / "README.md",
        REPO / "README.md",
        REPO / "docs" / "installation.md",
        REPO / "docs" / "compatibility.md",
        REPO / "docs" / "cross-agent.md",
    ):
        if path.is_file():
            errors.extend(resolve_md_links(path, path.read_text(encoding="utf-8")))

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("OK")
    print(f"  checked {len(REQUIRED_FILES)} required paths")
    print(f"  frontmatter OK for {len(skill_files)} SKILL.md files")
    print(f"  template sections OK ({len(TEMPLATE_SECTIONS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
