from __future__ import annotations

from unittest.mock import patch

import pytest

from modules.sports.infrastructure.persistence.database import DatabaseSettings, build_engine


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://user:pass@host/db", "postgresql+asyncpg://user:pass@host/db"),
        ("postgresql://user:pass@host/db", "postgresql+asyncpg://user:pass@host/db"),
        ("postgresql+asyncpg://user:pass@host/db", "postgresql+asyncpg://user:pass@host/db"),
        ("sqlite+aiosqlite:///./dev.db", "sqlite+aiosqlite:///./dev.db"),
    ],
)
def test_url_normalizes_to_the_asyncpg_driver(raw: str, expected: str) -> None:
    """Every managed-Postgres provider (Render included) hands out a plain postgres(ql):// string
    — this app's async SQLAlchemy engine needs the +asyncpg driver explicit, or engine creation
    fails trying to load a sync driver this app never installs."""
    settings = DatabaseSettings(url=raw)
    assert settings.url == expected


def test_postgres_engine_disables_the_asyncpg_statement_cache() -> None:
    """Real prod incident (2026-08-23): Supabase's transaction-mode pooler (the fix for the
    session-mode pooler's 15-connection ceiling that was crashing migrations and timing out
    requests under load) doesn't reliably support server-side prepared statements across
    different backend connections — asyncpg's statement cache has to be disabled to be
    compatible with it, harmless whether or not the URL is actually pooled."""
    settings = DatabaseSettings(url="postgresql://user:pass@host/db")
    with patch("modules.sports.infrastructure.persistence.database.create_async_engine") as mock_create:
        build_engine(settings)
    assert mock_create.call_args.kwargs["connect_args"]["statement_cache_size"] == 0


def test_postgres_engine_sets_a_bounded_command_timeout() -> None:
    """Real prod incident (2026-08-30): ingestion.sync_completed_fixtures runs sat in
    SyncStatus.RUNNING for 20+ minutes, blowing straight through SyncOrchestrator's own 120s
    asyncio.wait_for bound — reproduced through both the Celery worker and a direct API-triggered
    run, narrowing it to a stalled DB call with no timeout of its own (asyncpg has none by
    default), unlike every other I/O client in this codebase (httpx, Redis)."""
    settings = DatabaseSettings(url="postgresql://user:pass@host/db")
    with patch("modules.sports.infrastructure.persistence.database.create_async_engine") as mock_create:
        build_engine(settings)
    assert mock_create.call_args.kwargs["connect_args"]["command_timeout"] == 30


def test_sqlite_engine_does_not_set_postgres_only_options() -> None:
    """SQLite has no connection pool, no PgBouncer, and no asyncpg driver to configure — the
    Postgres-only kwargs (pool_size, connect_args, ...) must never leak onto this branch."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///./dev.db")
    with patch("modules.sports.infrastructure.persistence.database.create_async_engine") as mock_create:
        build_engine(settings)
    assert "connect_args" not in mock_create.call_args.kwargs
    assert "pool_size" not in mock_create.call_args.kwargs
