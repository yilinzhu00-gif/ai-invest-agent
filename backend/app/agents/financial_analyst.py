"""Financial Analyst Agent for the Phase 2 research graph."""

from __future__ import annotations

from backend.app.agents.research_contracts import AgentFinding
from backend.app.agents.schemas import Citation, ResearchClaim
from backend.app.agents.specialist_utils import citation_ids, number, text

FINANCIAL_ANALYST_PROMPT = """你是一名专业股票分析师。
基于提供的财务数据生成研究观点；每个观点必须引用对应数据来源。
不得补充未提供的数字，不得把缺失字段当作零，不得输出买卖建议。
输出：summary、claims、missing_information、source。"""


class FinancialAnalystAgent:
    """Deterministic default implementation; an LLM adapter may replace it later."""

    role = "financial"
    prompt = FINANCIAL_ANALYST_PROMPT

    def analyze(
        self,
        *,
        symbol: str | None,
        report: dict[str, object] | None,
        evidence: list[Citation],
    ) -> AgentFinding:
        data = report or {}
        label = symbol or text(data.get("symbol"), "目标公司")
        report_period = text(data.get("report_period"), "未知报告期")
        claims: list[ResearchClaim] = []
        missing: list[str] = []
        revenue = number(data.get("revenue"))
        profit = number(data.get("profit"))
        gross_margin = number(data.get("gross_margin"))
        growth = number(data.get("growth_rate"))
        if revenue is not None:
            claims.append(
                ResearchClaim(
                    text=f"{label}在{report_period}的营收为 {revenue:g}。",
                    citation_ids=citation_ids(evidence, keywords=("revenue", "营收", "财报"), fallback="tool:financial_report"),
                    numeric_values=[revenue],
                )
            )
        else:
            missing.append("revenue")
        if profit is not None:
            claims.append(
                ResearchClaim(
                    text=f"{label}在{report_period}的利润为 {profit:g}。",
                    citation_ids=citation_ids(evidence, keywords=("profit", "利润", "净利"), fallback="tool:financial_report"),
                    numeric_values=[profit],
                )
            )
        else:
            missing.append("profit")
        if gross_margin is not None:
            claims.append(
                ResearchClaim(
                    text=f"{label}毛利率为 {gross_margin:g}%。",
                    citation_ids=citation_ids(evidence, keywords=("gross", "毛利"), fallback="tool:financial_report"),
                    numeric_values=[gross_margin],
                )
            )
        else:
            missing.append("gross_margin")
        if growth is not None:
            claims.append(
                ResearchClaim(
                    text=f"{label}增长率为 {growth:g}%。",
                    citation_ids=citation_ids(evidence, keywords=("growth", "增长", "同比"), fallback="tool:financial_report"),
                    numeric_values=[growth],
                )
            )
        else:
            missing.append("growth_rate")
        if not claims:
            missing.append("financial_report")
        summary = (
            f"财务分析覆盖 {len(claims)} 项已提供指标，报告期：{report_period}。"
            if claims
            else "没有足够的财务数据生成观点。"
        )
        return AgentFinding(
            agent="financial",
            summary=summary,
            claims=claims,
            missing_information=list(dict.fromkeys(missing)),
            source=text(data.get("source"), "financial_report input"),
        )


def analyze_financials(
    symbol: str | None,
    report: dict[str, object] | None,
    evidence: list[Citation] | None = None,
) -> AgentFinding:
    return FinancialAnalystAgent().analyze(symbol=symbol, report=report, evidence=evidence or [])
