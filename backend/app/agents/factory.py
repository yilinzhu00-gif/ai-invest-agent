"""Composition root for the constrained Analyst -> Validator -> Reviewer flow."""

from typing import cast

from openai import OpenAI

from backend.app.agents.analyst import ResearchAnalyst
from backend.app.agents.concrete import (
    EvidenceBoundAnalyst,
    EvidenceReviewer,
    RunUsageLedger,
    StructuredModelAnalyst,
    StructuredModelReviewer,
)
from backend.app.agents.flow import ControlledResearchFlow, FlowObserver
from backend.app.agents.reviewer import EvidenceReviewer as EvidenceReviewerProtocol
from backend.app.agents.validators import EvidenceValidator
from backend.app.core.config import Settings
from backend.app.models.openai_compatible import OpenAICompatibleClient, OpenAICompatibleGateway


def build_research_flow(settings: Settings, observer: FlowObserver | None = None) -> ControlledResearchFlow:
    """Build one run-local flow; model credentials are never stored on a Run."""
    analyst: ResearchAnalyst
    reviewer: EvidenceReviewerProtocol
    if settings.agent_execution_mode == "deterministic":
        analyst = EvidenceBoundAnalyst()
        reviewer = EvidenceReviewer()
    else:
        assert settings.model_api_key is not None  # Settings validates this invariant.
        client = OpenAI(
            api_key=settings.model_api_key.get_secret_value(),
            base_url=settings.model_base_url,
        )
        gateway = OpenAICompatibleGateway(
            cast(OpenAICompatibleClient, client), provider=settings.model_provider
        )
        ledger = RunUsageLedger(
            max_tokens=settings.model_run_max_tokens,
            max_cost_microusd=settings.model_run_max_cost_microusd,
        )
        analyst = StructuredModelAnalyst(
            gateway=gateway,
            model=settings.chat_model,
            timeout_seconds=settings.agent_model_timeout_seconds,
            ledger=ledger,
        )
        reviewer = StructuredModelReviewer(
            gateway=gateway,
            model=settings.review_model,
            timeout_seconds=settings.agent_model_timeout_seconds,
            ledger=ledger,
        )
    return ControlledResearchFlow(
        analyst=analyst,
        validator=EvidenceValidator(),
        reviewer=reviewer,
        max_revisions=settings.agent_max_revisions,
        observer=observer,
    )
