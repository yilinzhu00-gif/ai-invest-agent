import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.agents.capabilities import AgentCapability
from backend.app.agents.experiment import (
    AgentExperimentArm,
    ExperimentDecisionStatus,
    ExperimentObservation,
    ExperimentPolicy,
    evaluate_controlled_experiment,
)
from backend.app.evidence.provenance import EvidenceKind, EvidenceProvenance


def _provenance(kind: EvidenceKind = EvidenceKind.REAL_ATTESTED) -> EvidenceProvenance:
    return EvidenceProvenance(
        kind=kind,
        source_reference="artifact://agent-experiment/v1",
        artifact_sha256="a" * 64,
        collected_at=datetime(2026, 8, 9, tzinfo=UTC),
        attested_by="reviewer-1" if kind is EvidenceKind.REAL_ATTESTED else None,
    )


def _observations(
    arm: AgentExperimentArm,
    *,
    passed: int,
    cases: int = 100,
    latency_ms: int = 100,
    cost_microusd: int = 50,
    case_ids: Iterable[str] | None = None,
    provenance: EvidenceProvenance | None = None,
    model_id: str = "model-v1",
    token_budget: int = 1_000,
) -> list[ExperimentObservation]:
    ids = list(case_ids) if case_ids is not None else [f"case-{index:03d}" for index in range(cases)]
    return [
        ExperimentObservation(
            case_id=case_id,
            case_sha256=hashlib.sha256(case_id.encode()).hexdigest(),
            arm=arm,
            experiment_id=UUID(int=1),
            provenance=provenance or _provenance(),
            model_id=model_id,
            token_budget=token_budget,
            input_tokens=600,
            output_tokens=200,
            hard_gate_passed=index < passed,
            latency_ms=latency_ms,
            cost_microusd=cost_microusd,
            failure_type=None if index < passed else "quality_gate",
        )
        for index, case_id in enumerate(ids)
    ]


def _three_arms(*, specialist_passed: int = 86, specialist_cost: int = 50) -> list[ExperimentObservation]:
    return [
        *_observations(AgentExperimentArm.BASELINE, passed=78),
        *_observations(AgentExperimentArm.TOKEN_MATCHED, passed=80),
        *_observations(
            AgentExperimentArm.SPECIALIST,
            passed=specialist_passed,
            cost_microusd=specialist_cost,
        ),
    ]


def test_capability_cannot_delegate_write_or_exceed_one_call() -> None:
    capability = AgentCapability(
        name="financial-validator",
        input_schema="financial-validation-input/v1",
        output_schema="financial-validation-output/v1",
        allowed_tools=("query_table",),
        max_cost_microusd=1_000,
        required_eval_suite="financial-validator/v1",
    )

    assert capability.allow_delegation is False
    assert capability.read_only is True
    assert capability.max_calls == 1
    with pytest.raises(ValidationError):
        AgentCapability.model_validate(
            {
                "name": "unsafe",
                "input_schema": "input/v1",
                "output_schema": "output/v1",
                "allowed_tools": ("query_table",),
                "max_calls": 2,
                "max_cost_microusd": 1_000,
                "required_eval_suite": "unsafe/v1",
            }
        )


def test_experiment_rejects_non_identical_case_sets() -> None:
    observations = _three_arms()
    observations[-1] = observations[-1].model_copy(update={"case_id": "different-case"})

    with pytest.raises(ValueError, match="identical case sets"):
        evaluate_controlled_experiment(observations, ExperimentPolicy())


def test_experiment_rejects_same_case_id_with_different_input_digest() -> None:
    observations = _three_arms()
    observations[-1] = observations[-1].model_copy(update={"case_sha256": "f" * 64})

    with pytest.raises(ValueError, match="identical case inputs"):
        evaluate_controlled_experiment(observations, ExperimentPolicy())


def test_fewer_than_100_matched_cases_is_insufficient_evidence() -> None:
    observations = [
        *_observations(AgentExperimentArm.BASELINE, passed=70, cases=99),
        *_observations(AgentExperimentArm.TOKEN_MATCHED, passed=75, cases=99),
        *_observations(AgentExperimentArm.SPECIALIST, passed=85, cases=99),
    ]

    decision = evaluate_controlled_experiment(observations, ExperimentPolicy())

    assert decision.status is ExperimentDecisionStatus.INSUFFICIENT_EVIDENCE
    assert decision.matched_cases == 99
    assert decision.reasons == ["minimum_cases_not_met"]


def test_synthetic_evidence_can_never_return_go() -> None:
    synthetic = _provenance(EvidenceKind.SYNTHETIC)
    observations = [
        *_observations(AgentExperimentArm.BASELINE, passed=70, provenance=synthetic),
        *_observations(AgentExperimentArm.TOKEN_MATCHED, passed=80, provenance=synthetic),
        *_observations(AgentExperimentArm.SPECIALIST, passed=100, provenance=synthetic),
    ]

    decision = evaluate_controlled_experiment(observations, ExperimentPolicy())

    assert decision.status is ExperimentDecisionStatus.INSUFFICIENT_EVIDENCE
    assert decision.reasons == ["real_attested_evidence_required"]


def test_token_matched_and_specialist_arms_require_same_model_and_budget() -> None:
    observations = _three_arms()
    observations[-1] = observations[-1].model_copy(update={"token_budget": 2_000})

    with pytest.raises(ValueError, match="same model and token budget"):
        evaluate_controlled_experiment(observations, ExperimentPolicy())


def test_experiment_observation_requires_case_digest() -> None:
    payload = _observations(AgentExperimentArm.BASELINE, passed=1, cases=1)[0].model_dump()
    payload.pop("case_sha256")

    with pytest.raises(ValidationError):
        ExperimentObservation.model_validate(payload)


def test_specialist_is_go_only_against_token_matched_arm_and_within_budgets() -> None:
    decision = evaluate_controlled_experiment(
        _three_arms(),
        ExperimentPolicy(max_p95_latency_ms=200, max_average_cost_microusd=60),
    )

    assert decision.status is ExperimentDecisionStatus.GO
    assert decision.hard_gate_improvement_pp == 6.0
    assert decision.metrics[AgentExperimentArm.SPECIALIST].hard_gate_pass_rate == 0.86
    assert decision.metrics[AgentExperimentArm.SPECIALIST].p95_latency_ms == 100
    assert decision.reasons == []


@pytest.mark.parametrize(
    ("observations", "reason"),
    [
        (_three_arms(specialist_passed=84), "hard_gate_improvement_below_threshold"),
        (_three_arms(specialist_cost=61), "average_cost_budget_exceeded"),
    ],
)
def test_specialist_is_no_go_when_quality_or_budget_gate_fails(
    observations: list[ExperimentObservation], reason: str
) -> None:
    decision = evaluate_controlled_experiment(
        observations,
        ExperimentPolicy(max_p95_latency_ms=200, max_average_cost_microusd=60),
    )

    assert decision.status is ExperimentDecisionStatus.NO_GO
    assert reason in decision.reasons


def test_latency_budget_is_a_hard_no_go_gate() -> None:
    observations = [
        *_observations(AgentExperimentArm.BASELINE, passed=78),
        *_observations(AgentExperimentArm.TOKEN_MATCHED, passed=80),
        *_observations(AgentExperimentArm.SPECIALIST, passed=86, latency_ms=201),
    ]

    decision = evaluate_controlled_experiment(
        observations,
        ExperimentPolicy(max_p95_latency_ms=200, max_average_cost_microusd=60),
    )

    assert decision.status is ExperimentDecisionStatus.NO_GO
    assert decision.reasons == ["p95_latency_budget_exceeded"]


def test_decision_uses_exact_improvement_before_display_rounding() -> None:
    cases = 981
    observations = [
        *_observations(AgentExperimentArm.BASELINE, passed=560, cases=cases),
        *_observations(AgentExperimentArm.TOKEN_MATCHED, passed=572, cases=cases),
        *_observations(AgentExperimentArm.SPECIALIST, passed=621, cases=cases),
    ]

    decision = evaluate_controlled_experiment(observations, ExperimentPolicy())

    assert decision.hard_gate_improvement_pp == 4.99
    assert decision.status is ExperimentDecisionStatus.NO_GO
    assert decision.reasons == ["hard_gate_improvement_below_threshold"]


def test_decision_uses_exact_average_cost_before_display_rounding() -> None:
    cases = 250
    specialist = _observations(
        AgentExperimentArm.SPECIALIST,
        passed=215,
        cases=cases,
        cost_microusd=60,
    )
    specialist[0] = specialist[0].model_copy(update={"cost_microusd": 61})
    observations = [
        *_observations(AgentExperimentArm.BASELINE, passed=195, cases=cases),
        *_observations(AgentExperimentArm.TOKEN_MATCHED, passed=200, cases=cases),
        *specialist,
    ]

    decision = evaluate_controlled_experiment(
        observations,
        ExperimentPolicy(max_average_cost_microusd=60),
    )

    assert decision.metrics[AgentExperimentArm.SPECIALIST].average_cost_microusd == 60.0
    assert decision.status is ExperimentDecisionStatus.NO_GO
    assert decision.reasons == ["average_cost_budget_exceeded"]
