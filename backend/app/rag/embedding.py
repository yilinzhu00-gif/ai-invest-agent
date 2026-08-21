"""Embedding providers used by the RAG boundary.

``HashEmbeddingProvider`` keeps local development and offline evaluation
network-free.  ``OpenAIEmbeddingProvider`` is an explicit opt-in adapter for
production; callers own the client and credentials, so secrets never enter an
index or a chunk object.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class EmbeddingProvider(Protocol):
    dimension: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class EmbeddingError(RuntimeError):
    """Raised when a remote embedding provider cannot produce a result."""


@dataclass(frozen=True)
class HashEmbeddingProvider:
    """Deterministic signed feature hashing baseline; no model or network."""

    dimension: int = 1536

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_hash_embedding(text, self.dimension) for text in texts]


class OpenAIEmbeddingProvider:
    """Small adapter around an OpenAI-compatible client.

    The client only needs ``embeddings.create(model=..., input=...)``; this
    keeps the adapter compatible with the installed OpenAI SDK and test fakes.
    """

    def __init__(self, client: object, *, model: str = "text-embedding-3-small", dimension: int = 1536) -> None:
        self.client = client
        self.model = model
        self.dimension = dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self.client.embeddings.create(model=self.model, input=list(texts))  # type: ignore[attr-defined]
            data = sorted(response.data, key=lambda item: item.index)
            vectors = [list(map(float, item.embedding)) for item in data]
        except Exception as error:
            raise EmbeddingError("embedding provider request failed") from error
        if len(vectors) != len(texts) or any(len(vector) != self.dimension for vector in vectors):
            raise EmbeddingError("embedding provider returned an invalid vector shape")
        return [_unit_normalize(vector) for vector in vectors]


def embed_text(text: str, provider: EmbeddingProvider | None = None) -> list[float]:
    """Embed one string using the offline-safe default provider."""

    return embed_texts([text], provider=provider)[0]


def embed_texts(texts: Sequence[str], provider: EmbeddingProvider | None = None) -> list[list[float]]:
    if any(not isinstance(text, str) for text in texts):
        raise TypeError("texts must contain strings")
    return (provider or HashEmbeddingProvider()).embed(texts)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimension")
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if not denominator:
        return 0.0
    # Floating-point accumulation can produce 1.0000000000000002 for two
    # identical unit vectors; cosine similarity is mathematically bounded.
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right)) / denominator))


def _hash_embedding(text: str, dimension: int) -> list[float]:
    if dimension < 1:
        raise ValueError("dimension must be positive")
    vector = [0.0] * dimension
    terms = _tokens(text)
    for term in terms:
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimension
        sign = 1.0 if digest[8] & 1 else -1.0
        vector[index] += sign
    return _unit_normalize(vector)


def _tokens(text: str) -> list[str]:
    """Keep words intact while adding CJK character n-grams for Chinese queries."""

    tokens: list[str] = []
    for term in re.findall(r"[\w]+|[^\s\w]", text.casefold(), flags=re.UNICODE):
        tokens.append(term)
        if any("\u4e00" <= char <= "\u9fff" for char in term) and len(term) > 1:
            tokens.extend(term[index : index + 2] for index in range(len(term) - 1))
    return tokens


def _unit_normalize(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return [float(value / norm) for value in vector] if norm else [0.0 for _ in vector]


__all__ = [
    "EmbeddingError",
    "EmbeddingProvider",
    "HashEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "cosine_similarity",
    "embed_text",
    "embed_texts",
]
