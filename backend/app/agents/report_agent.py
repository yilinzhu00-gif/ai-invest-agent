"""Evidence-bound Report Agent that expands validated findings into a fixed report."""

from datetime import UTC, datetime

from backend.app.agents.schemas import Citation, ResearchDraft
from backend.app.domain.agent_runs.institutional_report import (
    INSTITUTIONAL_REPORT_SECTION_TITLES,
    InstitutionalReportContent,
    InstitutionalReportSection,
    ReportCitation,
    ReportClaim,
    ReportGenerationError,
)


class ReportAgent:
    """Build a professional structure without inventing unsupported facts."""

    def generate(
        self,
        *,
        target: str,
        draft: ResearchDraft,
        evidence: list[Citation],
        title: str | None = None,
    ) -> InstitutionalReportContent:
        evidence_by_id = {citation.id: citation for citation in evidence}
        reportable_ids = {
            citation.id
            for citation in evidence
            if citation.source not in {"development-executor", "worker-run-input", "celery-worker"}
            and citation.locator != "run-question"
        }
        source_claims = [
            claim
            for claim in draft.claims
            if any(citation_id in reportable_ids for citation_id in claim.citation_ids)
        ]
        if not source_claims:
            raise ReportGenerationError("report requires at least one evidence-backed claim")

        def make_claim(section_title: str, index: int) -> ReportClaim:
            claim = source_claims[index % len(source_claims)]
            citations = [
                ReportCitation(
                    evidence_id=citation_id,
                    source=evidence_by_id[citation_id].source,
                    locator=evidence_by_id[citation_id].locator,
                    # Keep the report event bounded while retaining the
                    # source locator for the full evidence record.
                    excerpt=evidence_by_id[citation_id].text[:4_000],
                    content=(evidence_by_id[citation_id].content or evidence_by_id[citation_id].text)[:20_000],
                    page=evidence_by_id[citation_id].page,
                    date=evidence_by_id[citation_id].date,
                    source_url=evidence_by_id[citation_id].source_url,
                )
                for citation_id in claim.citation_ids
                if citation_id in reportable_ids
            ]
            if not citations:
                raise ReportGenerationError("report claim lost its evidence citation")
            return ReportClaim(
                statement=draft.summary if section_title == "Executive Summary" else claim.text,
                data_support="；".join(citation.excerpt for citation in citations),
                analysis=(
                    f"{section_title}仅基于已列数据进行审慎解释；"
                    "未披露的事实、预测和估值参数不作补全。"
                ),
                citations=citations,
            )

        sections = [
            InstitutionalReportSection(
                title=section_title,
                claims=[make_claim(section_title, index)],
            )
            for index, section_title in enumerate(INSTITUTIONAL_REPORT_SECTION_TITLES)
        ]
        return InstitutionalReportContent(
            title=title or f"{target} Institutional Research Report",
            target=target,
            data_date=datetime.now(UTC).date().isoformat(),
            sections=sections,
        )
