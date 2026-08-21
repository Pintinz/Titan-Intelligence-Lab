"""POST-M24 Phase 5A — one-off backfill: computes and writes `basketball.fixture.
form_points_diff_last5` / `baseball.fixture.form_runs_diff_last5` for every existing basketball/
baseball fixture in dev.db.

Why this is needed: `FixtureFormDifferentialCalculator.compute_and_write` (wired into
`EntityReconciliationService.form_differential_calculators` this phase) only fires going forward,
on each future `reconcile_fixture` call — it does nothing for the 1,708 basketball and 3,923
baseball fixtures already in `dev.db` before this phase. Without this backfill, those markets'
`required_features` would stay unresolved for every existing fixture, even though the calculator
itself is now correctly wired.

Reuses the exact same calculator class (`FixtureFormDifferentialCalculator`) and the exact same
`TeamStatisticsRepositoryPort.list_recent_by_team` read path every live reconciliation call uses —
this script performs no new computation logic, only re-runs the real one across existing rows. No
predictions, models, or Champions are read or written.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_secondary_sport_form_differential.py
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import (
    baseball_fixture_form_differential_calculator,
    basketball_fixture_form_differential_calculator,
    build_feature_registration_service,
    build_feature_store_service,
    get_engine,
)
from modules.sports.domain.value_objects import TeamId
from modules.sports.infrastructure.persistence.repositories import SqlAlchemyTeamStatisticsRepository


async def _backfill_sport(session, sport_code: str, calculator, now: datetime) -> int:
    rows = (
        await session.execute(
            text(
                "SELECT f.id, f.home_team_id, f.away_team_id FROM fixtures f "
                "JOIN seasons se ON f.season_id = se.id JOIN competitions c ON se.competition_id = c.id "
                "JOIN sports s ON c.sport_id = s.id WHERE s.code = :sport"
            ),
            {"sport": sport_code},
        )
    ).all()
    written = 0
    for fixture_id, home_team_id, away_team_id in rows:
        # Raw SQLite storage is dashless hex; str(uuid.UUID(...)) reproduces the canonical
        # with-dashes form every other feature write for this fixture already uses.
        value = await calculator.compute_and_write(
            str(uuid.UUID(fixture_id)), TeamId(uuid.UUID(home_team_id)), TeamId(uuid.UUID(away_team_id)), now,
        )
        if value is not None:
            written += 1
    return written


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        now = datetime.now(timezone.utc)
        team_statistics = SqlAlchemyTeamStatisticsRepository(session=session)
        registration = build_feature_registration_service(session)
        store = build_feature_store_service(session)

        basketball_calc = basketball_fixture_form_differential_calculator(registration, store, team_statistics)
        baseball_calc = baseball_fixture_form_differential_calculator(registration, store, team_statistics)
        await basketball_calc.ensure_registered(now)
        await baseball_calc.ensure_registered(now)

        basketball_written = await _backfill_sport(session, "basketball", basketball_calc, now)
        baseball_written = await _backfill_sport(session, "baseball", baseball_calc, now)
        await session.commit()

        print(f"basketball.fixture.form_points_diff_last5: {basketball_written} fixtures written")
        print(f"baseball.fixture.form_runs_diff_last5: {baseball_written} fixtures written")


if __name__ == "__main__":
    asyncio.run(main())
