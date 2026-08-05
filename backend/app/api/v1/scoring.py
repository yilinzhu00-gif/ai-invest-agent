from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.domain.scoring.schemas import ScoringEvaluationRequest, ScoringEvaluationResponse
from backend.app.domain.scoring.service import ScoringService, get_scoring_service

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.post("/evaluate", response_model=ScoringEvaluationResponse)
def evaluate_scoring(
    payload: ScoringEvaluationRequest,
    service: Annotated[ScoringService, Depends(get_scoring_service)],
) -> ScoringEvaluationResponse:
    return service.evaluate(payload.metrics)
