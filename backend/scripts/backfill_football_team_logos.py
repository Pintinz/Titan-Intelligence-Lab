"""One-off local dev helper: backfills `logo_url` for football teams that don't have one yet, by
re-fetching real team data (crest URLs) from whichever provider each team's `provider_ref_index`
row says it came from.

Audit finding (2026-08-04): `SyncOrchestrator.sync_teams()`/`SportsProviderRouter.fetch_teams()`
only ever resolve the sport's DEFAULT real adapter (api-football) — there's no equivalent of
`fetch_upcoming_fixtures`'s explicit `provider_key` routing for teams. Every team introduced via
`sync_upcoming_fixtures` (the football-data.org path, `CompetitionFixtureSourcePreference`) gets
reconciled from the team refs embedded in that provider's *fixture* payload, not from a dedicated
`fetch_teams` call — and football-data.org's `/matches` response doesn't carry each team's crest,
only its `/teams` endpoint does. Result: a handful of teams reconciled only through that path (here:
Arsenal, Chelsea, Fulham) never got a real logo_url, while every other football team already has one.

This script re-fetches each affected competition's real team list from its actual source provider
(`FootballDataOrgAdapter.fetch_teams`, which does map `logo_url=team.get("crest")`) and calls the
same, already-tested `EntityReconciliationService.reconcile_team` every real sync already uses —
idempotent by `(provider, external_id)`, so it UPDATES the existing team row's `logo_url` in place;
it never creates a duplicate team, and it never fabricates a URL for a team the provider itself
doesn't have a crest for.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_football_team_logos.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_entity_reconciliation_service, build_football_data_org_adapter, get_engine
from modules.sports.domain.value_objects import SportId


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        now = datetime.now(timezone.utc)

        missing = (
            await session.execute(
                text(
                    "SELECT t.id, t.name FROM teams t JOIN sports s ON t.sport_id = s.id "
                    "WHERE s.code = 'football' AND (t.logo_url IS NULL OR t.logo_url = '')"
                )
            )
        ).all()
        if not missing:
            print("No football teams missing a logo — nothing to do.")
            return
        missing_ids = {row[0] for row in missing}
        print(f"{len(missing)} football team(s) missing a logo: {', '.join(r[1] for r in missing)}")

        # Which real provider (and competition ref) each affected team actually came from —
        # driving the re-fetch from real data instead of guessing a provider.
        refs = (
            await session.execute(
                text(
                    "SELECT REPLACE(entity_id, '-', ''), provider, external_id FROM provider_ref_index "
                    "WHERE entity_kind = 'team'"
                )
            )
        ).all()
        provider_by_team = {team_id: provider for team_id, provider, _ in refs if team_id in missing_ids}
        providers_needed = set(provider_by_team.values())
        print(f"Source provider(s) to re-fetch from: {', '.join(providers_needed)}")

        sport_row = (await session.execute(text("SELECT id FROM sports WHERE code = 'football'"))).first()
        sport_id = SportId(__import__("uuid").UUID(sport_row[0]))

        reconciler = build_entity_reconciliation_service(session)
        updated = 0

        if "football_data_org" in providers_needed:
            adapter = build_football_data_org_adapter(session)
            # Premier League — the one competition every currently-affected team belongs to.
            # Extend this list if a future run finds teams from a different competition.
            for competition_ref in ("PL",):
                records = await adapter.fetch_teams(competition_ref)
                by_external_id = {r.external_ref.external_id: r for r in records}
                for team_id, provider in provider_by_team.items():
                    if provider != "football_data_org":
                        continue
                    ext_id = (
                        await session.execute(
                            text(
                                "SELECT external_id FROM provider_ref_index WHERE REPLACE(entity_id,'-','')=:tid "
                                "AND provider='football_data_org' AND entity_kind='team'"
                            ),
                            {"tid": team_id},
                        )
                    ).scalar()
                    record = by_external_id.get(ext_id)
                    if record is None or not record.logo_url:
                        continue
                    _, created = await reconciler.reconcile_team(record, sport_id, now)
                    updated += 0 if created else 1
                    print(f"  updated logo for {record.name} <- {record.logo_url}")

        await session.commit()
        print(f"Backfilled logo_url for {updated}/{len(missing)} team(s).")


if __name__ == "__main__":
    asyncio.run(main())
