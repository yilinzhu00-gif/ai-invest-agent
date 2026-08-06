"""OIDC access-token validation with bounded JWK lookup caching."""

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidTokenError,
    PyJWKClient,
)
from jwt.exceptions import PyJWKClientError

from backend.app.security.principal import Principal


class JwtValidationError(Exception):
    """Safe token-validation error code; never contains the source token."""


@dataclass(frozen=True)
class OidcSettings:
    issuer: str
    audience: str
    clock_skew_seconds: int = 30
    allowed_algorithms: tuple[str, ...] = ("RS256",)
    allowed_token_types: tuple[str, ...] = ("access", "at+jwt")


class BoundedJwkCache:
    """Small LRU cache; unknown key IDs force the resolver so rotation is immediately visible."""

    def __init__(self, resolver: Callable[[str | None], Any], max_entries: int = 8) -> None:
        self.resolver = resolver
        self.max_entries = max_entries
        self._entries: OrderedDict[str, Any] = OrderedDict()

    def resolve(self, kid: str | None) -> Any:
        key_id = kid or ""
        if key_id in self._entries:
            self._entries.move_to_end(key_id)
            return self._entries[key_id]
        key = self.resolver(kid)
        self._entries[key_id] = key
        self._entries.move_to_end(key_id)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
        return key

    def invalidate(self, kid: str | None) -> None:
        self._entries.pop(kid or "", None)


class OidcJwtValidator:
    def __init__(self, settings: OidcSettings, key_resolver: Callable[[str | None], Any]) -> None:
        self.settings = settings
        self.keys = BoundedJwkCache(key_resolver)

    def validate(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid:
                raise JwtValidationError("missing_key_id")
            key = self.keys.resolve(kid)
            claims = jwt.decode(
                token,
                key,
                algorithms=list(self.settings.allowed_algorithms),
                issuer=self.settings.issuer,
                audience=self.settings.audience,
                leeway=self.settings.clock_skew_seconds,
                options={"require": ["sub", "iss", "aud", "exp", "nbf", "jti"]},
            )
        except JwtValidationError:
            raise
        except ExpiredSignatureError as error:
            raise JwtValidationError("token_expired") from error
        except InvalidIssuerError as error:
            raise JwtValidationError("invalid_issuer") from error
        except InvalidAudienceError as error:
            raise JwtValidationError("invalid_audience") from error
        except PyJWKClientError as error:
            raise JwtValidationError("jwk_unavailable") from error
        except InvalidTokenError as error:
            raise JwtValidationError("invalid_token") from error
        token_type = claims.get("typ") or header.get("typ")
        if token_type not in self.settings.allowed_token_types:
            raise JwtValidationError("invalid_token_type")
        if not isinstance(claims.get("scope", ""), str):
            raise JwtValidationError("invalid_scope")
        return claims

    def principal(self, token: str, *, workspace_id: str, roles: frozenset[str], is_human: bool) -> Principal:
        claims = self.validate(token)
        return Principal(
            user_id=str(claims["sub"]),
            active_workspace_id=workspace_id,
            roles=roles,
            permissions=frozenset(str(claims.get("scope", "")).split()),
            token_id=str(claims["jti"]),
            authentication_method="oidc",
            is_human=is_human,
        )


def build_oidc_jwt_validator(
    *, issuer: str, audience: str, jwks_url: str, clock_skew_seconds: int, allowed_token_types: tuple[str, ...] = ("access", "at+jwt")
) -> OidcJwtValidator:
    """Build the production validator backed by the configured OIDC JWK provider."""
    jwk_client = PyJWKClient(jwks_url)
    return OidcJwtValidator(
        OidcSettings(
            issuer=issuer,
            audience=audience,
            clock_skew_seconds=clock_skew_seconds,
            allowed_token_types=allowed_token_types,
        ),
        key_resolver=lambda kid: jwk_client.get_signing_key(kid or "").key,
    )
