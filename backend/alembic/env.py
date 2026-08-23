"""Alembic environment. Reads TITANIQ_DB_URL the same way the application does
(modules.sports.infrastructure.persistence.database.DatabaseSettings) — one source of
truth for the connection string, no separate migration-only config.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from modules.sports.infrastructure.persistence.database import get_database_settings
from modules.sports.infrastructure.persistence.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return get_database_settings().url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=target_metadata.schema,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    # Bootstrap gap found running this against a genuinely fresh Postgres for the first time
    # (2026-08-21): Alembic creates its own `version_table_schema` bookkeeping table BEFORE
    # invoking any real migration — including 0001, the one that would otherwise create this
    # schema. On a brand-new database with no schemas at all, that's a chicken-and-egg failure
    # (`InvalidSchemaNameError: schema "sports" does not exist`) no migration script can fix,
    # since none of them get a chance to run first. `alembic_version` staying inside `sports`
    # (not `public`) is deliberate — see 0010_row_level_security.py's RLS coverage and
    # tests/integration/test_database.py's own assertion — so the fix is ensuring the schema
    # exists here, before Alembic's bootstrap, not relocating the table.
    if connection.dialect.name == "postgresql":
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS sports"))

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=target_metadata.schema,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    url = get_url()
    configuration["sqlalchemy.url"] = url
    # Same asyncpg/PgBouncer-transaction-pooler compatibility fix as
    # database.py::build_engine() — the migration's engine is built independently here, so it
    # needs it too (see that function's comment for the real prod incident this traces back to).
    # `statement_cache_size` is an asyncpg-only DBAPI kwarg — aiosqlite's `Connection()` rejects it
    # outright (`TypeError: unexpected keyword argument 'statement_cache_size'`), so this must stay
    # scoped to Postgres URLs, same as build_engine()'s own dialect branch.
    if not url.startswith("sqlite"):
        configuration["sqlalchemy.connect_args"] = {"statement_cache_size": 0}
    connectable = async_engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    # `.connect()` (not `.begin()`) does NOT commit on a clean async context-manager exit — found
    # live (2026-08-22) running this against real Postgres for the first time: every migration
    # logged as successful, the process exited 0, and yet nothing was ever actually persisted
    # (re-querying the database afterward showed the schema completely unchanged). `.begin()`
    # commits automatically on success and rolls back on exception, which is what this needs —
    # Alembic's own `context.begin_transaction()` manages a transaction *within* this connection's
    # scope, but someone still has to commit the connection's own transaction at the end, and
    # nothing here ever did.
    async with connectable.begin() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
