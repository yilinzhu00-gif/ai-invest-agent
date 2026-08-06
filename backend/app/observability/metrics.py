from prometheus_client import Counter

_FORBIDDEN_LABELS = {"user_id", "workspace_id", "run_id", "document_id", "trace_id"}

HTTP_REQUESTS = Counter(
    "investment_agent_http_requests",
    "Completed HTTP requests observed by the API process.",
    ("method", "status"),
)


def safe_metric_labels(labels: dict[str, str]) -> dict[str, str]:
    if _FORBIDDEN_LABELS.intersection(labels):
        raise ValueError("high_cardinality_label")
    return dict(labels)
