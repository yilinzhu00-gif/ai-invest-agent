from io import BytesIO

from docx import Document
from pypdf import PdfReader

from backend.app.domain.agent_runs.research_brief import (
    BriefCitation,
    BriefClaim,
    BriefExportFormat,
    BriefSection,
    ResearchBriefContent,
    ResearchBriefVersion,
    content_sha256,
    export_bytes,
    render_markdown,
)


def _version() -> ResearchBriefVersion:
    citation = BriefCitation(
        evidence_id="document:31:block:7",
        filename="收购报告书.pdf",
        document_version=2,
        page_number=8,
        block_id="7",
    )
    content = ResearchBriefContent(
        title="甲公司收购交易研究简报",
        summary="交易对价为 10 亿元，需结合后续市场数据继续审核。",
        data_date="2026-08-18",
        sections=[
            BriefSection(title="已证实的交易事实", claims=[BriefClaim(text="交易对价为 10 亿元。", citations=[citation])]),
            BriefSection(title="公告后的市场反应", claims=[]),
            BriefSection(title="可能的影响机制", claims=[]),
            BriefSection(title="正面因素", claims=[]),
            BriefSection(title="风险和不确定性", claims=[]),
        ],
        missing_information=["公告后市场反应的完整窗口数据。"],
        confidence="low",
        confidence_rationale="关键结论仅有一处公告原文引用。",
        risk_disclaimer="本简报不构成投资建议。",
    )
    return ResearchBriefVersion(version=3, content=content, content_sha256=content_sha256(content))


def test_all_exports_are_rendered_from_the_same_saved_snapshot() -> None:
    version = _version()
    markdown = render_markdown(version)
    docx_bytes, docx_type, _ = export_bytes(version, BriefExportFormat.DOCX)
    pdf_bytes, pdf_type, _ = export_bytes(version, BriefExportFormat.PDF)

    assert docx_type.startswith("application/vnd.openxmlformats-officedocument")
    assert pdf_type == "application/pdf"
    assert pdf_bytes.startswith(b"%PDF-")
    for expected in (
        "交易对价为 10 亿元。",
        "收购报告书.pdf · v2 · 第 8 页 · 块 7",
        "数据日期：2026-08-18",
        version.content_sha256,
        "本简报不构成投资建议。",
    ):
        assert expected in markdown

    docx_text = "\n".join(paragraph.text for paragraph in Document(BytesIO(docx_bytes)).paragraphs)
    for expected in ("交易对价为 10 亿元。", "数据日期：2026-08-18", version.content_sha256):
        assert expected in docx_text

    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages)
    assert "2026-08-18" in pdf_text
    assert version.content_sha256 in pdf_text


def test_content_fingerprint_changes_when_the_researcher_changes_a_number() -> None:
    version = _version()
    changed = version.content.model_copy(
        update={"summary": "交易对价为 11 亿元，需结合后续市场数据继续审核。"}
    )

    assert content_sha256(changed) != version.content_sha256
