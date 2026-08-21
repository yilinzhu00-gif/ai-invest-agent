"""Market Analyst Agent for price trend, technical indicators and sentiment."""

from __future__ import annotations

from backend.app.agents.research_contracts import AgentFinding
from backend.app.agents.schemas import Citation, ResearchClaim
from backend.app.agents.specialist_utils import citation_ids, number, text

MARKET_ANALYST_PROMPT = """你是一名市场分析师。
分析提供的股价趋势、技术指标和市场情绪；每条观点必须引用行情或情绪数据。
只描述已观测数据，不预测未来走势，不输出买卖建议。"""


class MarketAnalystAgent:
    role = "market"
    prompt = MARKET_ANALYST_PROMPT

    def analyze(
        self,
        *,
        symbol: str | None,
        stock_data: dict[str, object] | None,
        market_data: dict[str, object] | None,
        evidence: list[Citation],
    ) -> AgentFinding:
        stock = stock_data or {}
        sentiment = market_data or {}
        label = symbol or text(stock.get("symbol"), "目标公司")
        claims: list[ResearchClaim] = []
        missing: list[str] = []
        price = number(stock.get("price"))
        change = number(stock.get("change_percent"))
        pe = number(stock.get("pe"))
        rsi = number(stock.get("rsi"))
        if rsi is None and market_data:
            rsi = number(market_data.get("rsi"))
        ma_20 = number(stock.get("ma_20"))
        if ma_20 is None and market_data:
            ma_20 = number(market_data.get("ma_20"))
        if price is not None:
            claims.append(
                ResearchClaim(
                    text=f"{label}当前观测价格为 {price:g}。",
                    citation_ids=citation_ids(evidence, keywords=("price", "行情", "quote"), fallback="tool:stock_price"),
                    numeric_values=[price],
                )
            )
        else:
            missing.append("price")
        if change is not None:
            claims.append(
                ResearchClaim(
                    text=f"{label}观测区间涨跌幅为 {change:g}%。",
                    citation_ids=citation_ids(evidence, keywords=("change", "涨跌", "return"), fallback="tool:stock_price"),
                    numeric_values=[change],
                )
            )
        else:
            missing.append("price_trend")
        if pe is not None:
            claims.append(
                ResearchClaim(
                    text=f"{label}当前 PE 观测值为 {pe:g}。",
                    citation_ids=citation_ids(evidence, keywords=("pe", "估值", "valuation"), fallback="tool:stock_price"),
                    numeric_values=[pe],
                )
            )
        else:
            missing.append("valuation_data")
        if rsi is not None:
            claims.append(
                ResearchClaim(
                    text=f"{label} RSI 观测值为 {rsi:g}。",
                    citation_ids=citation_ids(evidence, keywords=("rsi", "技术", "technical"), fallback="tool:stock_price"),
                    numeric_values=[rsi],
                )
            )
        else:
            missing.append("technical_indicators")
        if ma_20 is not None:
            claims.append(
                ResearchClaim(
                    text=f"{label} 20 日均线观测值为 {ma_20:g}。",
                    citation_ids=citation_ids(evidence, keywords=("moving average", "均线", "technical"), fallback="tool:stock_price"),
                    numeric_values=[ma_20],
                )
            )
        sentiment_text = text(sentiment.get("sentiment"))
        if sentiment_text:
            claims.append(
                ResearchClaim(
                    text=f"市场情绪观测：{sentiment_text}",
                    citation_ids=citation_ids(evidence, keywords=("sentiment", "情绪", "新闻"), fallback="tool:market_sentiment"),
                )
            )
        else:
            missing.append("market_sentiment")
        return AgentFinding(
            agent="market",
            summary=f"市场分析覆盖 {len(claims)} 项价格、趋势、估值或情绪观测。",
            claims=claims,
            missing_information=list(dict.fromkeys(missing)),
            source=text(stock.get("source") or sentiment.get("source"), "market_data input"),
        )


def analyze_market(
    symbol: str | None,
    stock_data: dict[str, object] | None,
    market_data: dict[str, object] | None = None,
    evidence: list[Citation] | None = None,
) -> AgentFinding:
    return MarketAnalystAgent().analyze(
        symbol=symbol,
        stock_data=stock_data,
        market_data=market_data,
        evidence=evidence or [],
    )
