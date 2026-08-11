"""One-off local dev helper: seeds real injuries, transfers, coaching staff, and one fixture's
lineups for the same handful of already-rostered football teams `backfill_football_players.py`
seeded, by calling the newly-added `SyncOrchestrator.sync_injuries`/`sync_transfers`/
`sync_coaching_staff`/`sync_lineups`.

Every row this produces is genuine API-Football data (or an honest zero — most teams have no
reported injuries at any given moment, which is a real result, not a gap) — never fabricated.
`sync_injuries`/`sync_transfers`/`sync_coaching_staff` depend on the team's roster already being
reconciled (`reconcile_injury`/`reconcile_transfer` resolve each record's `player_ref` against
already-synced players), which is why this targets the same teams `backfill_football_players.py`
already seeded rather than every team.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_squad_intelligence.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_sync_orchestrator, get_engine
from modules.sports.domain.value_objects import SportCode
from modules.sports.infrastructure.persistence.models import FixtureModel, PlayerModel
from modules.sports.infrastructure.persistence.repositories import SqlAlchemySportRepository, SqlAlchemyTeamRepository

TEAM_LIMIT = 5
# api-football's /injuries defaults to the current calendar year, which this dev credential's
# free tier rejects ("Free plans do not have access to this season, try from 2022 to 2024") —
# same restriction backfill_football_players.py already hit for /players. /transfers and
# /coachs take no season param at all, so this only applies to the injuries call below.
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

        # Only teams that already have a synced roster — reconcile_injury/reconcile_transfer
        # need each record's player_ref to already resolve to a real Player row.
        rostered_team_ids = set(
            (await session.execute(select(PlayerModel.team_id).where(PlayerModel.team_id.isnot(None)).distinct()))
            .scalars()
            .all()
        )
        candidates = [t for t in teams if t.provider_refs and t.id.value in rostered_team_ids][:TEAM_LIMIT]
        if not candidates:
            print("No rostered football teams found — run backfill_football_players.py first.")
            return

        print(f"Seeding squad intelligence for {len(candidates)} team(s): {', '.join(t.name for t in candidates)}")

        for label, coro, kwargs in (
            ("injuries", orchestrator.sync_injuries, {"season_label": SEASON_LABEL}),
            ("transfers", orchestrator.sync_transfers, {}),
            ("coaching staff", orchestrator.sync_coaching_staff, {}),
        ):
            print(f"-- {label} --")
            for team in candidates:
                run = await coro("football", team.provider_refs[0], now, force=True, **kwargs)
                await session.commit()
                if run is None:
                    print(f"  {team.name}: sync skipped (locked or throttled)")
                    continue
                print(
                    f"  {team.name}: fetched={run.records_fetched} created={run.records_created} "
                    f"updated={run.records_updated} rejected={run.records_rejected} status={run.status.value}"
                )

        # One fixture between two of the candidate teams, for a real lineups sync — lineups are
        # the one piece that already had a working reconciler/validator (Milestone 5) but no
        # orchestration ever calling it; a genuinely completed fixture is the most representative
        # target for verifying it end-to-end.
        candidate_ids = [t.id.value for t in candidates]
        fixture_row = (
            await session.execute(
                select(FixtureModel)
                .where(
                    FixtureModel.status == "completed",
                    FixtureModel.home_team_id.in_(candidate_ids),
                    FixtureModel.away_team_id.in_(candidate_ids),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if fixture_row is None:
            print("No completed fixture between two seeded teams found — skipping lineups.")
        else:
            fixture_ref_dict = fixture_row.provider_ref.get("api_football")
            if not fixture_ref_dict:
                print(f"Fixture {fixture_row.id} has no api_football provider ref — skipping lineups.")
            else:
                from modules.sports.domain.value_objects import ProviderRef

                fixture_ref = ProviderRef(provider="api_football", external_id=str(fixture_ref_dict))
                print(f"-- lineups (fixture {fixture_row.id}) --")
                run = await orchestrator.sync_lineups("football", fixture_ref, str(fixture_row.id), now, force=True)
                await session.commit()
                if run is None:
                    print("  sync skipped (locked or throttled)")
                else:
                    print(
                        f"  fetched={run.records_fetched} created={run.records_created} "
                        f"updated={run.records_updated} rejected={run.records_rejected} status={run.status.value}"
                    )

        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
