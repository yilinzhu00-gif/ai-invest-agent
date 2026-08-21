import pytest
from pydantic import ValidationError

from backend.app.agents.report_agent import ReportAgent
from backend.app.agents.schemas import Citation, ResearchClaim, ResearchDraft
from backend.app.domain.agent_runs.institutional_report import (
    INSTITUTIONAL_REPORT_SECTION_TITLES,
    InstitutionalReportContent,
    ReportExportFormat,
    export_report_bytes,
)


def _report():
    citation = Citation(
        id="c1",
        source="financial-report.pdf",
        locator="page=3; block=2",
        text="Revenue was 100 and gross margin was 40%.",
    )
    draft = ResearchDraft(
        summary="Evidence-backed summary.",
        claims=[ResearchClaim(text="Revenue was 100.", citation_ids=["c1"], numeric_values=[100])],
    )
    return ReportAgent().generate(target="NVDA", draft=draft, evidence=[citation])


def test_report_agent_generates_all_institutional_sections_with_citations() -> None:
    report = _report()

    assert tuple(section.title for section in report.sections) == INSTITUTIONAL_REPORT_SECTION_TITLES
    assert all(claim.citations for section in report.sections for claim in section.claims)
    assert report.sections[0].claims[0].citations[0].content == "Revenue was 100 and gross margin was 40%."
    markdown, media_type, extension = export_report_bytes(report, ReportExportFormat.MARKDOWN)
    assert media_type.startswith("text/markdown")
    assert extension == "md"
    assert b"## Executive Summary" in markdown
    assert b"## Valuation" in markdown
    pdf, pdf_media_type, pdf_extension = export_report_bytes(report, ReportExportFormat.PDF)
    assert pdf.startswith(b"%PDF")
    assert pdf_media_type == "application/pdf"
    assert pdf_extension == "pdf"


def test_report_schema_rejects_a_section_without_evidence() -> None:
    report = _report().model_dump(mode="json")
    report["sections"][0]["claims"][0]["citations"] = []
    with pytest.raises(ValidationError):
        InstitutionalReportContent.model_validate(report)
