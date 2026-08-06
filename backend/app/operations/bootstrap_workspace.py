"""Create the first local workspace membership for an OIDC subject."""

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.domain.identity.models import WorkspaceMembership


async def bootstrap_workspace(
    session: AsyncSession, *, workspace_id: str, user_id: str, role: str
) -> bool:
    """Create one membership once; an existing membership is never overwritten."""
    result = await session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is not None:
        return False
    session.add(WorkspaceMembership(workspace_id=workspace_id, user_id=user_id, role=role, is_human=True))
    await session.commit()
    return True


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} must be set")
    return value


async def _main() -> None:
    database_url = _required_environment("DATABASE_URL")
    workspace_id = _required_environment("BOOTSTRAP_WORKSPACE_ID")
    user_id = _required_environment("BOOTSTRAP_USER_ID")
    role = os.environ.get("BOOTSTRAP_WORKSPACE_ROLE", "owner")
    if role not in {"owner", "admin", "analyst", "reviewer"}:
        raise SystemExit("BOOTSTRAP_WORKSPACE_ROLE must be owner, admin, analyst, or reviewer")
    async_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
    engine = create_async_engine(async_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            created = await bootstrap_workspace(
                session, workspace_id=workspace_id, user_id=user_id, role=role
            )
    finally:
        await engine.dispose()
    print("workspace membership created" if created else "workspace membership already exists")


if __name__ == "__main__":
    asyncio.run(_main())
