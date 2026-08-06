from dataclasses import replace

from backend.app.domain.knowledge.retrieval import EvidenceItem


def revoke_document(items: list[EvidenceItem], document_id: str) -> list[EvidenceItem]:
    """Do not delete historical evidence snapshots; block new retrieval immediately."""
    return [replace(item, status="revoked") if item.document_id == document_id else item for item in items]
