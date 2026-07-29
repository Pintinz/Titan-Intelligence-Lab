"""Async engine/session factory. DATABASE_URL is validated at startup (fail fast on missing
config, per docs/architecture.md §10) rather than defaulting silently to a local database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TITANIQ_DB_")

    url: str
    echo: bool = False
    pool_size: int = 10


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()  # type: ignore[call-arg]  # raises if TITANIQ_DB_URL is unset


# Every module schema in the system (mirrors the MetaData(schema=...) declared by each module's
# infrastructure/persistence/models.py). SQLite has no multi-schema support, so local dev against
# sqlite+aiosqlite:// (docs/deployment.md §1's documented fallback when no Postgres password is
# available) needs these collapsed to SQLite's single default namespace — the same
# schema_translate_map technique the test suite already uses per-module (e.g.
# tests/unit/modules/sports/conftest.py), just applied across all of them for the real engine.
_ALL_SCHEMAS = [
    "admin",
    "billing",
    "features",
    "identity",
    "ingestion",
    "intelligence",
    "knowledge_graph",
    "predictions",
    "sports",
    "tenancy",
    "webhooks",
]


def build_engine(settings: DatabaseSettings | None = None) -> AsyncEngine:
    settings = settings or get_database_settings()
    if settings.url.startswith("sqlite"):
        return create_async_engine(
            settings.url,
            echo=settings.echo,
            execution_options={"schema_translate_map": dict.fromkeys(_ALL_SCHEMAS)},
        )
    return create_async_engine(settings.url, echo=settings.echo, pool_size=settings.pool_size)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
