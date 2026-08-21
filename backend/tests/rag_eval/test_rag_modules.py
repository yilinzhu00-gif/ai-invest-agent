from pathlib import Path

from backend.app.rag.embedding import HashEmbeddingProvider, cosine_similarity, embed_text
from backend.app.rag.loader import load_document
from backend.app.rag.retriever import RAGRetriever


def test_loader_preserves_source_hash_page_and_financial_metadata(tmp_path: Path) -> None:
    source = tmp_path / "nvidia-annual-report.md"
    source.write_text("收入增长。\n\n生态和软件开发者网络形成转换成本。", encoding="utf-8")

    chunks = load_document(
        source,
        document_type="research_report",
        symbol="NVDA",
        workspace_id="workspace-a",
        max_characters=30,
        overlap=5,
    )

    assert chunks
    assert all(chunk.page_number == 1 for chunk in chunks)
    assert all(chunk.document_type == "research_report" for chunk in chunks)
    assert all(chunk.workspace_id == "workspace-a" for chunk in chunks)
    assert chunks[0].source_sha256


def test_hash_embedding_is_deterministic_and_unit_normalized() -> None:
    provider = HashEmbeddingProvider(dimension=32)
    first = embed_text("护城河", provider)
    second = embed_text("护城河", provider)

    assert first == second
    assert cosine_similarity(first, second) == 1.0


def test_retriever_filters_workspace_acl_and_returns_citations() -> None:
    retriever = RAGRetriever()
    from backend.app.rag.loader import DocumentChunk

    retriever.index(
        [
            DocumentChunk(
                id="allowed",
                text="软件生态与开发者网络带来护城河",
                source_path="annual.pdf",
                source_sha256="a",
                page_number=12,
                document_type="research_report",
                workspace_id="workspace-a",
                allowed_principals=frozenset({"analyst"}),
            ),
            DocumentChunk(
                id="private",
                text="护城河来自客户锁定",
                source_path="private.pdf",
                source_sha256="b",
                page_number=4,
                workspace_id="workspace-b",
                allowed_principals=frozenset({"analyst"}),
            ),
        ]
    )

    result = retriever.retrieve(
        "为什么护城河强",
        workspace_id="workspace-a",
        principal_id="analyst",
        top_k=5,
    )

    assert [item.chunk.id for item in result] == ["allowed"]
    assert result[0].citation["page_number"] == 12
