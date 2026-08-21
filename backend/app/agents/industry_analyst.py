"""Industry Analyst Agent for trends, competition and market space."""

from __future__ import annotations

from backend.app.agents.research_contracts import AgentFinding
from backend.app.agents.schemas import Citation, ResearchClaim
from backend.app.agents.specialist_utils import citation_ids, number, text

INDUSTRY_ANALYST_PROMPT = """你是一名行业研究分析师。
分析行业趋势、竞争格局和市场空间；每条观点必须引用提供的新闻、搜索或行业数据。
不得把搜索摘要当作经过核实的事实，不得补充未提供的数字，不得输出买卖建议。"""


class IndustryAnalystAgent:
    role = "industry"
    prompt = INDUSTRY_ANALYST_PROMPT

    def analyze(
        self,
        *,
        symbol: str | None,
        data: dict[str, object] | None,
        evidence: list[Citation],
    ) -> AgentFinding:
        payload = data or {}
        label = symbol or text(payload.get("company"), "目标公司")
        claims: list[ResearchClaim] = []
        missing: list[str] = []

        trend = text(payload.get("trend"))
        if trend:
            claims.append(
                ResearchClaim(
                    text=f"行业趋势：{trend}",
                    citation_ids=citation_ids(evidence, keywords=("industry", "行业", "trend", "趋势"), fallback="tool:industry_search"),
                )
            )
        else:
            missing.append("industry_trend")

        competition = text(payload.get("competition"))
        if competition:
            claims.append(
                ResearchClaim(
                    text=f"竞争格局：{competition}",
                    citation_ids=citation_ids(evidence, keywords=("competition", "竞争", "同行"), fallback="tool:industry_search"),
                )
            )
        else:
            missing.append("competition_landscape")

        market_size = number(payload.get("market_size"))
        if market_size is not None:
            unit = text(payload.get("market_size_unit"), "")
            claims.append(
                ResearchClaim(
                    text=f"{label}所在市场规模为 {market_size:g}{unit}。",
                    citation_ids=citation_ids(evidence, keywords=("market size", "市场空间", "市场规模"), fallback="tool:industry_search"),
                    numeric_values=[market_size],
                )
            )
        else:
            missing.append("market_size")

        return AgentFinding(
            agent="industry",
            summary=f"行业分析覆盖 {len(claims)} 项趋势、竞争或市场空间信息。",
            claims=claims,
            missing_information=list(dict.fromkeys(missing)),
            source=text(payload.get("source"), "industry_data input"),
        )


def analyze_industry(
    symbol: str | None,
    data: dict[str, object] | None,
    evidence: list[Citation] | None = None,
) -> AgentFinding:
    return IndustryAnalystAgent().analyze(symbol=symbol, data=data, evidence=evidence or [])

