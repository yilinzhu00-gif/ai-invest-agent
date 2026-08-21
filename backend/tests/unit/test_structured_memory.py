from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.memory import ResearchMemoryRecord, UserMemoryProfile


def test_user_memory_profile_normalizes_preferences_and_accepts_principal_alias() -> None:
    profile = UserMemoryProfile(
        workspace_id="workspace-a",
        principal_id="user-a",
        investment_preferences=[" AI ", "AI", "Growth stocks"],
        risk_level=" medium ",
        industries=["Semiconductor"],
        historical_stocks=["NVDA"],
    )

    assert profile.user_id == "user-a"
    assert profile.investment_preferences == ["AI", "Growth stocks"]
    assert profile.risk_level == "medium"


def test_research_memory_record_matches_report_yaml_shape() -> None:
    record = ResearchMemoryRecord(
        workspace_id="workspace-a",
        report_title="NVIDIA analysis",
        report_date="2026-08-21",
        confidence=0.8,
    )

    assert record.report_date == date(2026, 8, 21)
    assert record.confidence == 0.8


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_research_memory_confidence_is_bounded(confidence: float) -> None:
    with pytest.raises(ValidationError):
        ResearchMemoryRecord(
            workspace_id="workspace-a",
            report_title="NVIDIA analysis",
            report_date=date(2026, 8, 21),
            confidence=confidence,
        )
