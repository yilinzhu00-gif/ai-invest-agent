from backend.app.agents.schemas import Citation, ResearchDraft, ValidationResult


def validate_draft(draft: ResearchDraft, evidence: list[Citation]) -> ValidationResult:
    """Apply non-overridable schema, citation, numeric and permission gates."""
    errors: list[str] = []
    if draft.requested_tool_permissions:
        errors.append("agents may not request tool permissions")

    evidence_ids = {citation.id for citation in evidence}
    if len(evidence_ids) != len(evidence):
        errors.append("evidence citation ids must be unique")
    for claim_index, claim in enumerate(draft.claims):
        unknown = sorted(set(claim.citation_ids) - evidence_ids)
        if unknown:
            errors.append(f"claim[{claim_index}] references unknown citations: {', '.join(unknown)}")
    return ValidationResult(passed=not errors, errors=errors)
