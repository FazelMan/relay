"""Sensitive-data filtering for checkpoints and handoffs."""

from __future__ import annotations

import re
from typing import Any

# Patterns that indicate secret-like values (values redacted, keys kept).
SECRET_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|private[_-]?key|access[_-]?key|"
    r"auth|credential|bearer|session[_-]?id|client[_-]?secret|aws_secret)"
)
SECRET_VALUE_RE = re.compile(
    r"(?i)\b(sk-[a-z0-9]{20,}|ghp_[a-zA-Z0-9]{36,}|xox[baprs]-[a-zA-Z0-9-]{10,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)

REDACTED = "[REDACTED]"


def looks_secret_key(key: str) -> bool:
    return bool(SECRET_KEY_RE.search(key))


def redact_string(value: str) -> str:
    if SECRET_VALUE_RE.search(value):
        return SECRET_VALUE_RE.sub(REDACTED, value)
    return value


def scrub(value: Any, *, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key = str(k)
            if looks_secret_key(key) and not isinstance(v, (dict, list)):
                out[key] = REDACTED
            else:
                out[key] = scrub(v, parent_key=key)
        return out
    if isinstance(value, list):
        return [scrub(v, parent_key=parent_key) for v in value]
    if isinstance(value, str):
        if looks_secret_key(parent_key):
            return REDACTED
        return redact_string(value)
    return value
