"""Workspace-aware dense retrieval over loaded financial document chunks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from backend.app.rag.embedding import (
    EmbeddingProvider,
    HashEmbeddingProvider,
    cosine_similarity,
    embed_text,
    embed_texts,
)
from backend.app.rag.loader import DocumentChunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float

    @property
    def citation(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk.id,
            "source": self.chunk.source_path,
            "page_number": self.chunk.page_number,
            "document_type": self.chunk.document_type,
            "symbol": self.chunk.symbol,
            "text": self.chunk.text,
            "score": round(self.score, 6),
        }


class InMemoryVectorStore:
    """A deterministic store for local development and retrieval evaluation.

    Production persistence remains PostgreSQL/pgvector (already represented by
    the migration); this class provides the same citation and ACL contract
    without requiring a database or a networked model.
    """

    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self.provider = cast(EmbeddingProvider, provider or HashEmbeddingProvider())
        self._rows: dict[str, tuple[DocumentChunk, list[float]]] = {}

    def add(self, chunks: Iterable[DocumentChunk]) -> int:
        items = list(chunks)
        vectors = embed_texts([item.text for item in items], provider=self.provider)
        for chunk, vector in zip(items, vectors):
            self._rows[chunk.id] = (chunk, vector)
        return len(items)

    def clear(self) -> None:
        self._rows.clear()

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        document_types: set[str] | None = None,
        symbol: str | None = None,
        workspace_id: str | None = None,
        principal_id: str | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip() or top_k < 1:
            return []
        query_vector = embed_text(query, provider=self.provider)
        candidates = (
            (chunk, vector)
            for chunk, vector in self._rows.values()
            if (document_types is None or chunk.document_type in document_types)
            and (symbol is None or chunk.symbol == symbol)
            and (workspace_id is None or chunk.workspace_id == workspace_id)
            and (
                not chunk.allowed_principals
                or (principal_id is not None and principal_id in chunk.allowed_principals)
            )
        )
        ranked = [RetrievedChunk(chunk, cosine_similarity(query_vector, vector)) for chunk, vector in candidates]
        return sorted(ranked, key=lambda result: (-result.score, result.chunk.id))[:top_k]


class RAGRetriever:
    """Index + retrieve facade used by ingestion workers and Agent adapters."""

    def __init__(self, store: InMemoryVectorStore | None = None) -> None:
        self.store = store or InMemoryVectorStore()

    def index(self, chunks: Iterable[DocumentChunk]) -> int:
        return self.store.add(chunks)

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        document_types: set[str] | None = None,
        symbol: str | None = None,
        workspace_id: str | None = None,
        principal_id: str | None = None,
    ) -> list[RetrievedChunk]:
        return self.store.search(
            query,
            top_k=top_k,
            document_types=document_types,
            symbol=symbol,
            workspace_id=workspace_id,
            principal_id=principal_id,
        )

    def context(self, query: str, *, top_k: int = 5, symbol: str | None = None) -> str:
        """Render retrieved excerpts for a model prompt without losing citations."""

        results = self.retrieve(query, top_k=top_k, symbol=symbol)
        return "\n\n".join(
            f"[{result.chunk.id} | {result.chunk.source_path} | p.{result.chunk.page_number}]\n{result.chunk.text}"
            for result in results
        )


__all__ = ["InMemoryVectorStore", "RAGRetriever", "RetrievedChunk"]
