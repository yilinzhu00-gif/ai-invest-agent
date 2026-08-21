"""Authenticated read-only public market-data endpoints."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.agents.concrete import RunUsageLedger
from backend.app.api.v1.agent_runs import get_request_principal
from backend.app.domain.agent_runs.service import RunPrincipal
from backend.app.domain.market_debate import (
    MarketDebateInput,
    MarketDebateOutputError,
    MarketDebateResult,
    run_market_debate,
)
from backend.app.domain.market_dossier import (
    MarketDossier,
    MarketDossierInput,
    build_market_dossier,
)
from backend.app.security.authorization import AuthorizationError, require_permission
from backend.app.security.principal import Principal
from backend.app.tools.market_data import (
    MarketDataUnavailableError,
    MarketFinancialsInput,
    MarketFinancialsOutput,
    MarketQuoteInput,
    MarketQuoteOutput,
    MarketValuationInput,
    MarketValuationOutput,
)
from backend.app.tools.policy import ToolPrincipal
from backend.app.tools.registry import ToolRegistry, ToolTimeoutError

router = APIRouter(prefix="/market", tags=["market-data"])


def _require_market_permission(principal: RunPrincipal) -> None:
    if isinstance(principal, Principal):
        try:
            require_permission(principal, "market:read")
        except AuthorizationError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from error


def _tool_principal(principal: RunPrincipal) -> ToolPrincipal:
    permissions: set[str]
    if isinstance(principal, Principal):
        permissions = set(principal.permissions)
        if "market:read" in permissions:
            permissions.add("tools:market:read")
    else:
        permissions = {"tools:market:read"}
    return ToolPrincipal(workspace_id=principal.workspace_id, permissions=frozenset(permissions))


async def _invoke(
    request: Request,
    principal: RunPrincipal,
    name: str,
    payload: dict[str, object],
) -> object:
    registry = cast(ToolRegistry, request.app.state.market_tool_registry)
    try:
        return await registry.invoke(name, payload, _tool_principal(principal), calls_so_far=0)
    except MarketDataUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="market_data_unavailable") from error
    except ToolTimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="market_data_timeout") from error


@router.post("/quote", response_model=MarketQuoteOutput)
async def quote(
    payload: MarketQuoteInput,
    request: Request,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
) -> MarketQuoteOutput:
    _require_market_permission(principal)
    result = await _invoke(request, principal, "market.quote", payload.model_dump())
    return cast(MarketQuoteOutput, result)


@router.post("/valuation", response_model=MarketValuationOutput)
async def valuation(
    payload: MarketValuationInput,
    request: Request,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
) -> MarketValuationOutput:
    _require_market_permission(principal)
    result = await _invoke(request, principal, "market.valuation", payload.model_dump())
    return cast(MarketValuationOutput, result)


@router.post("/financials", response_model=MarketFinancialsOutput)
async def financials(
    payload: MarketFinancialsInput,
    request: Request,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
) -> MarketFinancialsOutput:
    _require_market_permission(principal)
    result = await _invoke(request, principal, "market.financials", payload.model_dump())
    return cast(MarketFinancialsOutput, result)


@router.post("/dossier", response_model=MarketDossier)
async def dossier(
    payload: MarketDossierInput,
    request: Request,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
) -> MarketDossier:
    """Build the fixed, model-free market fact dossier."""
    _require_market_permission(principal)
    registry = cast(ToolRegistry, request.app.state.market_tool_registry)
    return await build_market_dossier(
        registry=registry,
        principal=_tool_principal(principal),
        symbol=payload.symbol,
    )


@router.post("/debate", response_model=MarketDebateResult)
async def debate(
    payload: MarketDebateInput,
    request: Request,
    principal: Annotated[RunPrincipal, Depends(get_request_principal)],
) -> MarketDebateResult:
    """Run one non-streaming Bull -> Bear -> Moderator sequence."""
    _require_market_permission(principal)
    gateway = request.app.state.market_debate_gateway
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="model_not_configured",
        )
    registry = cast(ToolRegistry, request.app.state.market_tool_registry)
    dossier_result = await build_market_dossier(
        registry=registry,
        principal=_tool_principal(principal),
        symbol=payload.symbol,
    )
    if dossier_result.status == "unavailable":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="market_data_unavailable",
        )
    settings = request.app.state.settings
    try:
        return await run_market_debate(
            dossier=dossier_result,
            gateway=gateway,
            model=settings.chat_model,
            timeout_seconds=settings.agent_model_timeout_seconds,
            ledger=RunUsageLedger(
                max_tokens=settings.model_run_max_tokens,
                max_cost_microusd=settings.model_run_max_cost_microusd,
            ),
        )
    except MarketDebateOutputError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="invalid_model_debate_output",
        ) from error
