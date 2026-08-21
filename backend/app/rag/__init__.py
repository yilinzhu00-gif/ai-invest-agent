"""Retrieval-augmented generation boundaries.

PostgreSQL/pgvector is the selected production vector store in this checkout;
the adapter remains replaceable by Chroma or Milvus later.
"""

from backend.app.domain.knowledge.retrieval import EvidenceItem, HybridRetriever
from backend.app.rag.embedding import (
    EmbeddingError,
    EmbeddingProvider,
    HashEmbeddingProvider,
    OpenAIEmbeddingProvider,
    cosine_similarity,
    embed_text,
    embed_texts,
)
from backend.app.rag.loader import DocumentChunk, load_document, load_documents
from backend.app.rag.retriever import InMemoryVectorStore, RAGRetriever, RetrievedChunk

__all__ = [
    "DocumentChunk",
    "EmbeddingError",
    "EmbeddingProvider",
    "EvidenceItem",
    "HashEmbeddingProvider",
    "HybridRetriever",
    "InMemoryVectorStore",
    "OpenAIEmbeddingProvider",
    "RAGRetriever",
    "RetrievedChunk",
    "cosine_similarity",
    "embed_text",
    "embed_texts",
    "load_document",
    "load_documents",
]
