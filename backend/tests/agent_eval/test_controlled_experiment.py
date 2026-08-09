from collections.abc import Iterable

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


def _observations(
    arm: AgentExperimentArm,
    *,
    passed: int,
    cases: int = 100,
    latency_ms: int = 100,
    cost_microusd: int = 50,
    case_ids: Iterable[str] | None = None,
) -> list[ExperimentObservation]:
    ids = list(case_ids) if case_ids is not None else [f"case-{index:03d}" for index in range(cases)]
    return [
        ExperimentObservation(
            case_id=case_id,
            arm=arm,
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
        AgentCapability(
            name="unsafe",
            input_schema="input/v1",
            output_schema="output/v1",
            allowed_tools=("query_table",),
            max_calls=2,
            max_cost_microusd=1_000,
            required_eval_suite="unsafe/v1",
        )


def test_experiment_rejects_non_identical_case_sets() -> None:
    observations = _three_arms()
    observations[-1] = observations[-1].model_copy(update={"case_id": "different-case"})

    with pytest.raises(ValueError, match="identical case sets"):
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
