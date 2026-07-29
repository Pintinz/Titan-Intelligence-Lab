"""Shared fixtures for the live Supabase integration test tier (docs/supabase.md).

This tier is SEPARATE from ``tests/unit`` (docs/roadmap.md Milestone 6 requirement: "keep the
existing SQLite/fakeredis test suite for fast unit tests; add a SEPARATE integration test suite
against the live Supabase project — do NOT replace the fast local tests"). It is gated behind
real credentials via environment variables and is skipped entirely — not failed — when they
are absent, so ``pytest`` (no args) and CI runs without live secrets never break:

  TITANIQ_INTEGRATION_DB_URL        postgresql+asyncpg://... with the REAL database password
                                     (Settings -> Database on the Supabase dashboard). Distinct
                                     from TITANIQ_DB_URL so the fast suite's SQLite config and
                                     this tier's live Postgres config can never collide.
  TITANIQ_SUPABASE_PROJECT_URL      e.g. https://irhnoilyaqgewfidhunx.supabase.co
  TITANIQ_SUPABASE_ANON_KEY         the project's anon/publishable key (Settings -> API).
                                     Public by design, but still sourced from the environment,
                                     never hardcoded, to keep this tier portable across projects.

None of these are ever fabricated by the assistant — same secrets-handling rule as
TITANIQ_REDIS_URL/TITANIQ_ENCRYPTION_KEY elsewhere in this codebase.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import asyncpg
import httpx
import pytest
import pytest_asyncio

DB_URL = os.environ.get("TITANIQ_INTEGRATION_DB_URL")
SUPABASE_PROJECT_URL = os.environ.get("TITANIQ_SUPABASE_PROJECT_URL")
SUPABASE_ANON_KEY = os.environ.get("TITANIQ_SUPABASE_ANON_KEY")

HAS_DB_CREDENTIALS = bool(DB_URL)
HAS_SUPABASE_CREDENTIALS = bool(SUPABASE_PROJECT_URL and SUPABASE_ANON_KEY)

requires_db = pytest.mark.skipif(
    not HAS_DB_CREDENTIALS,
    reason="TITANIQ_INTEGRATION_DB_URL not set — skipping live-database integration tests",
)
requires_supabase_api = pytest.mark.skipif(
    not HAS_SUPABASE_CREDENTIALS,
    reason="TITANIQ_SUPABASE_PROJECT_URL/TITANIQ_SUPABASE_ANON_KEY not set — skipping live Supabase API tests",
)


def _asyncpg_dsn(url: str) -> str:
    """Alembic/SQLAlchemy URLs use the ``postgresql+asyncpg://`` scheme; asyncpg's own
    ``connect()`` wants a bare ``postgresql://`` DSN."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest_asyncio.fixture
async def db_connection() -> AsyncIterator[asyncpg.Connection]:
    if not HAS_DB_CREDENTIALS:
        pytest.skip("TITANIQ_INTEGRATION_DB_URL not set")
    conn = await asyncpg.connect(_asyncpg_dsn(DB_URL))
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
def supabase_client() -> httpx.Client:
    if not HAS_SUPABASE_CREDENTIALS:
        pytest.skip("TITANIQ_SUPABASE_PROJECT_URL/TITANIQ_SUPABASE_ANON_KEY not set")
    return httpx.Client(
        base_url=SUPABASE_PROJECT_URL,
        headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
        timeout=15.0,
    )


@pytest.fixture
def unique_test_email() -> str:
    return f"integration-test-{uuid.uuid4().hex[:12]}@titaniq-test.local"
