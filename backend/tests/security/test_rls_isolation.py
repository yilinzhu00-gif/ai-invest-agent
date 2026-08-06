from backend.app.security.principal import Principal
from backend.app.security.rls import rls_settings_sql


def test_rls_settings_use_transaction_local_context() -> None:
    principal = Principal(
        user_id="user-1",
        active_workspace_id="workspace-a",
        roles=frozenset({"analyst"}),
        permissions=frozenset({"agent:run"}),
        token_id="token-1",
        authentication_method="oidc",
        is_human=True,
    )

    statements = rls_settings_sql(principal)

    assert statements == (
        ("SET LOCAL app.current_user_id = :user_id", {"user_id": "user-1"}),
        ("SET LOCAL app.current_workspace_id = :workspace_id", {"workspace_id": "workspace-a"}),
    )
