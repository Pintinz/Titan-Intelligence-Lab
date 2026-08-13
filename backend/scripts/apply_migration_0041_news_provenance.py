"""Applies Alembic migration 0041 (Milestone 9 news provenance columns) directly to the local
SQLite dev.db, mirroring the precedent established in Milestone 5: `alembic upgrade head` doesn't
cleanly apply migrations declared with `schema="intelligence"` against SQLite, because
`alembic/env.py`'s `run_migrations_online()` doesn't set a `schema_translate_map` the way the real
app engine (`modules.sports.infrastructure.persistence.database.build_engine`) does. This script
uses that same schema-translate-map-aware engine and issues the equivalent DDL directly.

Idempotent: skips any column that already exists (checked via PRAGMA table_info), so it is safe to
re-run. Additive only — mirrors migration 0041's `upgrade()` exactly, including its
`server_default` values, so every existing row (68 at time of writing, none synced through a
genuine LIVE_SCHEDULED-equivalent pipeline) gets an honest `availability_classification =
'UNKNOWN_AVAILABILITY_TIME'`, never a fabricated 'VERIFIED_PRE_MATCH'.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from modules.sports.infrastructure.persistence.database import build_engine

_COLUMNS = (
    ("resolved_entities", "JSON NOT NULL DEFAULT '[]'"),
    ("confidence_tier", "VARCHAR(16) NOT NULL DEFAULT 'uncertain'"),
    ("information_available_at", "DATETIME"),
    ("availability_classification", "VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN_AVAILABILITY_TIME'"),
    ("validity_start", "DATETIME"),
    ("validity_end", "DATETIME"),
    ("sync_run_id", "VARCHAR(36)"),
)


async def main() -> None:
    engine = build_engine()
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(news_events)"))
        existing_columns = {row[1] for row in result.fetchall()}

        for column_name, ddl_type in _COLUMNS:
            if column_name in existing_columns:
                print(f"skip (already exists): {column_name}")
                continue
            await conn.execute(text(f"ALTER TABLE news_events ADD COLUMN {column_name} {ddl_type}"))
            print(f"added column: {column_name}")

        result = await conn.execute(text("SELECT COUNT(*) FROM news_events"))
        total = result.scalar_one()
        result = await conn.execute(
            text("SELECT COUNT(*) FROM news_events WHERE availability_classification = 'UNKNOWN_AVAILABILITY_TIME'")
        )
        unknown = result.scalar_one()
        print(f"news_events total={total}, availability_classification=UNKNOWN_AVAILABILITY_TIME={unknown}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
