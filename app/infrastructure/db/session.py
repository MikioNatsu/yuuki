from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import Settings


def build_async_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.postgres_dsn_plain(),
        pool_pre_ping=True,
        pool_size=int(settings.db_pool_size),
        max_overflow=int(settings.db_max_overflow),
        pool_timeout=int(settings.db_pool_timeout_seconds),
        connect_args={"command_timeout": int(settings.db_command_timeout_seconds)},
    )


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False, autocommit=False)
