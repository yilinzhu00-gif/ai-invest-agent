from backend.app.domain.knowledge.citations import render_citation
from backend.app.domain.knowledge.lifecycle import revoke_document
from backend.app.domain.knowledge.retrieval import (
    EvidenceItem,
    HybridRetriever,
    InMemoryKnowledgeRepository,
)


def item(*, id: str, workspace_id: str = "ws-1", status: str = "active") -> EvidenceItem:
    return EvidenceItem(
        id=id,
        workspace_id=workspace_id,
        document_id="doc-1",
        document_version=2,
        page_number=3,
        block_id="block-1",
        text="营收下降 12.5%",
        status=status,
        keyword_score=0.8,
        dense_score=0.7,
        table_id="table-1",
        cell_refs=[{"row": 1, "column": 1, "text": "-12.5%", "unit": "%"}],
        bbox=[0, 0, 10, 10],
    )


def test_retrieval_filters_acl_and_revoked_before_rrf() -> None:
    repository = InMemoryKnowledgeRepository([item(id="allowed"), item(id="other", workspace_id="ws-2"), item(id="revoked", status="revoked")])

    evidence = HybridRetriever(repository).retrieve("营收", workspace_id="ws-1", principal_id="analyst", top_k=8)

    assert [entry.id for entry in evidence] == ["allowed"]
    assert evidence[0].rrf_score > 0


def test_citation_keeps_exact_document_version_page_and_table_cell() -> None:
    citation = render_citation(item(id="allowed"))

    assert citation.document_id == "doc-1"
    assert citation.document_version == 2
    assert citation.page_number == 3
    assert citation.cells[0]["text"] == "-12.5%"


def test_revoked_document_is_not_retrievable() -> None:
    repository = InMemoryKnowledgeRepository(revoke_document([item(id="allowed")], "doc-1"))

    assert HybridRetriever(repository).retrieve("营收", workspace_id="ws-1", principal_id="analyst", top_k=8) == []
