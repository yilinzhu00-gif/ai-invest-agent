from math import isclose
from typing import Protocol

from backend.app.agents.schemas import (
    CalculationOperator,
    Citation,
    NumericCalculation,
    ResearchDraft,
    ValidationResult,
)


class ResearchValidator(Protocol):
    """The validator is an independent, non-delegating hard gate."""

    allow_delegation: bool

    def validate(self, draft: ResearchDraft, evidence: list[Citation]) -> ValidationResult: ...


class NumericEvidenceValidator:
    """Independently validate citations and all Analyst-supplied calculations.

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
            for calculation_index, calculation in enumerate(claim.calculations):
                self._validate_calculation(
                    claim_index,
                    calculation_index,
                    calculation,
                    cited_text,
                    errors,
                )

        return ValidationResult(passed=not errors, errors=errors)

    @staticmethod
    def _validate_calculation(
        claim_index: int,
        calculation_index: int,
        calculation: NumericCalculation,
        cited_text: str,
        errors: list[str],
    ) -> None:
        prefix = f"claim[{claim_index}] calculation[{calculation_index}]"
        for operand in calculation.operands:
            if format(operand, "g") not in cited_text:
                errors.append(f"{prefix} operand {format(operand, 'g')} is not in cited evidence")
        expected: float | None = None
        if calculation.operator is CalculationOperator.SUM:
            expected = sum(calculation.operands)
        elif calculation.operator is CalculationOperator.DIFFERENCE:
            if len(calculation.operands) != 2:
                errors.append(f"{prefix} difference requires exactly two operands")
            else:
                expected = calculation.operands[0] - calculation.operands[1]
        elif calculation.operator is CalculationOperator.RATIO:
            if len(calculation.operands) != 2 or calculation.operands[1] == 0:
                errors.append(f"{prefix} ratio requires two operands and a non-zero denominator")
            else:
                expected = calculation.operands[0] / calculation.operands[1]
        elif calculation.operator is CalculationOperator.PERCENT_CHANGE:
            if len(calculation.operands) != 2 or calculation.operands[0] == 0:
                errors.append(
                    f"{prefix} percent_change requires two operands and a non-zero starting value"
                )
            else:
                expected = (calculation.operands[1] / calculation.operands[0] - 1) * 100
        if expected is not None and not isclose(
            calculation.result, expected, rel_tol=1e-6, abs_tol=1e-6
        ):
            errors.append(
                f"{prefix} result {format(calculation.result, 'g')} does not equal "
                f"recomputed value {format(expected, 'g')}"
            )


class EvidenceValidator(NumericEvidenceValidator):
    """Backward-compatible name for the independent numeric/evidence gate."""


def validate_draft(
    draft: ResearchDraft, evidence: list[Citation], *, require_structured_conclusion: bool = False
) -> ValidationResult:
    """Backward-compatible entrypoint for the default Validator agent."""
    result = EvidenceValidator().validate(draft, evidence)
    if not require_structured_conclusion:
        return result
    errors = list(result.errors)
    conclusion = draft.conclusion
    if conclusion is None:
        errors.append("announcement research requires the fixed structured conclusion")
    else:
        evidence_ids = {citation.id for citation in evidence}
        required = set(conclusion.required_evidence_ids)
        if len(required) != len(conclusion.required_evidence_ids):
            errors.append("conclusion repeats a required evidence id")
        missing = sorted(required - evidence_ids)
        if missing:
            errors.append("conclusion requires missing evidence: " + ", ".join(missing))
        cited = {citation_id for claim in draft.claims for citation_id in claim.citation_ids}
        unreferenced = sorted(required - cited)
        if unreferenced:
            errors.append("conclusion required evidence is not cited by a claim: " + ", ".join(unreferenced))
    return ValidationResult(passed=not errors, errors=errors)
