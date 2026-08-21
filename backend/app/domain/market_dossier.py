"""Deterministic market fact dossier built from the first public-data tools."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.tools.market_data import (
    MarketDataUnavailableError,
    MarketFinancialsInput,
    MarketQuoteInput,
    MarketValuationInput,
)
from backend.app.tools.policy import ToolPrincipal
from backend.app.tools.registry import ToolRegistry, ToolTimeoutError

DossierSectionStatus = Literal["ready", "partial", "missing", "error"]
DossierStatus = Literal["ready", "partial", "unavailable"]


class MarketDossierInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^[0-9]{6}$")


class MarketDossierSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    tool: str
    status: DossierSectionStatus
    data: dict[str, Any] | None = None
    missing_fields: list[str] = Field(default_factory=list)
    error_code: str | None = None


class MarketDossier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^[0-9]{6}$")
    generated_at: datetime
    status: DossierStatus
    sections: list[MarketDossierSection] = Field(min_length=3, max_length=3)
    missing_sections: list[str] = Field(default_factory=list)
    boundary: str = (
        "该底稿只整理当前取得的公开观测，不预测未来走势，不生成买卖建议、目标价或评级。"
    )


_DOSSIER_SPEC: tuple[tuple[str, str, str], ...] = (
    ("quote", "实时行情", "market.quote"),
    ("valuation", "估值与一致预期", "market.valuation"),
    ("financials", "最新报告期财务指标", "market.financials"),
)


def _payload(key: str, symbol: str) -> dict[str, object]:
    if key == "quote":
        return MarketQuoteInput(codes=[symbol]).model_dump()
    if key == "valuation":
        return MarketValuationInput(symbol=symbol).model_dump()
    return MarketFinancialsInput(symbol=symbol).model_dump()


def _section_data(result: object) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(result, BaseModel):
        raise TypeError("market tool result must be a Pydantic model")
    data = result.model_dump(mode="json")
    missing = data.get("missing_fields")
    return data, list(missing) if isinstance(missing, list) else []


async def build_market_dossier(
    *, registry: ToolRegistry, principal: ToolPrincipal, symbol: str
) -> MarketDossier:
    """Run the fixed tool list in order and preserve every data gap explicitly."""
    sections: list[MarketDossierSection] = []
    for key, title, tool_name in _DOSSIER_SPEC:
        try:
            result = await registry.invoke(
                tool_name,
                _payload(key, symbol),
                principal,
                # Each fixed tool appears once in this dossier; this is its
                # first invocation within the bounded tool contract.
                calls_so_far=0,
            )
            data, missing = _section_data(result)
            status: DossierSectionStatus = "partial" if missing else "ready"
            sections.append(
                MarketDossierSection(
                    key=key,
                    title=title,
                    tool=tool_name,
                    status=status,
                    data=data,
                    missing_fields=missing,
                )
            )
        except MarketDataUnavailableError:
            sections.append(
                MarketDossierSection(
                    key=key,
                    title=title,
                    tool=tool_name,
                    status="missing",
                    error_code="market_data_unavailable",
                )
            )
        except ToolTimeoutError:
            sections.append(
                MarketDossierSection(
                    key=key,
                    title=title,
                    tool=tool_name,
                    status="error",
                    error_code="market_data_timeout",
                )
            )

    missing_sections = [
        section.key for section in sections if section.status in {"missing", "error"}
    ]
    if all(section.status in {"missing", "error"} for section in sections):
        dossier_status: DossierStatus = "unavailable"
    elif any(section.status in {"partial", "missing", "error"} for section in sections):
        dossier_status = "partial"
    else:
        dossier_status = "ready"
    return MarketDossier(
        symbol=symbol,
        generated_at=datetime.now(UTC),
        status=dossier_status,
        sections=sections,
        missing_sections=missing_sections,
    )
