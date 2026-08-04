"""One-off local dev helper: creates backend/dev.db (SQLite) with every module's schema.

Alembic's versions/*.py migrations issue Postgres-flavored DDL (``op.create_table(...,
schema="sports")`` etc. across 11 module schemas) and SQLite has no multi-schema support, so
those migrations cannot run against SQLite as-is (see docs/deployment.md §1 — the real
Postgres password was never supplied to this session, hence this local fallback). Tests already
solve the same problem per-module with a ``schema_translate_map`` engine option (e.g.
tests/unit/modules/sports/conftest.py); this script applies the identical technique once, across
every module's Base, to stand up a persistent local dev.db instead of pytest's in-memory engine.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/init_local_sqlite_db.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from modules.admin.infrastructure.persistence.models import Base as AdminBase
from modules.alerts.infrastructure.persistence.models import Base as AlertsBase
from modules.billing.infrastructure.persistence.models import Base as BillingBase
from modules.features.infrastructure.persistence.models import Base as FeaturesBase
from modules.identity.infrastructure.persistence.models import Base as IdentityBase
from modules.ingestion.infrastructure.persistence.models import Base as IngestionBase
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase
from modules.predictions.infrastructure.persistence.models import Base as PredictionsBase
from modules.sports.infrastructure.persistence.database import get_database_settings
from modules.sports.infrastructure.persistence.models import Base as SportsBase
from modules.tenancy.infrastructure.persistence.models import Base as TenancyBase
from modules.watchlist.infrastructure.persistence.models import Base as WatchlistBase
from modules.webhooks.infrastructure.persistence.models import Base as WebhooksBase

ALL_BASES = [
    AdminBase,
    AlertsBase,
    BillingBase,
    FeaturesBase,
    IdentityBase,
    IngestionBase,
    IntelligenceBase,
    KnowledgeGraphBase,
    PredictionsBase,
    SportsBase,
    TenancyBase,
    WatchlistBase,
    WebhooksBase,
]

SCHEMA_TRANSLATE_MAP = {
    "admin": None,
    "alerts": None,
    "billing": None,
    "features": None,
    "identity": None,
    "ingestion": None,
    "intelligence": None,
    "knowledge_graph": None,
    "predictions": None,
    "sports": None,
    "tenancy": None,
    "watchlist": None,
    "webhooks": None,
}


async def main() -> None:
    url = get_database_settings().url
    engine = create_async_engine(url, execution_options={"schema_translate_map": SCHEMA_TRANSLATE_MAP})
    async with engine.begin() as conn:
        for base in ALL_BASES:
            await conn.run_sync(base.metadata.create_all)
    await engine.dispose()
    print(f"Created {sum(len(b.metadata.tables) for b in ALL_BASES)} tables at {url}")


if __name__ == "__main__":
    asyncio.run(main())
