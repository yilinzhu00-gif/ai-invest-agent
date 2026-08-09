import hashlib
import json
from collections.abc import Sequence

from backend.app.security.pii import redact_sensitive_text
from backend.app.training.schemas import (
    CandidateStatus,
    TrainingCandidate,
    TrainingExample,
    TrainingExportPolicy,
    TrainingExportReport,
    TrainingReadinessStatus,
    TrainingSplit,
)


def _candidate_rejection_reasons(candidate: TrainingCandidate) -> list[str]:
    reasons: list[str] = []
    if candidate.status is not CandidateStatus.APPROVED:
        reasons.append("candidate_not_approved")
    if not candidate.license_allows_training:
        reasons.append("license_not_approved")
    if not candidate.training_authorized:
        reasons.append("training_not_authorized")
    if any(
        redact_sensitive_text(value) != value
        for value in (candidate.input_text, candidate.expected_output)
    ):
        reasons.append("sensitive_text_detected")
    return reasons


def _dataset_hash(examples: Sequence[TrainingExample]) -> str:
    canonical = json.dumps(
        [example.model_dump(mode="json") for example in examples],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def prepare_training_export(
    candidates: Sequence[TrainingCandidate],
    *,
    holdout_groups: frozenset[str],
    policy: TrainingExportPolicy | None = None,
) -> TrainingExportReport:
    policy = policy or TrainingExportPolicy()
    sample_ids = [candidate.sample_id for candidate in candidates]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("training sample ids must be unique")

    rejected = {
        candidate.sample_id: reasons
        for candidate in sorted(candidates, key=lambda item: item.sample_id)
        if (reasons := _candidate_rejection_reasons(candidate))
    }
    if rejected:
        return TrainingExportReport(
            status=TrainingReadinessStatus.NO_GO,
            train_count=0,
            holdout_count=0,
            rejected=rejected,
            dataset_hash=None,
            examples=[],
            reasons=["candidate_governance_gate_failed"],
        )

    examples = [
        TrainingExample(
            sample_id=candidate.sample_id,
            task_type=candidate.task_type,
            source_run_id=candidate.source_run_id,
            classification=candidate.classification,
            input_text=candidate.input_text,
            expected_output=candidate.expected_output,
            tool_names=candidate.tool_names,
            labels=candidate.labels,
            license_id=candidate.license_id,
            split_group=candidate.split_group,
            split=(
                TrainingSplit.HOLDOUT
                if candidate.split_group in holdout_groups
                else TrainingSplit.TRAIN
            ),
        )
        for candidate in sorted(candidates, key=lambda item: item.sample_id)
    ]
    train_count = sum(example.split is TrainingSplit.TRAIN for example in examples)
    holdout_count = sum(example.split is TrainingSplit.HOLDOUT for example in examples)
    reasons: list[str] = []
    if train_count < policy.minimum_train:
        reasons.append("minimum_train_not_met")
    if holdout_count < policy.minimum_holdout:
        reasons.append("minimum_holdout_not_met")
    if holdout_count > policy.maximum_holdout:
        reasons.append("maximum_holdout_exceeded")
    if reasons:
        return TrainingExportReport(
            status=TrainingReadinessStatus.INSUFFICIENT_EVIDENCE,
            train_count=train_count,
            holdout_count=holdout_count,
            rejected={},
            dataset_hash=None,
            examples=[],
            reasons=reasons,
        )
    return TrainingExportReport(
        status=TrainingReadinessStatus.EVIDENCE_READY,
        train_count=train_count,
        holdout_count=holdout_count,
        rejected={},
        dataset_hash=_dataset_hash(examples),
        examples=examples,
        reasons=[],
    )
