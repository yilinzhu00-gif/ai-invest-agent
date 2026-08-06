"""Immutable authenticated identity passed through every protected boundary."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    user_id: str
    active_workspace_id: str
    roles: frozenset[str]
    permissions: frozenset[str]
    token_id: str
    authentication_method: str
    is_human: bool

    def __post_init__(self) -> None:
        if "admin" in self.roles and not self.is_human:
            raise ValueError("admin role requires a human principal")
