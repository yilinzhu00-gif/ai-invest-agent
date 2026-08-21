from backend.app.agents.planner import AI_INDUSTRY_STEP, make_plan
from backend.app.memory.research_memory import ResearchMemoryRecord
from backend.app.memory.user_memory import UserMemoryProfile


def test_planner_marks_ai_interest_from_user_memory() -> None:
    profile = UserMemoryProfile(
        workspace_id="workspace-a",
        user_id="analyst-a",
        industries=["AI"],
        investment_style="成长",
    )

    plan = make_plan("分析 NVIDIA 投资价值", user_memory=profile)

    assert AI_INDUSTRY_STEP in plan.steps
    assert "user_memory:ai_interest" in plan.memory_used


def test_planner_marks_previous_research_context() -> None:
    history = ResearchMemoryRecord(
        workspace_id="workspace-a",
        user_id="analyst-a",
        report_title="NVIDIA historical report",
        report_date="2026-08-20",
        confidence=0.8,
    )

    plan = make_plan("复盘 NVIDIA 风险", research_memories=[history])

    assert "research_memory:previous_reports" in plan.memory_used
