"""Institutional investment-report contract and deterministic Markdown/PDF renderers."""

from __future__ import annotations

import html
from datetime import date
from enum import Enum
from io import BytesIO

from pydantic import BaseModel, ConfigDict, Field, model_validator
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

INSTITUTIONAL_REPORT_SECTION_TITLES = (
    "Executive Summary",
    "Investment Thesis",
    "Business Overview",
    "Financial Analysis",
    "Industry Analysis",
    "Competitive Landscape",
    "Risk Analysis",
    "Valuation",
    "Bull Case",
    "Bear Case",
    "Conclusion",
)


class ReportExportFormat(str, Enum):
    MARKDOWN = "markdown"
    PDF = "pdf"


class ReportCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=256)
    source: str = Field(min_length=1, max_length=512)
    locator: str = Field(min_length=1, max_length=512)
    excerpt: str = Field(min_length=1, max_length=20_000)
    content: str | None = Field(default=None, max_length=20_000)
    page: int | None = Field(default=None, ge=1)
    date: str | None = Field(default=None, max_length=64)
    source_url: str | None = Field(default=None, max_length=2_048)


class ReportClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=10_000)
    data_support: str = Field(min_length=1, max_length=10_000)
    analysis: str = Field(min_length=1, max_length=10_000)
    citations: list[ReportCitation] = Field(min_length=1, max_length=8)


class InstitutionalReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=64)
    claims: list[ReportClaim] = Field(min_length=1, max_length=8)


class InstitutionalReportContent(BaseModel):
    """A fixed, citation-bearing structure suitable for an institution-style report."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=64)
    data_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    sections: list[InstitutionalReportSection] = Field(
        min_length=len(INSTITUTIONAL_REPORT_SECTION_TITLES),
        max_length=len(INSTITUTIONAL_REPORT_SECTION_TITLES),
    )
    risk_disclaimer: str = Field(
        default="This report is evidence-bound and does not constitute investment advice.",
        min_length=1,
        max_length=2_000,
    )

    @model_validator(mode="after")
    def require_fixed_sections_and_date(self) -> InstitutionalReportContent:
        date.fromisoformat(self.data_date)
        if tuple(section.title for section in self.sections) != INSTITUTIONAL_REPORT_SECTION_TITLES:
            raise ValueError("institutional report sections must use the fixed order")
        return self


class ReportGenerationError(ValueError):
    """A report cannot be generated without at least one cited evidence claim."""


def _citation_label(citation: ReportCitation) -> str:
    location = f"p.{citation.page}" if citation.page is not None else citation.locator
    date_label = f", {citation.date}" if citation.date else ""
    return f"{citation.source} ({location}{date_label})"


def render_report_markdown(content: InstitutionalReportContent) -> str:
    lines = [
        f"# {content.title}",
        "",
        f"Target: {content.target}",
        f"Data date: {content.data_date}",
        "",
    ]
    for section in content.sections:
        lines.extend((f"## {section.title}", ""))
        for claim in section.claims:
            lines.extend(
                (
                    f"### {claim.statement}",
                    "",
                    f"**Data support:** {claim.data_support}",
                    "",
                    f"**Analysis:** {claim.analysis}",
                    "",
                    "**Citations:**",
                )
            )
            lines.extend(f"- {_citation_label(citation)}: {citation.excerpt}" for citation in claim.citations)
            lines.append("")
    lines.extend(("## Risk Disclaimer", content.risk_disclaimer, ""))
    return "\n".join(lines)


def _report_lines(content: InstitutionalReportContent) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = [
        ("title", content.title),
        ("meta", f"Target: {content.target}"),
        ("meta", f"Data date: {content.data_date}"),
    ]
    for section in content.sections:
        lines.append(("heading", section.title))
        for claim in section.claims:
            lines.extend(
                (
                    ("subheading", claim.statement),
                    ("body", f"Data support: {claim.data_support}"),
                    ("body", f"Analysis: {claim.analysis}"),
                )
            )
            lines.extend(
                ("source", f"Citation: {_citation_label(citation)} — {citation.excerpt}")
                for citation in claim.citations
            )
    lines.extend((("heading", "Risk Disclaimer"), ("body", content.risk_disclaimer)))
    return lines


def render_report_pdf(content: InstitutionalReportContent) -> bytes:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("ReportTitle", parent=styles["Title"], fontName="STSong-Light", fontSize=18))
    styles.add(ParagraphStyle("ReportHeading", parent=styles["Heading2"], fontName="STSong-Light", fontSize=13))
    styles.add(ParagraphStyle("ReportSubheading", parent=styles["Heading3"], fontName="STSong-Light", fontSize=11))
    styles.add(ParagraphStyle("ReportBody", parent=styles["BodyText"], fontName="STSong-Light", fontSize=10, leading=15))
    styles.add(ParagraphStyle("ReportMeta", parent=styles["BodyText"], fontName="STSong-Light", fontSize=8.5, leading=12))
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    story = []
    style_by_kind = {
        "title": "ReportTitle",
        "heading": "ReportHeading",
        "subheading": "ReportSubheading",
        "meta": "ReportMeta",
    }
    for kind, text in _report_lines(content):
        story.append(Paragraph(html.escape(text), styles[style_by_kind.get(kind, "ReportBody")]))
        story.append(Spacer(1, 3 * mm if kind in {"title", "heading"} else 1.5 * mm))
    document.build(story)
    return output.getvalue()


def export_report_bytes(
    content: InstitutionalReportContent, export_format: ReportExportFormat
) -> tuple[bytes, str, str]:
    if export_format is ReportExportFormat.MARKDOWN:
        return render_report_markdown(content).encode("utf-8"), "text/markdown; charset=utf-8", "md"
    return render_report_pdf(content), "application/pdf", "pdf"
