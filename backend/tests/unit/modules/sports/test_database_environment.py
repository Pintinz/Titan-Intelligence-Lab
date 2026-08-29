import os

import pytest

from modules.sports.infrastructure.persistence.database import DatabaseSettings, Environment, get_environment


@pytest.fixture(autouse=True)
def _clear_environment_override(monkeypatch):
    monkeypatch.delenv("TITANIQ_ENVIRONMENT", raising=False)


def test_get_environment_defaults_to_development():
    assert get_environment() is Environment.DEVELOPMENT


def test_get_environment_reads_the_env_var(monkeypatch):
    monkeypatch.setenv("TITANIQ_ENVIRONMENT", "production")
    assert get_environment() is Environment.PRODUCTION


def test_get_environment_rejects_an_unknown_value(monkeypatch):
    monkeypatch.setenv("TITANIQ_ENVIRONMENT", "prod")  # not one of the three real values

    with pytest.raises(RuntimeError, match="not one of"):
        get_environment()


def test_sqlite_is_allowed_in_development():
    settings = DatabaseSettings(url="sqlite+aiosqlite:///./dev.db")
    assert settings.url.startswith("sqlite")


def test_sqlite_is_rejected_in_staging(monkeypatch):
    monkeypatch.setenv("TITANIQ_ENVIRONMENT", "staging")

    with pytest.raises(RuntimeError, match="refusing to start"):
        DatabaseSettings(url="sqlite+aiosqlite:///./dev.db")


def test_sqlite_is_rejected_in_production(monkeypatch):
    monkeypatch.setenv("TITANIQ_ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="refusing to start"):
        DatabaseSettings(url="sqlite+aiosqlite:///./dev.db")


def test_postgres_is_allowed_in_production(monkeypatch):
    monkeypatch.setenv("TITANIQ_ENVIRONMENT", "production")

    settings = DatabaseSettings(url="postgresql://user:pass@example.supabase.co:5432/postgres")

    assert settings.url.startswith("postgresql+asyncpg://")
