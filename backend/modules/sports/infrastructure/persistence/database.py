"""Async engine/session factory. DATABASE_URL is validated at startup (fail fast on missing
config, per docs/architecture.md §10) rather than defaulting silently to a local database.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from enum import Enum
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import Pool


class Environment(str, Enum):
    """`TITANIQ_ENVIRONMENT` — absent anywhere in this codebase before 2026-08-29, the exact gap
    that let a staging deployment be mistaken for production and a local script be run without
    anyone being able to check, in code, which database it was actually about to touch."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


def get_environment() -> Environment:
    """Defaults to DEVELOPMENT — the same "fail toward the safer, more restrictive local
    default" posture `DatabaseSettings.url` already has (required, no default), not toward the
    default that would silently grant production-level trust to an unconfigured process."""
    raw = os.environ.get("TITANIQ_ENVIRONMENT", "development").strip().lower()
    try:
        return Environment(raw)
    except ValueError:
        valid = ", ".join(e.value for e in Environment)
        raise RuntimeError(f"TITANIQ_ENVIRONMENT={raw!r} is not one of: {valid}") from None


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TITANIQ_DB_")

    url: str
    echo: bool = False
    # Real prod incident (2026-08-23): these were sized as if 10+5=15 was this *worker's own*
    # generous budget — actually the full ceiling Supabase's port-5432 "session mode" pooler
    # allowed *shared across every worker and every other client*. Once TITANIQ_DB_URL moved to
    # port 6543 ("transaction mode" — much higher effective capacity, Supabase's own documented
    # fix for a multi-connection app server), the same 10+5 became the bottleneck one level down:
    # `sqlalchemy.exc.TimeoutError: QueuePool limit of size 10 overflow 5 reached` under real
    # concurrent load, since 4 uvicorn workers each independently cap out this low with pages like
    # Team/Player/Competition Intelligence firing 5-6 concurrent queries per load. Raised now that
    # the upstream constraint that justified the old low value is gone; still well under a
    # transaction-mode pooler's real ceiling even across all 4 workers (4 * (20+10) = 120 total).
    pool_size: int = 20
    # Recycles a connection SQLAlchemy hasn't verified is still alive before handing it to a
    # caller (a real production gap without this — a Postgres failover or an idle-connection
    # timeout on the DB side previously surfaced as a runtime error mid-request instead of being
    # transparently recycled, Production Readiness Audit §1). SQLite has no server-side connection
    # to go stale, so this only applies on the Postgres branch below.
    max_overflow: int = 10

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

    @model_validator(mode="after")
    def _no_sqlite_outside_development(self) -> "DatabaseSettings":
        """The fail-fast this module's own docstring already claimed but never actually enforced
        beyond "TITANIQ_DB_URL must be set to *something*" — a staging or production process
        pointed at sqlite (by a copy-pasted local .env, an unset TITANIQ_DB_URL falling through to
        some other default, etc.) previously started up successfully and served real traffic
        against a throwaway local file. Scoped to TITANIQ_ENVIRONMENT, not a database-type ban:
        local development against sqlite (docs/deployment.md §1's documented zero-Postgres-needed
        default) is unaffected."""
        if self.url.startswith("sqlite") and get_environment() is not Environment.DEVELOPMENT:
            raise RuntimeError(
                f"TITANIQ_ENVIRONMENT={get_environment().value!r} but TITANIQ_DB_URL points at "
                "sqlite — refusing to start. A staging or production process must never silently "
                "serve real traffic against a local throwaway database."
            )
        return self


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
