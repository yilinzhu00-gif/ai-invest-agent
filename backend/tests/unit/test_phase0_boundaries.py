from pathlib import Path

from backend.app.agents.planner import make_plan
from backend.app.config import Settings
from backend.app.main import create_app


def test_phase0_import_boundaries_and_research_route() -> None:
    app = create_app(Settings(app_env="test"))
    assert "/api/v1/research/capabilities" in app.openapi()["paths"]
    assert make_plan("  cash flow  ").question == "cash flow"


def test_phase0_directories_are_present() -> None:
    root = Path(__file__).parents[3]
    for relative in (
        "backend/app/api/research.py",
        "backend/app/api/stock.py",
        "backend/app/agents/planner.py",
        "backend/app/agents/researcher.py",
        "backend/app/agents/debate.py",
        "backend/app/agents/reflection.py",
        "backend/app/services/llm.py",
        "backend/app/services/market.py",
        "backend/app/services/news.py",
        "backend/app/rag",
        "backend/app/memory",
        "backend/app/evaluation",
        "backend/app/config",
        "frontend",
        "docker",
        "docker-compose.yml",
    ):
        assert (root / relative).exists(), relative

