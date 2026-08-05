from backend.app.domain.scoring.schemas import ScoringEvaluationResponse
from scoring import evaluate_score


class ScoringService:
    """Adapt the established root scorer to the HTTP domain contract."""

    def evaluate(self, metrics: dict[str, float | None]) -> ScoringEvaluationResponse:
        return ScoringEvaluationResponse.model_validate(evaluate_score(metrics))


def get_scoring_service() -> ScoringService:
    return ScoringService()
