"""Fail-closed server-side authorization helpers."""

from backend.app.security.principal import Principal


class AuthorizationError(Exception):
    """The authenticated identity lacks an operation permission."""


def require_permission(principal: Principal, permission: str) -> None:
    if permission not in principal.permissions:
        raise AuthorizationError("permission_denied")
