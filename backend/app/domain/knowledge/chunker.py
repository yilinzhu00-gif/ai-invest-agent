from backend.app.ingestion.normalizer import normalize_retrieval_text


def chunk_text(text: str, *, max_characters: int = 800, overlap: int = 100) -> list[str]:
    """Deterministic semantic-block fallback with a bounded overlap."""
    normalized = normalize_retrieval_text(text)
    if not normalized:
        return []
    return [normalized[start : start + max_characters] for start in range(0, len(normalized), max_characters - overlap)]
