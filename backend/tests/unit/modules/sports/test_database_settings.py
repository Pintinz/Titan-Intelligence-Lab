from __future__ import annotations

import pytest

from modules.sports.infrastructure.persistence.database import DatabaseSettings


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
