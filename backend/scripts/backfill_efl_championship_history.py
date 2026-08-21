"""Fixes "teams without recent form" for Coventry City FC / Hull City AFC / Sunderland AFC —
the 3 real, currently-scheduled fixtures whose opponent lacked enough completed-match history to
compute `expected_home_goals`/`expected_away_goals` (needs real scores), `football.market.
implied_probability_home/away`/`overround` (needs real odds), and `football.fixture.
form_shots_on_target_diff_last5` (needs real `TeamStatistics`) — the exact required features
`MISSING_REQUIRED_FEATURE` named live for these 3 teams.

Source: football-data.co.uk's real, free, no-authentication-required Championship results CSV
(the same underlying data most Kaggle "English football results" datasets repackage — used
directly here since it requires no API credentials, unlike Kaggle's own download API, which
this environment has none configured for). Real historical results, shots, corners, fouls,
cards, and Bet365 odds for the entire 2024-25 English Championship season.

Team-name safety: `_normalize_name` (the real matching function `HistoricalImportService`
already uses) only strips FC/CF/SC/AFC/CFC — it does NOT strip "City"/"Town" etc., so
football-data.co.uk's short names ("Coventry", "Hull") would NOT auto-match TitanIQ's existing
"Coventry City FC"/"Hull City AFC" rows and would silently create duplicate teams. This script
explicitly renames every football-data.co.uk team name to its real, already-existing TitanIQ
name before import — verified name-by-name against a live query of every existing football team
in dev.db, not guessed. Any name with no such verified mapping is passed through unchanged,
letting `HistoricalImportService`'s own real "no match -> create a new team" behavior handle a
genuinely new club exactly as designed.

Read-only until `--import` is passed — defaults to DRY_RUN (parses and resolves in memory, zero
writes) so the exact team/fixture/statistics counts can be inspected before committing anything.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import tempfile
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.ingestion.application.entity_reconciliation_service import EntityReconciliationService
from modules.ingestion.application.historical_import_service import HistoricalImportService
from modules.ingestion.domain.historical_import import ImportMode
from modules.ingestion.infrastructure.historical.csv_historical_source import (
    CsvColumnMapping,
    CsvHistoricalSource,
    OddsColumnMapping,
    StatisticsColumnMapping,
)
from modules.ingestion.infrastructure.persistence.repositories import (
    SqlAlchemyProviderRefIndexRepository,
    SqlAlchemySyncRunRepository,
    SqlAlchemyTimelineEventRepository,
)
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.knowledge_graph.infrastructure.persistence.repositories import (
    SqlAlchemyKGEdgeRepository,
    SqlAlchemyKGNodeRepository,
)
from modules.sports.domain.value_objects import SportCode
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCoachingStaffRepository,
    SqlAlchemyCompetitionRepository,
    SqlAlchemyCountryRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemyInjuryRepository,
    SqlAlchemyMarketLineRepository,
    SqlAlchemyMatchRepository,
    SqlAlchemyLineupRepository,
    SqlAlchemyPlayerRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
    SqlAlchemyStandingRepository,
    SqlAlchemyTeamRepository,
    SqlAlchemyTeamStatisticsRepository,
    SqlAlchemyTransferRepository,
    SqlAlchemyVenueRepository,
)

# Verified live against dev.db (2026-08-20): football-data.co.uk's real 2024-25 Championship
# short name -> TitanIQ's actual existing team name, for every team whose normalized names would
# NOT otherwise match. Any football-data.co.uk name not in this dict either already matches
# TitanIQ exactly after normalization (e.g. "Sunderland" -> "Sunderland AFC", AFC stripped) or is
# a genuinely new club TitanIQ hasn't tracked yet (created for real, not renamed — e.g. Blackburn,
# Cardiff, Derby, Middlesbrough, Norwich, Portsmouth, Luton, Watford, West Brom, Swansea have no
# existing row at all in dev.db today).
#
# Deliberately NOT included: "Bradford"/"Mansfield"/"Doncaster"/"Stockport" already exist in
# dev.db as real, well-covered team rows (46 completed fixtures each) under exactly these short
# names — renaming them to "Bradford City"/"Mansfield Town"/"Doncaster Rovers"/"Stockport County"
# would misroute this import onto a separate, unreferenced duplicate row instead (verified: those
# 4 long-name rows have zero fixtures pointing at them anywhere in dev.db — a pre-existing,
# harmless orphaned-duplicate artifact, not something this script should feed more data into).
DB_PATH = "dev.db"

RENAME_MAP: dict[str, str] = {
    "Coventry": "Coventry City FC",
    "Hull": "Hull City AFC",
    "Sheffield Weds": "Sheffield Wednesday",
    "Oxford": "Oxford United",
    "Plymouth": "Plymouth Argyle",
}


def _rewrite_team_names(source_path: str, dest_path: str) -> None:
    with open(source_path, newline="", encoding="utf-8-sig") as src, open(dest_path, "w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            row["HomeTeam"] = RENAME_MAP.get(row["HomeTeam"], row["HomeTeam"])
            row["AwayTeam"] = RENAME_MAP.get(row["AwayTeam"], row["AwayTeam"])
            writer.writerow(row)


def _championship_source() -> CsvHistoricalSource:
    return CsvHistoricalSource(
        source_key="football_data_co_uk_E1_2425",
        sport=SportCode.FOOTBALL,
        columns=CsvColumnMapping(
            date="Date", home_team="HomeTeam", away_team="AwayTeam", home_score="FTHG", away_score="FTAG",
            date_format="%d/%m/%Y",
            odds=(
                OddsColumnMapping(
                    bookmaker="Bet365",
                    moneyline_home="B365H", moneyline_draw="B365D", moneyline_away="B365A",
                    total_line=2.5, total_over="B365>2.5", total_under="B365<2.5",
                ),
            ),
            statistics=StatisticsColumnMapping(
                home_shots_on_target="HST", away_shots_on_target="AST",
                home_shots_total="HS", away_shots_total="AS",
                home_corners="HC", away_corners="AC",
                home_fouls="HF", away_fouls="AF",
                home_cards_yellow="HY", away_cards_yellow="AY",
            ),
        ),
        default_competition_ref="efl_championship",
        default_competition_name="EFL Championship",
    )


async def main(csv_path: str, mode: ImportMode) -> None:
    rewritten_path = tempfile.mktemp(suffix=".csv")
    _rewrite_team_names(csv_path, rewritten_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", execution_options={
        "schema_translate_map": {
            "sports": None, "ingestion": None, "knowledge_graph": None, "watchlist": None, "alerts": None,
        }
    })
    session = async_sessionmaker(engine, expire_on_commit=False)()
    kg = KnowledgeGraphPopulationService(
        nodes=SqlAlchemyKGNodeRepository(session=session), edges=SqlAlchemyKGEdgeRepository(session=session)
    )
    reconciler = EntityReconciliationService(
        sports=SqlAlchemySportRepository(session=session),
        countries=SqlAlchemyCountryRepository(session=session),
        competitions=SqlAlchemyCompetitionRepository(session=session),
        seasons=SqlAlchemySeasonRepository(session=session),
        venues=SqlAlchemyVenueRepository(session=session),
        teams=SqlAlchemyTeamRepository(session=session),
        players=SqlAlchemyPlayerRepository(session=session),
        fixtures=SqlAlchemyFixtureRepository(session=session),
        matches=SqlAlchemyMatchRepository(session=session),
        team_statistics=SqlAlchemyTeamStatisticsRepository(session=session),
        lineups=SqlAlchemyLineupRepository(session=session),
        standings=SqlAlchemyStandingRepository(session=session),
        injuries=SqlAlchemyInjuryRepository(session=session),
        transfers=SqlAlchemyTransferRepository(session=session),
        coaching_staff=SqlAlchemyCoachingStaffRepository(session=session),
        ref_index=SqlAlchemyProviderRefIndexRepository(session=session),
        kg=kg,
        timeline=SqlAlchemyTimelineEventRepository(session=session),
    )
    service = HistoricalImportService(
        reconciler=reconciler,
        sync_runs=SqlAlchemySyncRunRepository(session=session),
        market_lines=SqlAlchemyMarketLineRepository(session=session),
    )

    now = datetime.now(timezone.utc)
    report = await service.import_file(_championship_source(), rewritten_path, SportCode.FOOTBALL, mode, now)

    print(f"mode={mode.value}")
    print(f"total_records={report.total_records} rejected_rows={report.rejected_rows}")
    print(f"teams_matched={report.teams_matched} teams_created={report.teams_created}")
    print(f"fixtures_created={report.fixtures_created} fixtures_updated={report.fixtures_updated}")
    print(f"statistics_recorded={report.statistics_recorded}")
    print(f"odds_quotes_recorded={report.odds_quotes_recorded}")
    print(f"quarantined={report.quarantined_count}")
    for q in report.quarantined[:20]:
        print(f"  QUARANTINED {q.source_record_id}: {q.reason.value} — {q.detail}")

    if mode is ImportMode.IMPORT:
        await session.commit()
    await session.close()
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--import", dest="do_import", action="store_true", help="Actually write (default: dry run)")
    parser.add_argument("--db-path", default="dev.db")
    args = parser.parse_args()
    DB_PATH = args.db_path
    asyncio.run(main(args.csv_path, ImportMode.IMPORT if args.do_import else ImportMode.DRY_RUN))
