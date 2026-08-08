"""One-off local dev helper: corrects `online_ttl_seconds` on already-registered ENGINEERED
feature definitions (team-form rolling averages, form differentials, expected-goals rates —
`windowed_feature_engineering_service.py`) that were registered before that module started
passing `online_ttl_seconds` explicitly, and so are stuck on the registry's generic 3600s
(1-hour) default.

Root cause: these features only change once per fixture-reconciliation cycle, not continuously,
so a 1-hour TTL made `PredictionContextBuilder`'s TTL-aware freshness scoring (which reads
`online_ttl_seconds` from each feature's own registered definition) treat a normal few-hours-to-
a-day-old value as maximally stale — capping every prediction's confidence composite regardless
of actual data quality. `windowed_feature_engineering_service.py` now registers new features with
a 24-hour TTL; this script corrects the definitions that already existed in dev.db before that
fix, via a direct `upsert()` (pure metadata correction — no formula/lifecycle change, so it does
not touch `status`/`version`/review state on features already ACTIVE and in production use).

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_engineered_feature_ttl.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import get_engine
from modules.features.domain.value_objects import FeatureCategory
from modules.features.infrastructure.persistence.repositories import SqlAlchemyFeatureDefinitionRepository
from modules.predictions.application.windowed_feature_engineering_service import ENGINEERED_FEATURE_TTL_SECONDS


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        definitions = SqlAlchemyFeatureDefinitionRepository(session=session)
        all_definitions = await definitions.list_all()
        stale = [
            d for d in all_definitions
            if d.category is FeatureCategory.ENGINEERED and d.online_ttl_seconds != ENGINEERED_FEATURE_TTL_SECONDS
        ]
        if not stale:
            print("No ENGINEERED feature definitions need a TTL correction — nothing to do.")
            return

        for definition in stale:
            print(f"  {definition.feature_key}: {definition.online_ttl_seconds}s -> {ENGINEERED_FEATURE_TTL_SECONDS}s")
            definition.online_ttl_seconds = ENGINEERED_FEATURE_TTL_SECONDS
            await definitions.upsert(definition)

        await session.commit()
        print(f"Corrected online_ttl_seconds for {len(stale)} feature definition(s).")


if __name__ == "__main__":
    asyncio.run(main())
