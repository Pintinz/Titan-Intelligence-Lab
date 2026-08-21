"""One-off feature-recomputation pass for the fixtures unblocked by
`backfill_efl_championship_history.py` — the historical import writes real `Fixture`/
`TeamStatistics`/`MarketLine` rows but (correctly, per `HistoricalImportService`'s own contract)
never writes a derived feature itself. `EntityReconciliationService.reconcile_fixture` would
normally trigger `FixtureFormDifferentialCalculator` automatically on every *new* reconciliation,
but that only fires for the 552 historical fixtures just imported — never for the real, already-
existing, still-`scheduled` fixtures that reference these teams, since nothing reconciles those
again. This script explicitly (re)computes `expected_home_goals`/`expected_away_goals` and every
`form_*_diff_last5` feature for every real scheduled fixture involving the given teams, using the
exact same composition-wired calculator classes the live app already uses — no new calculator, no
new write path.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.composition import (
    build_football_expected_goals_calculator,
    build_football_form_differential_calculators,
)
from modules.sports.domain.value_objects import TeamId
from modules.sports.infrastructure.persistence.models import FixtureModel, TeamModel

TARGET_TEAM_NAMES = ["Coventry City FC", "Hull City AFC", "Sunderland AFC"]


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

    team_rows = (
        await session.execute(select(TeamModel).where(TeamModel.name.in_(TARGET_TEAM_NAMES)))
    ).scalars().all()
    team_ids = [t.id for t in team_rows]  # real UUID objects — the ORM column expects these, not strings
    print(f"target teams: {[(t.name, str(t.id)) for t in team_rows]}")

    fixtures = (
        await session.execute(
            select(FixtureModel).where(
                FixtureModel.status == "scheduled",
                (FixtureModel.home_team_id.in_(team_ids)) | (FixtureModel.away_team_id.in_(team_ids)),
            )
        )
    ).scalars().all()
    print(f"{len(fixtures)} real scheduled fixtures to recompute features for")

    expected_goals_calc = build_football_expected_goals_calculator(session)
    form_diff_calcs = build_football_form_differential_calculators(session)
    await expected_goals_calc.ensure_registered(datetime.now(timezone.utc))
    for calc in form_diff_calcs:
        await calc.ensure_registered(datetime.now(timezone.utc))

    now = datetime.now(timezone.utc)
    expected_goals_written = 0
    form_diff_written = 0
    for fixture in fixtures:
        fixture_id = str(fixture.id)
        home_id, away_id = TeamId(fixture.home_team_id), TeamId(fixture.away_team_id)
        home_val, away_val = await expected_goals_calc.compute_and_write(fixture_id, home_id, away_id, now)
        if home_val is not None:
            expected_goals_written += 1
        if away_val is not None:
            expected_goals_written += 1
        for calc in form_diff_calcs:
            written = await calc.compute_and_write(fixture_id, home_id, away_id, now)
            if written is not None:
                form_diff_written += 1

    await session.commit()
    print(f"expected_goals features written: {expected_goals_written}")
    print(f"form_differential features written: {form_diff_written}")
    await session.close()
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default="dev.db")
    args = parser.parse_args()
    asyncio.run(main(args.db_path))
