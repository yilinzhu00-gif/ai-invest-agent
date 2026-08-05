"""Lazy async SQLAlchemy engine and request-scoped session dependencies."""

from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.core.config import Settings


def create_database_engine(settings: Settings) -> AsyncEngine:
    """Build an asyncpg engine only when a database operation requires one."""
    database_url = settings.async_database_url
    if database_url is None:
        raise RuntimeError("DATABASE_URL is required for database operations")
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args={"timeout": settings.db_connect_timeout},
    )


def create_session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    """Create a non-autocommitting session factory for one application instance."""
    return async_sessionmaker(create_database_engine(settings), expire_on_commit=False)


def _get_request_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        engine = create_database_engine(request.app.state.settings)
        request.app.state.db_engine = engine
        factory = async_sessionmaker(engine, expire_on_commit=False)
        request.app.state.db_session_factory = factory
    return factory


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an independent session and close it once its request completes."""
    session_factory = _get_request_session_factory(request)
    async with session_factory() as session:
        yield session


async def dispose_database_engine(app: FastAPI) -> None:
    """Release a lazily-created application engine at shutdown."""
    engine = getattr(app.state, "db_engine", None)
    if engine is not None:
        await engine.dispose()
