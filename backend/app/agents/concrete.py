"""Concrete, evidence-bounded implementations for the three research roles."""

import json
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import ValidationError

from backend.app.agents.analyst import ResearchAnalyst
from backend.app.agents.reviewer import EvidenceReviewer as EvidenceReviewerProtocol
from backend.app.agents.schemas import (
    Citation,
    ClaimCitationReview,
    ConclusionConfidence,
    ResearchClaim,
    ResearchConclusion,
    ResearchDraft,
    ResearchRequest,
    ReviewDecision,
    ReviewVerdict,
)
from backend.app.models.gateway import enforce_budget
from backend.app.models.schemas import ModelMessage, ModelRequest, ModelResponse, ModelUsage


class CompletionGateway(Protocol):
    async def complete(self, request: ModelRequest, timeout_seconds: float) -> ModelResponse: ...


@dataclass
class RunUsageLedger:
    """Shared per-run budget across the Analyst and Reviewer model calls."""

    max_tokens: int
    max_cost_microusd: int
    _input_tokens: int = 0
    _output_tokens: int = 0
    _cost_microusd: int = 0

    def record(self, usage: ModelUsage) -> None:
        self._input_tokens += usage.input_tokens
        self._output_tokens += usage.output_tokens
        self._cost_microusd += usage.cost_microusd
        enforce_budget(
            ModelUsage(
                provider=usage.provider,
                model=usage.model,
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
                cost_microusd=self._cost_microusd,
            ),
            max_tokens=self.max_tokens,
            max_cost_microusd=self.max_cost_microusd,
        )


class ModelOutputError(ValueError):
    """A provider response did not meet the role's strict JSON contract."""


def _json_output(text: str) -> dict[str, object]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1] if "\n" in candidate else ""
        candidate = candidate.rsplit("```", 1)[0].strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ModelOutputError("model did not return JSON") from error
    if not isinstance(payload, dict):
        raise ModelOutputError("model JSON must be an object")
    return payload


def _evidence_payload(citations: list[Citation]) -> list[dict[str, str]]:
    return [
        {
            "id": citation.id,
            "source": citation.source,
            "locator": citation.locator,
            "text": citation.text,
        }
        for citation in citations
    ]


def _memory_payload(request: ResearchRequest) -> list[dict[str, str]]:
    """Memory is supplied as context only, never as an evidence citation."""
    return [{"id": str(memory.id), "content": memory.content} for memory in request.memory]


class EvidenceBoundAnalyst(ResearchAnalyst):
    """A runnable local Analyst that only turns supplied evidence into claims.

    It is deliberately conservative: without a configured model it quotes each
    evidence excerpt instead of inventing a research conclusion.  This keeps
    local and test runs useful while visibly preserving the evidence boundary.
    """

    allow_delegation = False

    async def produce_draft(
        self, request: ResearchRequest, revision_notes: list[str]
    ) -> ResearchDraft:
        # A fixed conclusion section has room for at most six claims.  Keep the
        # highest-ranked document excerpts within that contract rather than
        # letting an expansive retrieval leave a Run stuck in the Analyst stage.
        evidence = request.evidence[:6] if request.require_structured_conclusion else request.evidence[:32]
        claims = [
            ResearchClaim(text=citation.text, citation_ids=[citation.id]) for citation in evidence
        ]
        if not claims:
            # The Pydantic draft schema intentionally refuses an evidence-free answer;
            # use a sentinel citation so the Validator records the hard-gate failure.
            claims = [ResearchClaim(text=request.question, citation_ids=["missing-evidence"])]
        suffix = "；已按 Reviewer 意见修订。" if revision_notes else ""
        conclusion = None
        if request.require_structured_conclusion and evidence:
            conclusion = ResearchConclusion(
                confirmed_transaction_facts=claims,
                post_announcement_market_reaction=[],
                possible_impact_mechanisms=[],
                positive_factors=[],
                risks_and_uncertainties=[],
                missing_information=[
                    "公告后的市场反应：需要绑定公告日、个股和基准指数的可复算行情窗口。",
                    "可能的影响机制、正面因素和风险：当前确定性模式不对公告原文作超出摘录的推断。",
                ],
                confidence=ConclusionConfidence.LOW,
                confidence_rationale="本地确定性模式只摘录已检索的公告片段，必须经人工逐条复核后才可作为研究结论。",
                required_evidence_ids=[citation.id for citation in evidence],
            )
        return ResearchDraft(
            summary=f"基于 {len(evidence)} 条已提供证据整理的问题：{request.question}{suffix}",
            claims=claims,
            conclusion=conclusion,
        )


class EvidenceReviewer(EvidenceReviewerProtocol):
    """Independently audit that every claim is a direct excerpt of its evidence."""

    allow_delegation = False

    async def review(self, draft: ResearchDraft, citations: list[Citation]) -> ReviewDecision:
        evidence_by_id = {citation.id: citation for citation in citations}
        unsupported: list[str] = []
        targets: list[str] = []
        claim_reviews: list[ClaimCitationReview] = []
        for claim_index, claim in enumerate(draft.claims):
            targets.extend(claim.citation_ids)
            cited_text = " ".join(
                evidence_by_id[citation_id].text
                for citation_id in claim.citation_ids
                if citation_id in evidence_by_id
            )
            if claim.text not in cited_text:
                unsupported.append("将结论改为引用原文，或补充直接支持该结论的证据。")
            claim_reviews.extend(
                ClaimCitationReview(
                    claim_index=claim_index,
                    citation_id=citation_id,
                    supported=claim.text in evidence_by_id[citation_id].text,
                )
                for citation_id in claim.citation_ids
                if citation_id in evidence_by_id
            )
        targets = list(dict.fromkeys(targets))
        if unsupported:
            return ReviewDecision(
                verdict=ReviewVerdict.REVISE,
                claim_citation_ids=targets or [citation.id for citation in citations[:1]],
                claim_reviews=claim_reviews,
                revision_notes=list(dict.fromkeys(unsupported))[:8],
            )
        # This fallback cannot make a substantive investment judgment.  It can
        # prove the links were inspected, then deliberately stops at the human
        # gate instead of reproducing the former baseline auto-approval.
        return ReviewDecision(
            verdict=ReviewVerdict.HUMAN_REVIEW,
            claim_citation_ids=targets,
            claim_reviews=claim_reviews,
        )


@dataclass
class StructuredModelAnalyst(ResearchAnalyst):
    """Analyst backed by an explicitly configured OpenAI-compatible gateway."""

    gateway: CompletionGateway
    model: str
    timeout_seconds: float
    ledger: RunUsageLedger
    allow_delegation: bool = field(default=False, init=False)

    async def produce_draft(
        self, request: ResearchRequest, revision_notes: list[str]
    ) -> ResearchDraft:
        instruction = {
            "role": "investment research analyst",
            "rules": [
                "Use only the supplied evidence.",
                "Memory is user-approved context, not factual evidence and must not be cited.",
                "Return strict JSON matching ResearchDraft.",
                "Every claim must cite one or more supplied citation ids.",
                "For announcement research, fill the fixed conclusion object: confirmed_transaction_facts, post_announcement_market_reaction, possible_impact_mechanisms, positive_factors, risks_and_uncertainties, missing_information, confidence, confidence_rationale, required_evidence_ids.",
                "The top-level claims must exactly be the five factual conclusion sections concatenated in that order; include each key announcement citation in required_evidence_ids.",
                "Use calculations only when every operand is present in cited evidence; supply operator, operands, and result so the numeric validator can recompute it.",
                "Do not request tools or permissions.",
            ],
            "question": request.question,
            "evidence": _evidence_payload(request.evidence),
            "memory": _memory_payload(request),
            "revision_notes": revision_notes,
        }
        response = await self.gateway.complete(
            ModelRequest(
                model=self.model,
                messages=[
                    ModelMessage(role="system", content="You are a constrained research analyst."),
                    ModelMessage(role="user", content=json.dumps(instruction, ensure_ascii=False)),
                ],
                temperature=0,
            ),
            timeout_seconds=self.timeout_seconds,
        )
        self.ledger.record(response.usage)
        try:
            return ResearchDraft.model_validate(_json_output(response.text))
        except ValidationError as error:
            raise ModelOutputError("analyst output violates ResearchDraft schema") from error


@dataclass
class StructuredModelReviewer(EvidenceReviewerProtocol):
    """Reviewer backed by a separate configured model selection."""

    gateway: CompletionGateway
    model: str
    timeout_seconds: float
    ledger: RunUsageLedger
    allow_delegation: bool = field(default=False, init=False)

    async def review(self, draft: ResearchDraft, citations: list[Citation]) -> ReviewDecision:
        instruction = {
            "role": "investment research evidence reviewer",
            "rules": [
                "Use only the supplied draft and evidence.",
                "Return strict JSON matching ReviewDecision.",
                "Approve only claims directly supported by their cited excerpts.",
                "For every draft claim/citation pair, return one claim_reviews item with claim_index, citation_id, and supported=true/false. Never use a blanket approval.",
                "For revise, provide specific revision_notes. Do not alter evidence.",
            ],
            "draft": draft.model_dump(),
            "evidence": _evidence_payload(citations),
        }
        response = await self.gateway.complete(
            ModelRequest(
                model=self.model,
                messages=[
                    ModelMessage(role="system", content="You are an independent evidence reviewer."),
                    ModelMessage(role="user", content=json.dumps(instruction, ensure_ascii=False)),
                ],
                temperature=0,
            ),
            timeout_seconds=self.timeout_seconds,
        )
        self.ledger.record(response.usage)
        try:
            return ReviewDecision.model_validate(_json_output(response.text))
        except ValidationError as error:
            raise ModelOutputError("reviewer output violates ReviewDecision schema") from error
