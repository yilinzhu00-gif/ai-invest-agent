"""Database readiness checks that deliberately do not expose connection details."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.core.config import Settings
from backend.app.db.session import create_database_engine

CURRENT_ALEMBIC_REVISION = "20260805_p1_04"


async def is_database_ready(settings: Settings) -> bool:
    """Confirm the database is reachable and has the current Alembic revision."""
    if settings.database_url is None:
        return False

    engine = None
    try:
        engine = create_database_engine(settings)
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            return result.scalar_one_or_none() == CURRENT_ALEMBIC_REVISION
    except (OSError, TimeoutError, SQLAlchemyError):
        # Database driver errors must become a safe readiness response.
        return False
    finally:
        if engine is not None:
            await engine.dispose()
