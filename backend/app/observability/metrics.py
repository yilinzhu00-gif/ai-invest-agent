_FORBIDDEN_LABELS = {"user_id", "workspace_id", "run_id", "document_id", "trace_id"}


def safe_metric_labels(labels: dict[str, str]) -> dict[str, str]:
    if _FORBIDDEN_LABELS.intersection(labels):
        raise ValueError("high_cardinality_label")
    return dict(labels)
