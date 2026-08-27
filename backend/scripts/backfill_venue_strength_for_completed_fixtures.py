"""One-off backfill: computes and writes `FixtureVenueStrengthCalculator`'s four features for
every real completed football fixture, using each fixture's own `scheduled_at` as the point-in-time
cutoff — never `now`. This is the historical-training-data counterpart to
`backfill_venue_strength_and_manager_change_features.py` (which targets `scheduled`/upcoming
fixtures, for live predictions): the ~800 real completed fixtures whose resolved outcomes make up
`football.correct_score`'s training data were reconciled before `FixtureVenueStrengthCalculator`
existed, so they have zero venue-strength feature values today — meaning no retrain can ever
actually learn from this signal until these values exist for the fixtures training samples are
built from.

Point-in-time safety is the entire reason this is a separate script from the live-prediction one:
a completed fixture's own `scheduled_at` (its real kickoff) is the correct, honest cutoff — using
`now` here would let a team's post-kickoff (even post-fixture) results leak into what should be a
pre-match feature for that same fixture, the exact class of leakage this codebase tests against
everywhere else.

After this runs, `scripts/refresh_correct_score_training_feature_snapshots.py` re-reads these new
values into the existing training `Prediction.feature_snapshot` rows
(`backfill_correct_score_training_data.py` originally built), and a real retrain can then use them.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python -m scripts.backfill_venue_strength_for_completed_fixtures
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_football_venue_strength_calculator, get_engine
from modules.sports.domain.value_objects import SeasonId, SportId, TeamId
from modules.sports.infrastructure.persistence.models import FixtureModel, SportModel


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007)."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        sport_row = (await session.execute(select(SportModel).where(SportModel.code == "football"))).scalar_one()
        sport_id = SportId(sport_row.id)

        fixtures = (
            await session.execute(
                select(FixtureModel).where(FixtureModel.status == "completed", FixtureModel.home_score.is_not(None))
            )
        ).scalars().all()
        print(f"{len(fixtures)} real completed football fixtures to backfill venue-strength features for")

        now = datetime.now(timezone.utc)
        calc = build_football_venue_strength_calculator(session)
        await calc.ensure_registered(now)

        written = 0
        for fixture in fixtures:
            fixture_id = str(fixture.id)
            home_id, away_id = TeamId(fixture.home_team_id), TeamId(fixture.away_team_id)
            season_id = SeasonId(fixture.season_id)
            # The real, honest point-in-time cutoff for a historical fixture is its OWN kickoff —
            # never `now`, which would leak this fixture's (and every later fixture's) own result
            # into what must be a pre-match feature.
            cutoff = _ensure_aware(fixture.scheduled_at, now)

            values = await calc.compute_and_write(fixture_id, home_id, away_id, sport_id, season_id, cutoff)
            written += sum(1 for v in values if v is not None)

        await session.commit()
        print(f"venue_strength features written: {written}")


if __name__ == "__main__":
    asyncio.run(main())
