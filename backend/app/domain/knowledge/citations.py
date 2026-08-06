from dataclasses import dataclass

from backend.app.domain.knowledge.retrieval import EvidenceItem


@dataclass(frozen=True)
class EvidenceCitation:
    evidence_id: str
    document_id: str
    document_version: int
    page_number: int
    block_id: str
    table_id: str | None
    cells: list[dict[str, object]]
    bbox: list[float] | None


def render_citation(item: EvidenceItem) -> EvidenceCitation:
    return EvidenceCitation(item.id, item.document_id, item.document_version, item.page_number, item.block_id, item.table_id, item.cell_refs, item.bbox)
