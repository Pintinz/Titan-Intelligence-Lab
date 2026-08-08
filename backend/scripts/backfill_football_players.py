"""One-off local dev helper: seeds real player rosters for a handful of already-synced football
teams by calling the newly-added `SyncOrchestrator.sync_players`.

Audit finding (2026-08-08): `fetch_players`/`validate_player`/`reconcile_player` were already real
and fully built across every layer (port, every provider adapter, validator, reconciler, DB model/
migration, GET endpoint) but `SyncOrchestrator` had no `sync_players` method wiring them together —
so the `players` table stayed empty even though teams/fixtures were fully populated. `sync_players`
now exists (mirrors `sync_team_statistics_for_fixture`'s "already built, never orchestrated" shape)
and this script calls it once per team via each team's own real `provider_refs`, so every player row
this produces is genuine API-Football roster data — never a fabricated name.

Pins `SEASON_LABEL = "2023"`: api-football's `/players` endpoint defaults to the current calendar
year, which this dev credential's free tier rejects ("Free plans do not have access to this season,
try from 2022 to 2024"). 2023 is real, in-range, and still a genuine roster snapshot — never a
fabricated one, just not the current season.

Deliberately limited to a small handful of teams rather than every football team: this is a
verification seed ("does the real pipeline work end-to-end"), not a full-catalog sync, and keeps
this one-off run well inside the active API-Football credential's daily request budget. Re-run with
a larger TEAM_LIMIT (or loop over every team) once the org is ready to spend the quota on a full
roster sync.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_football_players.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_sync_orchestrator, get_engine
from modules.sports.domain.value_objects import SportCode
from modules.sports.infrastructure.persistence.repositories import SqlAlchemySportRepository, SqlAlchemyTeamRepository

TEAM_LIMIT = 5
SEASON_LABEL = "2023"


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        now = datetime.now(timezone.utc)
        orchestrator = build_sync_orchestrator(session)

        sport = await SqlAlchemySportRepository(session=session).get_by_code(SportCode.FOOTBALL)
        if sport is None:
            print("Football sport not reconciled yet — nothing to seed.")
            return
        teams = await SqlAlchemyTeamRepository(session=session).list_by_sport(sport.id)
        candidates = [t for t in teams if t.provider_refs][:TEAM_LIMIT]
        if not candidates:
            print("No football teams with a provider reference found — nothing to seed.")
            return

        print(f"Seeding real rosters for {len(candidates)} team(s): {', '.join(t.name for t in candidates)}")
        total_created = 0
        for team in candidates:
            run = await orchestrator.sync_players("football", team.provider_refs[0], now, force=True, season_label=SEASON_LABEL)
            await session.commit()
            if run is None:
                print(f"  {team.name}: sync skipped (locked or throttled)")
                continue
            print(f"  {team.name}: fetched={run.records_fetched} created={run.records_created} updated={run.records_updated} rejected={run.records_rejected} status={run.status.value}")
            total_created += run.records_created

        print(f"Done. {total_created} real player row(s) created.")


if __name__ == "__main__":
    asyncio.run(main())
