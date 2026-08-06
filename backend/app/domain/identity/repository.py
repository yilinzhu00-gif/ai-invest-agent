"""Database lookups for workspace-scoped identities."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.identity.models import WorkspaceMembership


class WorkspaceMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(self, *, workspace_id: str, user_id: str) -> WorkspaceMembership | None:
        result = await self.session.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
