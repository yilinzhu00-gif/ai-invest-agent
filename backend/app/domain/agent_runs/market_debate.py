"""Persisted Agent Run adapter for the bounded market debate workflow."""

from uuid import UUID

from backend.app.agents.concrete import RunUsageLedger
from backend.app.agents.factory import build_completion_gateway
from backend.app.core.config import Settings
from backend.app.domain.agent_runs.models import AgentRun
from backend.app.domain.agent_runs.schemas import AgentRunStatus
from backend.app.domain.agent_runs.service import AgentRunService, RunPrincipal
from backend.app.domain.market_debate import MarketDebateResult, run_market_debate
from backend.app.domain.market_dossier import build_market_dossier
from backend.app.tools.market_registry import build_market_tool_registry
from backend.app.tools.policy import ToolPrincipal


class MarketDebateRunError(RuntimeError):
    """A market-debate Run cannot produce a truthful result."""


def _tool_principal(principal: RunPrincipal) -> ToolPrincipal:
    return ToolPrincipal(
        workspace_id=principal.workspace_id,
        permissions=frozenset({"tools:market:read"}),
    )


def market_debate_result_payload(result: MarketDebateResult) -> dict[str, object]:
    return {
        "symbol": result.symbol,
        "bull": result.bull.model_dump(mode="json"),
        "bear": result.bear.model_dump(mode="json"),
        "moderator": result.moderator.model_dump(mode="json"),
        "boundary": result.boundary,
    }


def _summary(result: MarketDebateResult) -> str:
    consensus = "；".join(result.moderator.consensus) or "暂无共识"
    disagreements = "；".join(result.moderator.disagreements) or "暂无记录"
    return f"市场事实辩论完成。共识：{consensus}。分歧：{disagreements}。"


async def execute_market_debate_run(
    *,
    run_id: UUID,
    principal: RunPrincipal,
    run: AgentRun,
    service: AgentRunService,
    settings: Settings,
) -> str:
    """Build a dossier, persist role events, and complete one market-debate Run."""
    if run.symbol is None:
        raise MarketDebateRunError("market_debate_requires_symbol")
    gateway = build_completion_gateway(settings)
    if gateway is None:
        raise MarketDebateRunError("model_not_configured")

    dossier = await build_market_dossier(
        registry=build_market_tool_registry(),
        principal=_tool_principal(principal),
        symbol=run.symbol,
    )
    if dossier.status == "unavailable":
        raise MarketDebateRunError("market_data_unavailable")
    await service.append_event(
        run_id,
        principal,
        "debate.dossier",
        {"symbol": dossier.symbol, "status": dossier.status, "dossier": dossier.model_dump(mode="json")},
    )

    result = await run_market_debate(
        dossier=dossier,
        gateway=gateway,
        model=settings.chat_model,
        timeout_seconds=settings.agent_model_timeout_seconds,
        ledger=RunUsageLedger(
            max_tokens=settings.model_run_max_tokens,
            max_cost_microusd=settings.model_run_max_cost_microusd,
        ),
    )
    await service.append_event(run_id, principal, "debate.bull", result.bull.model_dump(mode="json"))
    await service.append_event(run_id, principal, "debate.bear", result.bear.model_dump(mode="json"))
    await service.append_event(
        run_id, principal, "debate.moderator", result.moderator.model_dump(mode="json")
    )
    await service.append_event(run_id, principal, "debate.result", market_debate_result_payload(result))
    summary = _summary(result)
    await service.record_assistant_message(run_id, principal, summary)
    terminal = await service.transition(
        run_id,
        principal,
        AgentRunStatus.COMPLETED,
        "run.completed",
        {"workflow": "market_debate", "verdict": "evidence_only"},
    )
    return terminal.status
