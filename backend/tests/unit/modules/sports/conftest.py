"""Test fixtures for the sports module.

Repository tests run against an in-memory SQLite engine with a schema_translate_map that
maps the `sports` Postgres schema to SQLite's unqualified default schema — this lets the same
model definitions used against Postgres in every real environment run in CI without a live
Postgres instance (see infrastructure/persistence/models.py docstring).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from modules.sports.bootstrap import build_sport_plugin_registry
from modules.sports.infrastructure.persistence.models import Base


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        execution_options={"schema_translate_map": {"sports": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def plugin_registry():
    return build_sport_plugin_registry()
