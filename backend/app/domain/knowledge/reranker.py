from backend.app.domain.knowledge.retrieval import EvidenceItem


def rerank_authorized(items: list[EvidenceItem], *, limit: int = 12) -> list[EvidenceItem]:
    """Placeholder deterministic rerank; callers must pass ACL-filtered candidates only."""
    return sorted(items, key=lambda item: item.rrf_score, reverse=True)[:limit]
