from backend.app.domain.knowledge.retrieval import (
    EvidenceItem,
    HybridRetriever,
    InMemoryKnowledgeRepository,
)


def test_acl_leak_is_zero_when_principal_is_not_granted() -> None:
    private = EvidenceItem(
        id="restricted",
        workspace_id="ws-1",
        document_id="doc-private",
        document_version=1,
        page_number=1,
        block_id="b1",
        text="restricted evidence",
        status="active",
        allowed_principals={"owner"},
    )

    result = HybridRetriever(InMemoryKnowledgeRepository([private])).retrieve(
        "restricted", workspace_id="ws-1", principal_id="outsider", top_k=8
    )

    assert result == []
