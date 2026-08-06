import re

_PATTERNS = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?i)bearer\s+[a-z0-9._-]+"),
    re.compile(r"(?i)(?:sk|api[_-]?key)[_-][a-z0-9_-]{8,}"),
    re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)"),
)


def redact_sensitive_text(value: str) -> str:
    for pattern in _PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value
