from uuid import UUID

from backend.app.agents.schemas import ResearchClaim
from backend.app.domain.agent_runs.document_research import (
    document_evidence,
    document_result_payload,
    insufficient_evidence_payload,
)
from backend.app.domain.knowledge.schemas import EvidenceSearchResult


def _result() -> EvidenceSearchResult:
    return EvidenceSearchResult(
        evidence_id="document:00000000-0000-0000-0000-000000000031:block:7",
        document_id=UUID("00000000-0000-0000-0000-000000000031"),
        document_version=2,
        filename="收购报告书.pdf",
        source_url=None,
        page_number=8,
        block_id="7",
        text="本次交易对价为 10 亿元。",
        parser="native",
        confidence=1,
        bbox=None,
    )


def test_document_result_preserves_the_exact_version_page_and_block_for_each_claim() -> None:
    evidence = document_evidence([_result()])

    payload = document_result_payload(
        summary="已找到直接证据。",
        claims=[ResearchClaim(text="本次交易对价为 10 亿元。", citation_ids=[evidence[0].citation.id])],
        evidence=evidence,
    )

    citation = payload["claims"][0]["citations"][0]  # type: ignore[index]
    assert citation == {
        "evidence_id": "document:00000000-0000-0000-0000-000000000031:block:7",
        "filename": "收购报告书.pdf",
        "document_version": 2,
        "page_number": 8,
        "block_id": "7",
    }


def test_insufficient_document_evidence_has_no_claims() -> None:
    payload = insufficient_evidence_payload(UUID("00000000-0000-0000-0000-000000000031"))

    assert payload["status"] == "insufficient_evidence"
    assert payload["claims"] == []
    assert "未生成结论" in payload["summary"]
