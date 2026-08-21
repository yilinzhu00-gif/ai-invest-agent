"""Bull/Bear/Moderator Agent for the Phase 2 graph."""

from __future__ import annotations

from backend.app.agents.debate import DebatePosition
from backend.app.agents.research_contracts import AgentFinding, DebateOutput
from backend.app.agents.specialist_utils import collect_claims

DEBATE_AGENT_PROMPT = """你是中立的多空辩论主持人。
Bull 只陈述为什么基本面、行业或市场数据可能支持积极观点；Bear 只陈述风险和反证。
Moderator 总结共识、分歧和需要补证的事项。三方都必须引用已有 evidence_ids，禁止买卖建议、目标价和仓位。"""


class DebateAgent:
    role = "debate"
    prompt = DEBATE_AGENT_PROMPT

    def run(
        self,
        *,
        findings: list[AgentFinding],
    ) -> DebateOutput:
        claims = collect_claims(findings)
        evidence_ids = tuple(dict.fromkeys(identifier for claim in claims for identifier in claim.citation_ids))
        if claims:
            bull_source = claims[0]
            bear_source = claims[-1]
            bull = DebatePosition(
                side="bull",
                claim=f"支持方：{bull_source.text}",
                evidence_ids=tuple(bull_source.citation_ids),
            )
            bear = DebatePosition(
                side="bear",
                claim=f"风险方：{bear_source.text}",
                evidence_ids=tuple(bear_source.citation_ids),
            )
            moderator_claim = "共识与分歧需要结合全部引用逐条复核，当前不形成交易结论。"
        else:
            bull = DebatePosition(side="bull", claim="缺少可支持积极观点的研究证据。", evidence_ids=())
            bear = DebatePosition(side="bear", claim="缺少足够数据识别风险和反证。", evidence_ids=())
            moderator_claim = "当前没有可供辩论的事实证据。"
        gaps = list(dict.fromkeys(gap for finding in findings for gap in finding.missing_information))
        moderator = DebatePosition(
            side="moderator",
            claim=moderator_claim,
            evidence_ids=evidence_ids[:8],
        )
        return DebateOutput(bull=bull, bear=bear, moderator=moderator, data_gaps=gaps)


def run_debate(findings: list[AgentFinding]) -> DebateOutput:
    return DebateAgent().run(findings=findings)
