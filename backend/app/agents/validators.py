from typing import Protocol

from backend.app.agents.schemas import Citation, ResearchDraft, ValidationResult


class ResearchValidator(Protocol):
    """The validator is an independent, non-delegating hard gate."""

    allow_delegation: bool

    def validate(self, draft: ResearchDraft, evidence: list[Citation]) -> ValidationResult: ...


class EvidenceValidator:
    """Validate the evidence boundary before a reviewer can see a draft.

    This role is intentionally deterministic.  It enforces contracts that a
    language model must not be able to waive: evidence identifiers, finite
    numerical values, and the no-new-permissions policy.
    """

    allow_delegation = False

    def validate(self, draft: ResearchDraft, evidence: list[Citation]) -> ValidationResult:
        errors: list[str] = []
        if not evidence:
            errors.append("research requires at least one evidence citation")
        if draft.requested_tool_permissions:
            errors.append("agents may not request tool permissions")

        evidence_ids = {citation.id for citation in evidence}
        if len(evidence_ids) != len(evidence):
            errors.append("evidence citation ids must be unique")
        for claim_index, claim in enumerate(draft.claims):
            if len(set(claim.citation_ids)) != len(claim.citation_ids):
                errors.append(f"claim[{claim_index}] repeats a citation id")
            unknown = sorted(set(claim.citation_ids) - evidence_ids)
            if unknown:
                errors.append(
                    f"claim[{claim_index}] references unknown citations: {', '.join(unknown)}"
                )
            # Numeric assertions must be visibly grounded in one of their cited excerpts.
            cited_text = " ".join(
                citation.text for citation in evidence if citation.id in claim.citation_ids
            )
            for value in claim.numeric_values:
                if format(value, "g") not in cited_text:
                    errors.append(
                        f"claim[{claim_index}] numeric value {format(value, 'g')} is not in cited evidence"
                    )
        return ValidationResult(passed=not errors, errors=errors)


def validate_draft(draft: ResearchDraft, evidence: list[Citation]) -> ValidationResult:
    """Backward-compatible entrypoint for the default Validator agent."""
    return EvidenceValidator().validate(draft, evidence)
