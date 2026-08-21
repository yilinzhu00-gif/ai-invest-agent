"""Translate retrieved document blocks into durable, page-locatable Run evidence."""

from dataclasses import dataclass
from uuid import UUID

from backend.app.agents.schemas import Citation, ResearchClaim, ResearchConclusion
from backend.app.domain.knowledge.schemas import EvidenceSearchResult


@dataclass(frozen=True)
class DocumentEvidence:
    citation: Citation
    filename: str
    document_version: int
    page_number: int
    block_id: str


def document_evidence(results: list[EvidenceSearchResult]) -> list[DocumentEvidence]:
    return [
        DocumentEvidence(
            citation=Citation(
                id=result.evidence_id,
                source=result.filename,
                locator=(
                    f"document_id={result.document_id}; version={result.document_version}; "
                    f"page={result.page_number}; block={result.block_id}"
                ),
                text=result.text,
                content=result.content,
                page=result.page,
                date=result.date,
                source_url=result.source_url,
            ),
            filename=result.filename,
            document_version=result.document_version,
            page_number=result.page_number,
            block_id=result.block_id,
        )
        for result in results
    ]


def _claim_payload(claim: ResearchClaim, by_id: dict[str, DocumentEvidence]) -> dict[str, object]:
    return {
        "text": claim.text,
        "citations": [
            {
                "evidence_id": citation_id,
                "filename": by_id[citation_id].filename,
                "document_version": by_id[citation_id].document_version,
                "page_number": by_id[citation_id].page_number,
                "block_id": by_id[citation_id].block_id,
            }
            for citation_id in claim.citation_ids
            if citation_id in by_id
        ],
    }


def _conclusion_payload(
    conclusion: ResearchConclusion, by_id: dict[str, DocumentEvidence]
) -> dict[str, object]:
    sections = (
        ("已证实的交易事实", conclusion.confirmed_transaction_facts),
        ("公告后的市场反应", conclusion.post_announcement_market_reaction),
        ("可能的影响机制", conclusion.possible_impact_mechanisms),
        ("正面因素", conclusion.positive_factors),
        ("风险和不确定性", conclusion.risks_and_uncertainties),
    )
    return {
        "sections": [
            {"title": title, "claims": [_claim_payload(claim, by_id) for claim in claims]}
            for title, claims in sections
        ],
        "missing_information": list(conclusion.missing_information),
        "confidence": conclusion.confidence.value,
        "confidence_rationale": conclusion.confidence_rationale,
    }


def document_result_payload(
    *,
    summary: str,
    claims: list[ResearchClaim],
    evidence: list[DocumentEvidence],
    conclusion: ResearchConclusion | None = None,
    status: str = "supported",
) -> dict[str, object]:
    by_id = {item.citation.id: item for item in evidence}
    return {
        "status": status,
        "summary": summary,
        "claims": [_claim_payload(claim, by_id) for claim in claims],
        "conclusion": _conclusion_payload(conclusion, by_id) if conclusion is not None else None,
        "boundary": "每条结论仅整理所列公告文本；未检索到的事实不作推断。",
    }


def insufficient_evidence_payload(
    document_id: UUID,
    *,
    summary: str = "证据不足：所选文档中未找到可直接支持该问题的文本，未生成结论。",
) -> dict[str, object]:
    return {
        "status": "insufficient_evidence",
        "document_id": str(document_id),
        "summary": summary,
        "claims": [],
        "conclusion": None,
        "boundary": "系统未以行情、记忆或常识替代公告证据。",
    }
