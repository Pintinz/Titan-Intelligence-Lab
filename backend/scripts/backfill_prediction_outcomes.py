"""One-off local dev helper: retroactively resolves `PredictionOutcome` rows for every already-
COMPLETED fixture that has a real final score.

ML-architecture consolidation (2026-08-04): `OutcomeResolutionService.resolve_for_fixture()` is
already wired to fire automatically going forward, as part of normal ingestion — see
`EntityReconciliationService._resolve_prediction_outcomes`, called whenever a fixture is
reconciled as COMPLETED with both scores present. That live hook only ever sees fixtures that
complete AFTER a PUBLISHED prediction already exists for them. Every fixture already sitting in
dev.db as COMPLETED before that prediction existed (most of this environment's seeded/backfilled
data) never went through that hook, so `prediction_outcomes` stays empty even though real
predictions and real results both already exist for some of them.

This script closes that one-time gap — a pure catch-up sweep, not a new resolution mechanism: it
calls the exact same `resolve_for_fixture()` every real fixture completion already calls, for
every COMPLETED fixture in the database. `resolve_for_fixture()` is itself idempotent (skips a
prediction that's already been evaluated) and only ever grades a real PUBLISHED prediction against
a real recorded score — it fabricates nothing. Whatever real outcome rows this produces become the
seed of the training dataset `AutomaticModelSelectionService`/`ScheduledRetrainingOrchestrator`
need before a not-yet-trained market (see `seed_football_markets.py`'s `NOT_YET_TRAINED_MARKET_KEYS`)
can ever get a real Champion.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_prediction_outcomes.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_outcome_resolution_service, get_engine


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        now = datetime.now(timezone.utc)
        resolver = build_outcome_resolution_service(session)

        rows = (
            await session.execute(
                text(
                    "SELECT id, home_score, away_score FROM fixtures "
                    "WHERE status = 'completed' AND home_score IS NOT NULL AND away_score IS NOT NULL"
                )
            )
        ).all()

        total_recorded = 0
        fixtures_with_new_outcomes = 0
        for i, (raw_fixture_id, home_score, away_score) in enumerate(rows, start=1):
            fixture_id = str(UUID(raw_fixture_id))
            recorded = await resolver.resolve_for_fixture(fixture_id, home_score, away_score, now)
            if recorded:
                fixtures_with_new_outcomes += 1
                total_recorded += len(recorded)
            if i % 100 == 0 or i == len(rows):
                print(f"...{i}/{len(rows)} completed fixtures checked ({total_recorded} outcomes recorded)", flush=True)

        await session.commit()
        print(
            f"Backfilled {total_recorded} PredictionOutcome row(s) across "
            f"{fixtures_with_new_outcomes}/{len(rows)} completed fixtures that had a published "
            f"prediction awaiting grading."
        )


if __name__ == "__main__":
    asyncio.run(main())
