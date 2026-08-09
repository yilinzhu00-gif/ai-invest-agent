import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.security.classification import DataClassification
from backend.app.training.export import prepare_training_export
from backend.app.training.schemas import (
    CandidateStatus,
    TrainingCandidate,
    TrainingExportPolicy,
    TrainingReadinessStatus,
    TrainingSplit,
)


def _candidate(
    index: int,
    *,
    split_group: str | None = None,
    input_text: str = "核对营业收入是否与引用一致",
    license_allows_training: bool = True,
    training_authorized: bool = True,
) -> TrainingCandidate:
    return TrainingCandidate(
        sample_id=f"sample-{index:04d}",
        task_type="evidence_review",
        source_run_id=UUID(int=index + 1),
        source_document_id=f"document-{index:04d}",
        source_content_sha256=hashlib.sha256(f"content-{index}".encode()).hexdigest(),
        workspace_id=UUID(int=10_000),
        classification=DataClassification.INTERNAL,
        input_text=input_text,
        expected_output="引用与数值一致",
        tool_names=("query_table",),
        labels=("approved", "numeric"),
        approver_id="reviewer-1",
        approved_at=datetime(2026, 8, 9, tzinfo=UTC),
        license_id="internal-approved/v1",
        license_allows_training=license_allows_training,
        training_authorized=training_authorized,
        split_group=split_group or f"company-{index:04d}",
        status=CandidateStatus.APPROVED,
    )


def test_approved_candidate_requires_approver_and_timestamp() -> None:
    payload = _candidate(1).model_dump()
    payload["approver_id"] = None
    payload["approved_at"] = None

    with pytest.raises(ValidationError, match="approved candidates require"):
        TrainingCandidate.model_validate(payload)
    with pytest.raises(ValidationError):
        TrainingCandidate.model_validate(_candidate(1).model_dump() | {"unexpected": True})


def test_export_is_no_go_when_license_or_authorization_is_missing() -> None:
    candidates = [
        _candidate(1, license_allows_training=False),
        _candidate(2, training_authorized=False),
    ]

    report = prepare_training_export(
        candidates,
        holdout_groups=frozenset(),
        policy=TrainingExportPolicy(minimum_train=1, minimum_holdout=0, maximum_holdout=1),
    )

    assert report.status is TrainingReadinessStatus.NO_GO
    assert report.examples == []
    assert report.dataset_hash is None
    assert report.rejected == {
        "sample-0001": ["license_not_approved"],
        "sample-0002": ["training_not_authorized"],
    }


@pytest.mark.parametrize(
    "input_text",
    [
        "联系手机号 13800138000",
        "Authorization: Bearer secret-token",
        "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE",
        "SLACK_BOT_TOKEN=" + "xoxb-" + "redacted-fixture-1234567890",
        "GOOGLE_API_KEY=AIzaSyDUMMYKEY1234567890abcdefghijklm",
        "GITLAB_TOKEN=glpat-abcdefghijklmnopqrst",
        "-----BEGIN PRIVATE KEY-----",
        "password=correct-horse-battery-staple",
    ],
)
def test_export_rejects_sensitive_text(input_text: str) -> None:
    report = prepare_training_export(
        [_candidate(1, input_text=input_text)],
        holdout_groups=frozenset(),
        policy=TrainingExportPolicy(minimum_train=1, minimum_holdout=0, maximum_holdout=1),
    )

    assert report.status is TrainingReadinessStatus.NO_GO
    assert report.rejected == {"sample-0001": ["sensitive_text_detected"]}


def test_export_scans_exported_text_metadata_for_secrets() -> None:
    candidate = _candidate(1).model_copy(
        update={"labels": ("approved", "glpat-abcdefghijklmnopqrst")}
    )

    report = prepare_training_export(
        [candidate],
        holdout_groups=frozenset(),
        policy=TrainingExportPolicy(minimum_train=1, minimum_holdout=0, maximum_holdout=1),
    )

    assert report.status is TrainingReadinessStatus.NO_GO
    assert report.rejected == {"sample-0001": ["sensitive_text_detected"]}


def test_group_split_and_dataset_hash_are_deterministic() -> None:
    train = _candidate(1, split_group="company-a")
    holdout = _candidate(2, split_group="company-b")
    policy = TrainingExportPolicy(minimum_train=1, minimum_holdout=1, maximum_holdout=2)

    first = prepare_training_export(
        [train, holdout], holdout_groups=frozenset({"company-b"}), policy=policy
    )
    second = prepare_training_export(
        [holdout, train], holdout_groups=frozenset({"company-b"}), policy=policy
    )

    assert first.status is TrainingReadinessStatus.EVIDENCE_READY
    assert [(item.sample_id, item.split) for item in first.examples] == [
        ("sample-0001", TrainingSplit.TRAIN),
        ("sample-0002", TrainingSplit.HOLDOUT),
    ]
    assert first.dataset_hash == second.dataset_hash
    assert len(first.dataset_hash or "") == 64


def test_duplicate_sample_ids_are_rejected() -> None:
    duplicate = _candidate(1)

    with pytest.raises(ValueError, match="sample ids must be unique"):
        prepare_training_export(
            [duplicate, duplicate],
            holdout_groups=frozenset(),
            policy=TrainingExportPolicy(minimum_train=1, minimum_holdout=0, maximum_holdout=1),
        )


def test_duplicate_source_content_cannot_inflate_or_cross_splits() -> None:
    train = _candidate(1, split_group="company-a")
    holdout = _candidate(2, split_group="company-b").model_copy(
        update={"source_content_sha256": train.source_content_sha256}
    )

    with pytest.raises(ValueError, match="source content must be unique"):
        prepare_training_export(
            [train, holdout],
            holdout_groups=frozenset({"company-b"}),
            policy=TrainingExportPolicy(minimum_train=1, minimum_holdout=1, maximum_holdout=2),
        )


def test_one_source_document_cannot_cross_split_groups() -> None:
    train = _candidate(1, split_group="company-a")
    holdout = _candidate(2, split_group="company-b").model_copy(
        update={"source_document_id": train.source_document_id}
    )

    with pytest.raises(ValueError, match="source document cannot cross split groups"):
        prepare_training_export(
            [train, holdout],
            holdout_groups=frozenset({"company-b"}),
            policy=TrainingExportPolicy(minimum_train=1, minimum_holdout=1, maximum_holdout=2),
        )


def test_one_source_run_cannot_cross_split_groups() -> None:
    train = _candidate(1, split_group="company-a")
    holdout = _candidate(2, split_group="company-b").model_copy(
        update={"source_run_id": train.source_run_id}
    )

    with pytest.raises(ValueError, match="source run cannot cross split groups"):
        prepare_training_export(
            [train, holdout],
            holdout_groups=frozenset({"company-b"}),
            policy=TrainingExportPolicy(minimum_train=1, minimum_holdout=1, maximum_holdout=2),
        )


def test_blank_license_or_approver_is_rejected() -> None:
    for field in ("license_id", "approver_id"):
        payload = _candidate(1).model_dump()
        payload[field] = "   "
        with pytest.raises(ValidationError):
            TrainingCandidate.model_validate(payload)


def test_default_gate_requires_300_train_and_50_to_100_holdout() -> None:
    train = [_candidate(index) for index in range(300)]
    holdout = [
        _candidate(1_000 + index, split_group=f"holdout-{index:03d}") for index in range(50)
    ]
    holdout_groups = frozenset(candidate.split_group for candidate in holdout)

    report = prepare_training_export([*train, *holdout], holdout_groups=holdout_groups)

    assert report.status is TrainingReadinessStatus.EVIDENCE_READY
    assert report.train_count == 300
    assert report.holdout_count == 50
    assert report.rejected == {}
