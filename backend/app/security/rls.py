"""PostgreSQL transaction-local RLS context helpers."""

from backend.app.security.principal import Principal


def rls_settings_sql(principal: Principal) -> tuple[tuple[str, dict[str, str]], ...]:
    """Return only transaction-local settings so pooled connections cannot retain identity."""
    return (
        ("SET LOCAL app.current_user_id = :user_id", {"user_id": principal.user_id}),
        (
            "SET LOCAL app.current_workspace_id = :workspace_id",
            {"workspace_id": principal.active_workspace_id},
        ),
    )
