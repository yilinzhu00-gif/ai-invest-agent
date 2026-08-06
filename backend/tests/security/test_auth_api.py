import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.domain.identity.models import WorkspaceMembership
from backend.app.main import create_app
from backend.app.security.authentication import OidcJwtValidator, OidcSettings


def test_production_rejects_development_principal_headers() -> None:
    client = TestClient(
        create_app(
            Settings(
                app_env="production",
                database_url="postgresql://unused",
                oidc_issuer="https://issuer.example",
                oidc_audience="investment-api",
                oidc_jwks_url="https://issuer.example/.well-known/jwks.json",
            )
        )
    )
    response = client.post(
        "/api/v1/agent/runs",
        json={"question": "test"},
        headers={"X-Development-Principal-ID": "user", "X-Development-Workspace-ID": "workspace"},
    )
    assert response.status_code == 401


def test_production_requires_an_explicit_oidc_jwk_provider() -> None:
    with pytest.raises(ValueError, match="OIDC_ISSUER"):
        Settings(app_env="production", database_url="postgresql://unused")


def test_oidc_dependency_builds_principal_from_active_workspace_membership() -> None:
    """A valid bearer token must not grant a workspace role without an active local membership."""
    from backend.app.api.v1.agent_runs import get_authenticated_principal

    signing_key = "test-signing-key-with-at-least-thirty-two-bytes"
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "user-1",
            "iss": "https://issuer.example",
            "aud": "investment-api",
            "exp": now + timedelta(minutes=5),
            "nbf": now - timedelta(seconds=1),
            "jti": "token-1",
            "scope": "agent:run",
            "typ": "access",
        },
        signing_key,
        algorithm="HS256",
        headers={"kid": "test-key"},
    )
    validator = OidcJwtValidator(
        OidcSettings(
            issuer="https://issuer.example", audience="investment-api", allowed_algorithms=("HS256",)
        ),
        key_resolver=lambda _kid: signing_key,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=Settings(
                app_env="production",
                database_url="postgresql://unused",
                oidc_issuer="https://issuer.example",
                oidc_audience="investment-api",
                oidc_jwks_url="https://issuer.example/.well-known/jwks.json",
            ),
            oidc_validator=validator,
        )
    )
    request = Request({"type": "http", "app": app, "headers": []})
    membership = WorkspaceMembership(
        workspace_id="workspace-a", user_id="user-1", role="analyst", is_human=True
    )

    class Result:
        def scalar_one_or_none(self) -> WorkspaceMembership:
            return membership

    class Session:
        async def execute(self, _statement: object) -> Result:
            return Result()

    principal = asyncio.run(
        get_authenticated_principal(
            request=request,
            session=Session(),  # type: ignore[arg-type]
            authorization=f"Bearer {token}",
            workspace_id="workspace-a",
        )
    )

    assert principal.user_id == "user-1"
    assert principal.active_workspace_id == "workspace-a"
    assert principal.roles == frozenset({"analyst"})
    assert principal.permissions == frozenset({"agent:run"})


def test_oidc_validator_accepts_rfc9068_access_token_type() -> None:
    signing_key = "test-signing-key-with-at-least-thirty-two-bytes"
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "user-1",
            "iss": "https://issuer.example",
            "aud": "investment-api",
            "exp": now + timedelta(minutes=5),
            "nbf": now - timedelta(seconds=1),
            "jti": "token-1",
            "scope": "agent:run",
        },
        signing_key,
        algorithm="HS256",
        headers={"kid": "test-key", "typ": "at+jwt"},
    )
    validator = OidcJwtValidator(
        OidcSettings(
            issuer="https://issuer.example", audience="investment-api", allowed_algorithms=("HS256",)
        ),
        key_resolver=lambda _kid: signing_key,
    )

    assert validator.validate(token)["sub"] == "user-1"
