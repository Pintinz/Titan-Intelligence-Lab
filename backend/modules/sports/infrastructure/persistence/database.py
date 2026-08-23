"""Async engine/session factory. DATABASE_URL is validated at startup (fail fast on missing
config, per docs/architecture.md §10) rather than defaulting silently to a local database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import Pool


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TITANIQ_DB_")

    url: str
    echo: bool = False
    pool_size: int = 10
    # Recycles a connection SQLAlchemy hasn't verified is still alive before handing it to a
    # caller (a real production gap without this — a Postgres failover or an idle-connection
    # timeout on the DB side previously surfaced as a runtime error mid-request instead of being
    # transparently recycled, Production Readiness Audit §1). SQLite has no server-side connection
    # to go stale, so this only applies on the Postgres branch below.
    max_overflow: int = 5

    @field_validator("url")
    @classmethod
    def _use_asyncpg_driver(cls, value: str) -> str:
        """Every managed-Postgres provider (Render included) hands out a plain `postgresql://` or
        `postgres://` connection string — psycopg2-flavored, the sync-driver default — but this
        app is built entirely on SQLAlchemy's async engine, which needs `postgresql+asyncpg://`
        explicitly. Rewriting it here means pasting a provider's connection string straight into
        TITANIQ_DB_URL just works, instead of silently trying to load a sync driver this app
        never installs and failing at engine-creation time with a confusing DBAPI import error."""
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value[len("postgresql://") :]
        return value


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
    "alerts",
    "billing",
    "features",
    "identity",
    "ingestion",
    "intelligence",
    "knowledge_graph",
    "predictions",
    "sports",
    "tenancy",
    "watchlist",
    "webhooks",
]


def build_engine(
    settings: DatabaseSettings | None = None, *, poolclass: type[Pool] | None = None
) -> AsyncEngine:
    """`poolclass` overrides the default pool (e.g. `NullPool` for a caller like the Celery worker
    that invokes a fresh `asyncio.run()` event loop per call — pooled DBAPI connections are bound
    to the loop that created them, so reusing one across loops raises `RuntimeError: Event loop is
    closed`). Left `None`, callers get today's default pooling unchanged."""
    settings = settings or get_database_settings()
    if settings.url.startswith("sqlite"):
        kwargs: dict = {
            "echo": settings.echo,
            "execution_options": {"schema_translate_map": dict.fromkeys(_ALL_SCHEMAS)},
        }
    else:
        kwargs = {
            "echo": settings.echo,
            "pool_size": settings.pool_size,
            "max_overflow": settings.max_overflow,
            "pool_pre_ping": True,
            # Real prod incident (2026-08-23): TITANIQ_DB_URL pointed at Supabase's port-5432
            # "session mode" pooler, which caps at 15 total connections shared across every
            # client — 4 uvicorn workers each independently maintaining pool_size+max_overflow=15
            # blew straight through that ceiling under any real concurrency, surfacing as
            # `asyncpg.exceptions.InternalServerError: EMAXCONNSESSION ... max clients are limited
            # to pool_size: 15` (crashed the alembic migration step outright) and
            # `sqlalchemy.exc.TimeoutError: QueuePool limit ... reached` under live request load.
            # Port 6543 ("transaction mode") is Supabase's own documented fix for exactly this
            # multi-connection app-server shape — but PgBouncer transaction pooling doesn't
            # reliably support server-side prepared statements across different backend
            # connections (a "session" can land on a different real Postgres connection per
            # transaction), so asyncpg's statement cache has to be disabled to be compatible with
            # it. Harmless on a direct (non-pooled) connection too, so this is safe regardless of
            # which port TITANIQ_DB_URL ends up using.
            "connect_args": {"statement_cache_size": 0},
        }
    if poolclass is not None:
        # NullPool (the one real caller of this override, the Celery worker) manages no pool at
        # all, so it accepts neither pool_size nor max_overflow — only pool_pre_ping is compatible
        # with it, and is left in place since it's still meaningful per-connection there.
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        kwargs["poolclass"] = poolclass
    return create_async_engine(settings.url, **kwargs)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
