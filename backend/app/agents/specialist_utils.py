"""Small deterministic helpers shared by Phase 2 specialist nodes."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from backend.app.agents.schemas import Citation


def number(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def text(value: Any, default: str = "") -> str:
    return str(value).strip() if value not in (None, "") else default


def citation_ids(
    evidence: Iterable[Citation], *, keywords: tuple[str, ...], fallback: str
) -> list[str]:
    """Select matching citations, falling back to the first supplied source."""
    items = list(evidence)
    matching = [
        item.id
        for item in items
        if any(keyword.casefold() in f"{item.source} {item.locator} {item.text}".casefold() for keyword in keywords)
    ]
    if matching:
        return list(dict.fromkeys(matching[:3]))
    if items:
        return [items[0].id]
    return [fallback]


def finite_metrics(data: dict[str, object]) -> dict[str, float]:
    return {
        key: value
        for key, raw in data.items()
        if (value := number(raw)) is not None
    }


def collect_claims(findings: Iterable[Any]) -> list[Any]:
    claims: list[Any] = []
    for finding in findings:
        claims.extend(finding.claims)
    return claims
