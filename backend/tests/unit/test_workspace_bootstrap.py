import asyncio
from types import SimpleNamespace

from backend.app.operations.bootstrap_workspace import bootstrap_workspace


class Result:
    def __init__(self, membership: object | None) -> None:
        self.membership = membership

    def scalar_one_or_none(self) -> object | None:
        return self.membership


class Session:
    def __init__(self, membership: object | None = None) -> None:
        self.membership = membership
        self.added: list[object] = []
        self.commits = 0

    async def execute(self, _statement: object) -> Result:
        return Result(self.membership)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1


def test_bootstrap_creates_one_active_membership() -> None:
    session = Session()

    created = asyncio.run(
        bootstrap_workspace(session, workspace_id="workspace-a", user_id="idaas-user-1", role="owner")
    )

    assert created is True
    assert session.commits == 1
    assert len(session.added) == 1
    membership = session.added[0]
    assert membership.workspace_id == "workspace-a"
    assert membership.user_id == "idaas-user-1"
    assert membership.role == "owner"


def test_bootstrap_is_idempotent_for_an_existing_membership() -> None:
    session = Session(SimpleNamespace(workspace_id="workspace-a", user_id="idaas-user-1"))

    created = asyncio.run(
        bootstrap_workspace(session, workspace_id="workspace-a", user_id="idaas-user-1", role="owner")
    )

    assert created is False
    assert session.added == []
    assert session.commits == 0
