"""Regression tests for legacy scoring callers during the API transition."""

from __future__ import annotations

import runpy
import sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import legacy
from legacy import agent

FULL_METRICS = {
    "pe_ttm": 18.5,
    "pb": 2.3,
    "roe": 16.2,
    "net_margin": 12.5,
    "gross_margin": 38.0,
    "rev_growth": 22.0,
    "profit_growth": 28.0,
    "debt_ratio": 45.0,
    "current_ratio": 1.8,
    "ret_60d": 8.0,
    "price_vs_ma20": 3.5,
}


def test_agent_score_tool_hides_rating_when_data_is_insufficient(monkeypatch) -> None:
    """Calling the legacy scorer from the tool would expose a low-coverage rating."""
    monkeypatch.setattr(agent.finance, "get_metrics", lambda _: {"pe_ttm": 18.5})

    evaluation = agent.score_stock.invoke({"code": "600519"})

    assert evaluation["status"] == "insufficient_data"
    assert evaluation["result"] is None
    assert "grade" not in evaluation
    assert "label" not in evaluation


def _run_streamlit_score(metrics: dict[str, float]) -> tuple[MagicMock, int]:
    fake_streamlit = MagicMock()
    fake_streamlit.session_state = {}
    fake_streamlit.tabs.return_value = [nullcontext() for _ in range(5)]
    fake_streamlit.text_input.side_effect = lambda _, **kwargs: str(kwargs.get("value", ""))
    fake_streamlit.text_area.return_value = ""
    fake_streamlit.file_uploader.return_value = None
    fake_streamlit.button.side_effect = lambda _, **kwargs: kwargs.get("key") == "score"
    fake_streamlit.spinner.return_value = nullcontext()
    fake_streamlit.expander.return_value = nullcontext()
    fake_streamlit.columns.return_value = [fake_streamlit, fake_streamlit]
    fake_streamlit.container.return_value = fake_streamlit
    explanation_calls = 0

    def create_explanation(**_: object) -> SimpleNamespace:
        nonlocal explanation_calls
        explanation_calls += 1
        message = SimpleNamespace(content="must not be rendered")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create_explanation))
    )
    fake_finance = SimpleNamespace(get_metrics=lambda _: metrics)
    fake_llm = SimpleNamespace(_chat_client=fake_client, CHAT_MODEL="test-model")
    fake_agent = SimpleNamespace(set_research_store=lambda _: None)

    with (
        patch.dict(sys.modules, {"streamlit": fake_streamlit}),
        patch.object(legacy, "finance", fake_finance),
        patch.object(legacy, "llm", fake_llm, create=True),
        patch.object(legacy, "agent", fake_agent),
        patch.object(legacy, "rag", SimpleNamespace(), create=True),
    ):
        runpy.run_path("legacy/app.py", run_name="__legacy_scoring_ui_test__")

    return fake_streamlit, explanation_calls


def test_streamlit_hides_rating_and_skips_explanation_when_data_is_insufficient() -> None:
    """The legacy UI must diagnose low coverage without sending it to the LLM."""
    fake_streamlit, explanation_calls = _run_streamlit_score({"pe_ttm": 18.5})

    rendered_text = " ".join(
        str(value) for call in fake_streamlit.write.call_args_list for value in call.args
    )
    fake_streamlit.warning.assert_called_once()
    assert "覆盖率" in rendered_text
    assert "12%" in rendered_text
    assert "缺失核心维度" in rendered_text
    assert "缺失指标" in rendered_text
    fake_streamlit.metric.assert_not_called()
    assert explanation_calls == 0


def test_streamlit_preserves_full_score_display_and_explanation() -> None:
    """Passing the quality gate must retain the legacy total, rating, and explanation path."""
    fake_streamlit, explanation_calls = _run_streamlit_score(FULL_METRICS)

    fake_streamlit.metric.assert_any_call("综合评分", "79.9", "B · 看好")
    assert explanation_calls == 1
