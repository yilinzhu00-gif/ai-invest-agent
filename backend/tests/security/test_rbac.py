from datetime import UTC, datetime, timedelta

import jwt
import pytest

from backend.app.security.authentication import JwtValidationError, OidcJwtValidator, OidcSettings
from backend.app.security.authorization import AuthorizationError, require_permission
from backend.app.security.principal import Principal


def _principal(*, roles: frozenset[str] = frozenset({"analyst"})) -> Principal:
    return Principal(
        user_id="user-1",
        active_workspace_id="workspace-a",
        roles=roles,
        permissions=frozenset({"agent:run", "document:upload"}),
        token_id="token-1",
        authentication_method="oidc",
        is_human=True,
    )


def test_role_permissions_are_enforced_server_side() -> None:
    require_permission(_principal(), "agent:run")

    with pytest.raises(AuthorizationError, match="permission_denied"):
        require_permission(_principal(), "workspace:manage")


def test_admin_role_is_rejected_for_non_human_principals() -> None:
    with pytest.raises(ValueError, match="human"):
        Principal(
            user_id="agent-1",
            active_workspace_id="workspace-a",
            roles=frozenset({"admin"}),
            permissions=frozenset({"workspace:manage"}),
            token_id="token-1",
            authentication_method="oidc",
            is_human=False,
        )


def test_oidc_validator_rejects_expired_or_wrong_audience_tokens() -> None:
    settings = OidcSettings(
        issuer="https://issuer.example", audience="investment-api", allowed_algorithms=("HS256",)
    )
    signing_key = "test-signing-key-with-at-least-thirty-two-bytes"
    validator = OidcJwtValidator(settings, key_resolver=lambda _kid: signing_key)
    now = datetime.now(UTC)
    expired = jwt.encode(
        {"sub": "user-1", "iss": settings.issuer, "aud": settings.audience, "exp": now - timedelta(minutes=1), "nbf": now - timedelta(minutes=2), "jti": "token-1", "scope": "agent:run", "typ": "access"},
        signing_key,
        algorithm="HS256",
        headers={"kid": "test-key"},
    )

    with pytest.raises(JwtValidationError, match="token_expired"):
        validator.validate(expired)


def test_oidc_validator_rejects_a_token_without_a_jwk_key_id() -> None:
    settings = OidcSettings(
        issuer="https://issuer.example", audience="investment-api", allowed_algorithms=("HS256",)
    )
    signing_key = "test-signing-key-with-at-least-thirty-two-bytes"
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "user-1",
            "iss": settings.issuer,
            "aud": settings.audience,
            "exp": now + timedelta(minutes=5),
            "nbf": now - timedelta(seconds=1),
            "jti": "token-1",
            "scope": "agent:run",
            "typ": "access",
        },
        signing_key,
        algorithm="HS256",
    )
    validator = OidcJwtValidator(settings, key_resolver=lambda _kid: signing_key)

    with pytest.raises(JwtValidationError, match="missing_key_id"):
        validator.validate(token)
