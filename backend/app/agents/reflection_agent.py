"""Reflection Agent that checks citations, data completeness and logic gaps."""

from __future__ import annotations

from backend.app.agents.reflection import ReflectionResult, ReflectionScore
from backend.app.agents.research_contracts import AgentFinding, DebateOutput
from backend.app.agents.schemas import Citation
from backend.app.agents.specialist_utils import collect_claims

REFLECTION_AGENT_PROMPT = """你是研究质量审查员。
检查数据错误、逻辑漏洞和缺少引用；逐条核对观点是否引用已有证据。
输出 score：accuracy 0-10、logic 0-10，以及 missing 列表。证据不足时降低分数，不能自动补齐事实。"""


class ReflectionAgent:
    role = "reflection"
    prompt = REFLECTION_AGENT_PROMPT

    def run(
        self,
        *,
        findings: list[AgentFinding],
        debate: DebateOutput,
        evidence: list[Citation],
    ) -> ReflectionResult:
        known = {item.id for item in evidence}
        claims = collect_claims(findings)
        missing: list[str] = list(debate.data_gaps)
        issues: list[str] = []
        supported = 0
        for claim in claims:
            valid_ids = [identifier for identifier in claim.citation_ids if identifier in known or identifier.startswith("tool:")]
            if valid_ids:
                supported += 1
            else:
                issues.append(f"缺少引用：{claim.text[:80]}")
                missing.append("citation")
            if valid_ids and not any(identifier.startswith("tool:") for identifier in valid_ids):
                cited_text = " ".join(item.text for item in evidence if item.id in valid_ids)
                for value in claim.numeric_values:
                    if format(value, "g") not in cited_text:
                        issues.append(f"数字未在引用中出现：{value:g}")
                        missing.append("numeric_citation")
        if not claims:
            issues.append("没有 specialist 观点可供复核")
            missing.append("specialist_findings")
        if not debate.bull.evidence_ids or not debate.bear.evidence_ids:
            issues.append("多空一方缺少证据引用")
            missing.append("debate_evidence")
        missing = list(dict.fromkeys(missing))
        accuracy = round((supported / len(claims)) * 10) if claims else 0
        logic = max(0, 10 - min(7, len(missing)))
        accepted = bool(claims) and not issues and accuracy >= 8 and logic >= 7
        return ReflectionResult(
            accepted=accepted,
            issues=tuple(issues),
            confidence=round(min(1.0, accuracy / 10), 2),
            accuracy=accuracy,
            logic=logic,
            missing=tuple(missing),
            score=ReflectionScore(accuracy=accuracy, logic=logic, missing=tuple(missing)),
        )


def reflect(
    findings: list[AgentFinding], debate: DebateOutput, evidence: list[Citation] | None = None
) -> ReflectionResult:
    return ReflectionAgent().run(findings=findings, debate=debate, evidence=evidence or [])
