from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    workspace_id: str
    document_id: str
    document_version: int
    page_number: int
    block_id: str
    text: str
    status: str
    keyword_score: float = 0
    dense_score: float = 0
    table_id: str | None = None
    cell_refs: list[dict[str, object]] = field(default_factory=list)
    bbox: list[float] | None = None
    allowed_principals: set[str] = field(default_factory=set)
    rrf_score: float = 0


class InMemoryKnowledgeRepository:
    """Test/profile adapter; P2-06 SQL repository replaces this boundary in production."""

    def __init__(self, items: list[EvidenceItem]) -> None:
        self.items = items

    def authorized_active(self, workspace_id: str, principal_id: str) -> list[EvidenceItem]:
        return [
            item
            for item in self.items
            if item.workspace_id == workspace_id
            and item.status == "active"
            and (not item.allowed_principals or principal_id in item.allowed_principals)
        ]


class HybridRetriever:
    def __init__(self, repository: InMemoryKnowledgeRepository) -> None:
        self.repository = repository

    def retrieve(
        self, query: str, *, workspace_id: str, principal_id: str, top_k: int
    ) -> list[EvidenceItem]:
        candidates = self.repository.authorized_active(workspace_id, principal_id)
        query_terms = {term for term in query.lower().split() if term}
        keyword_rank = sorted(
            candidates,
            key=lambda item: (sum(term in item.text.lower() for term in query_terms), item.keyword_score),
            reverse=True,
        )
        dense_rank = sorted(candidates, key=lambda item: item.dense_score, reverse=True)
        scores: dict[str, float] = {}
        for rank, item in enumerate(keyword_rank, start=1):
            scores[item.id] = scores.get(item.id, 0) + 1 / (60 + rank)
        for rank, item in enumerate(dense_rank, start=1):
            scores[item.id] = scores.get(item.id, 0) + 1 / (60 + rank)
        return [
            replace(item, rrf_score=scores[item.id])
            for item in sorted(candidates, key=lambda item: scores[item.id], reverse=True)[:top_k]
        ]
