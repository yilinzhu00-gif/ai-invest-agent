import re

from backend.app.security.pii import redact_sensitive_text

_SECRET_PATTERNS = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:password|passwd|secret)\s*[:=]\s*[^\s,;]{8,}"),
)


def contains_sensitive_text(value: str) -> bool:
    if redact_sensitive_text(value) != value:
        return True
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)
