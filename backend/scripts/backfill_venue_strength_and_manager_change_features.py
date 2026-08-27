"""One-off feature-recomputation pass for three feature families that are all wired into
`EntityReconciliationService.reconcile_fixture` (so they compute automatically on every *new*
reconciliation) but never re-run for real, already-existing, still-`scheduled` fixtures on their
own: `FixtureVenueStrengthCalculator` and `ManagerChangeContextCalculator` (both added this
session) plus `NewsMarketImpactEngine` (pre-existing, but its real injury/suspension signal was
never actually reachable before this session's entity-resolution audit fix — see
`population_service.py`'s own module docstring — so it has the identical "never re-triggered for
already-existing fixtures" gap in practice even though the wiring itself predates today).

This script (re)computes all three for every real upcoming football fixture, using the exact same
composition-wired calculator/engine classes the live app already uses — no new calculator, no new
write path. Matches `recompute_features_for_teams.py`'s own established shape for exactly this
situation, generalized from "one historical import's affected teams" to "every upcoming fixture."

Run this before regenerating predictions for upcoming fixtures if you want those predictions to
actually see the new signal — `PredictionCacheService` reads whatever is already in the feature
store at generation time, it does not trigger this recomputation itself.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import (
    build_football_manager_change_context_calculator,
    build_football_news_market_impact_engine,
    build_football_venue_strength_calculator,
)
from modules.sports.domain.value_objects import SeasonId, SportId, TeamId
from modules.sports.infrastructure.persistence.models import FixtureModel, SportModel


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — duplicated
    per-module rather than imported, matching the existing convention across this codebase."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


async def main(db_path: str) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        execution_options={
            "schema_translate_map": {
                "sports": None, "ingestion": None, "knowledge_graph": None, "watchlist": None,
                "alerts": None, "predictions": None, "features": None, "admin": None, "intelligence": None,
            }
        },
    )
    session = async_sessionmaker(engine, expire_on_commit=False)()

    sport_row = (await session.execute(select(SportModel).where(SportModel.code == "football"))).scalar_one()
    sport_id = SportId(sport_row.id)

    fixtures = (
        await session.execute(select(FixtureModel).where(FixtureModel.status == "scheduled"))
    ).scalars().all()
    print(f"{len(fixtures)} real scheduled football fixtures to recompute features for")

    now = datetime.now(timezone.utc)
    venue_strength_calc = build_football_venue_strength_calculator(session)
    manager_change_calc = build_football_manager_change_context_calculator(session)
    news_impact_engine = build_football_news_market_impact_engine(session)
    await venue_strength_calc.ensure_registered(now)
    await manager_change_calc.ensure_registered(now)
    await news_impact_engine.ensure_registered(now)

    venue_strength_written = 0
    manager_change_written = 0
    news_impact_written = 0
    for fixture in fixtures:
        fixture_id = str(fixture.id)
        home_id, away_id = TeamId(fixture.home_team_id), TeamId(fixture.away_team_id)
        season_id = SeasonId(fixture.season_id)
        # Same "cap at this fixture's own kickoff, never a lagging sync job's future now"
        # reasoning recompute_features_for_teams.py already established.
        kickoff = _ensure_aware(fixture.scheduled_at, now)
        cutoff = min(now, kickoff)

        venue_values = await venue_strength_calc.compute_and_write(fixture_id, home_id, away_id, sport_id, season_id, cutoff)
        venue_strength_written += sum(1 for v in venue_values if v is not None)

        for team_id, side in ((home_id, "home"), (away_id, "away")):
            written = await manager_change_calc.compute_and_write(fixture_id, team_id, side, cutoff, kickoff=kickoff)
            if written is not None:
                manager_change_written += 1
            news_values = await news_impact_engine.compute_and_write(fixture_id, team_id, side, cutoff, kickoff=kickoff)
            news_impact_written += len(news_values)

    await session.commit()
    print(f"venue_strength features written: {venue_strength_written}")
    print(f"manager_change_context features written: {manager_change_written}")
    print(f"news_market_impact features written: {news_impact_written}")
    await session.close()
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default="dev.db")
    args = parser.parse_args()
    asyncio.run(main(args.db_path))
