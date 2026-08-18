"""Offline deterministic gate for comparing controlled runtime wiring."""

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from backend.app.agents.flow import ControlledResearchFlow
from backend.app.agents.runtime import run_with_runtime
from backend.app.agents.schemas import (
    AgentRuntime,
    Citation,
    ClaimCitationReview,
    ResearchClaim,
    ResearchDraft,
    ResearchRequest,
    ReviewDecision,
    ReviewVerdict,
)


class BaselineAnalyst:
    allow_delegation = False

    async def produce_draft(self, request: ResearchRequest, revision_notes: list[str]) -> ResearchDraft:
        del revision_notes
        citation_ids = [citation.id for citation in request.evidence[:1]]
        return ResearchDraft(
            summary=request.question,
            claims=[ResearchClaim(text=request.question, citation_ids=citation_ids)],
        )


class BaselineReviewer:
    allow_delegation = False

    async def review(self, draft: ResearchDraft, citations: list[Citation]) -> ReviewDecision:
        evidence_ids = {citation.id for citation in citations}
        return ReviewDecision(
            # A benchmark baseline may measure wiring, but it must not silently
            # certify an investment conclusion.
            verdict=ReviewVerdict.HUMAN_REVIEW,
            claim_citation_ids=[citation.id for citation in citations[:1]],
            claim_reviews=[
                ClaimCitationReview(
                    claim_index=index,
                    citation_id=citation_id,
                    supported=citation_id in evidence_ids,
                )
                for index, claim in enumerate(draft.claims)
                for citation_id in claim.citation_ids
            ],
        )


async def benchmark(runtime: AgentRuntime, dataset: Path) -> dict[str, object]:
    cases = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    started = perf_counter()
    approved = 0
    citation_gate_failures = 0
    revisions = 0
    for case in cases:
        evidence = [Citation.model_validate(item) for item in case["evidence"]]
        request = ResearchRequest(
            run_id=uuid5(NAMESPACE_URL, f"benchmark:{case['id']}"),
            workspace_id=uuid5(NAMESPACE_URL, "benchmark-workspace"),
            question=case["question"],
            evidence=evidence,
        )
        outcome = await run_with_runtime(
            runtime, ControlledResearchFlow(BaselineAnalyst(), BaselineReviewer()), request
        )
        approved += outcome.verdict is ReviewVerdict.APPROVE
        citation_gate_failures += not outcome.validation.passed
        revisions += outcome.revision_count
    return {
        "runtime": runtime.value,
        "cases": len(cases),
        "approved": approved,
        "citation_gate_failures": citation_gate_failures,
        "tool_calls": 0,
        "cost_microusd": 0,
        "revisions": revisions,
        "latency_ms": round((perf_counter() - started) * 1000, 2),
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", choices=[item.value for item in AgentRuntime], required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(asyncio.run(benchmark(AgentRuntime(args.runtime), args.dataset)), ensure_ascii=False))


if __name__ == "__main__":
    main()
