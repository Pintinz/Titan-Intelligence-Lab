"""Phase 1 (PROJECT TITANIQ — PHASE 1 COMMAND PROMPT): backfills `period_scores` (half-time) onto
already-reconciled api_football-sourced football fixtures, via the fix in
`ApiFootballAdapter._extract_half_time_scores` (previously `score.halftime` was never parsed).

Targets only the two competitions genuinely sourced from api_football in dev.db (confirmed by a
direct provider_ref_index query, not assumption): Premier League (competition_ref="39") and
DFB-Pokal (competition_ref="81"), across every season currently on file for each.

Deliberately narrower than a full `SyncOrchestrator.sync_fixtures` resync: these fixtures were
already correctly reconciled (teams, scores, status) by the pre-fix adapter — the only field
that's missing is `period_scores`. A full resync re-runs `EntityReconciliationService
.reconcile_fixture`'s entire side-effect chain per record (KG population, prediction-outcome
resolution, form-differential/transfer-activity/news-market-impact recomputation) for data that
hasn't changed, which is unnecessary work for a single-field repair — and was empirically found to
hang indefinitely partway through that chain when run against this dev.db (confirmed via isolated
diagnostics: the raw `router.fetch_fixtures` call reliably succeeds in seconds; calling
`reconcile_fixture` per record — even in complete isolation, with the live dev server stopped and
no other process touching the DB — reliably hung on the very first record with near-zero CPU,
un-interruptible by `asyncio.wait_for`, indicating a genuine block deep in that call chain rather
than ordinary slowness. Root-causing that hang further was not pursued further given the scope of
this phase; it's a separate, real, pre-existing issue worth its own follow-up investigation).

This script instead reuses the two pieces of *existing* production wiring that are actually needed
— `SportsProviderRouter.fetch_fixtures` (the real api-football HTTP call, unchanged) and
`SqlAlchemyFixtureRepository`/`ProviderRefIndexRepository` (the real persistence layer, unchanged)
— to resolve each fetched record to its already-reconciled `Fixture` row via `provider_ref_index`,
and update only `period_scores` (`dataclasses.replace`, matching `reconcile_fixture`'s own
"fetched score always wins" merge semantics for this field) before calling the same
`FixtureRepository.upsert` reconciliation already uses. No parallel fetch/reconcile architecture,
no new provider integration — a narrower write path through the same real components.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_football_half_time_scores.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_sports_provider_router, get_engine
from modules.ingestion.domain.value_objects import EntityKind
from modules.ingestion.infrastructure.persistence.repositories import SqlAlchemyProviderRefIndexRepository
from modules.sports.domain.value_objects import CompetitionId, FixtureId, SportCode
from modules.sports.infrastructure.persistence.repositories import (
    SqlAlchemyCompetitionRepository,
    SqlAlchemyFixtureRepository,
    SqlAlchemySeasonRepository,
    SqlAlchemySportRepository,
)
from modules.sports.infrastructure.providers.provider_router import _InMemoryDistributedLock, _InMemorySyncCache

# Confirmed via provider_ref_index (entity_kind='competition', provider='api_football') during
# the Phase 1 audit — these are the only two football competitions genuinely api_football-sourced
# in dev.db. English Football League Two is football_data_org-sourced and out of scope for this
# adapter-specific fix.
TARGET_COMPETITION_REFS = {"39": "Premier League", "81": "DFB-Pokal"}


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        now = datetime.now(timezone.utc)
        router = build_sports_provider_router(session)
        router.lock = _InMemoryDistributedLock()
        router.cache = _InMemorySyncCache()

        sport = await SqlAlchemySportRepository(session=session).get_by_code(SportCode.FOOTBALL)
        if sport is None:
            print("Football sport not reconciled yet — nothing to resync.")
            return

        competition_repo = SqlAlchemyCompetitionRepository(session=session)
        season_repo = SqlAlchemySeasonRepository(session=session)
        fixture_repo = SqlAlchemyFixtureRepository(session=session)
        ref_index = SqlAlchemyProviderRefIndexRepository(session=session)

        targets = []
        for competition_ref in TARGET_COMPETITION_REFS:
            entity_id = await ref_index.get("api_football", competition_ref, EntityKind.COMPETITION)
            if entity_id is None:
                print(f"  competition_ref={competition_ref}: no provider_ref_index entry — skipping")
                continue
            competition = await competition_repo.get(CompetitionId(uuid.UUID(entity_id)))
            if competition is None:
                print(f"  competition_ref={competition_ref}: resolved entity_id {entity_id} but no Competition row — skipping")
                continue
            targets.append((competition_ref, competition))

        if not targets:
            print("No matching api_football-sourced competitions found — nothing to resync.")
            return

        totals = {"fetched": 0, "updated": 0, "unchanged": 0, "not_reconciled": 0, "no_period_scores": 0}
        summary = []
        for competition_ref, competition in targets:
            seasons = await season_repo.list_by_competition(competition.id)
            seasons.sort(key=lambda s: s.label)
            print(f"-- {competition.name} (competition_ref={competition_ref}): {len(seasons)} season(s) --", flush=True)
            for season in seasons:
                print(f"  {season.label}: fetching...", flush=True)
                try:
                    records = await asyncio.wait_for(
                        router.fetch_fixtures("football", competition_ref, season.label, now), timeout=60
                    )
                except TimeoutError:
                    print(f"  {season.label}: fetch TIMED OUT after 60s — skipping", flush=True)
                    summary.append((competition.name, season.label, "FETCH_TIMED_OUT", None))
                    continue
                except Exception as exc:  # noqa: BLE001 — provider/plan rejections are real, per-season outcomes
                    print(f"  {season.label}: fetch FAILED — {type(exc).__name__}: {exc}", flush=True)
                    summary.append((competition.name, season.label, "FETCH_FAILED", str(exc)))
                    continue

                updated = unchanged = not_reconciled = no_period_scores = 0
                for record in records:
                    if record.period_scores is None:
                        no_period_scores += 1
                        continue
                    entity_id = await ref_index.get(
                        record.external_ref.provider, record.external_ref.external_id, EntityKind.FIXTURE
                    )
                    if entity_id is None:
                        not_reconciled += 1
                        continue
                    existing = await fixture_repo.get(FixtureId(uuid.UUID(entity_id)))
                    if existing is None:
                        not_reconciled += 1
                        continue
                    if existing.period_scores == record.period_scores:
                        unchanged += 1
                        continue
                    updated_entity = dataclasses.replace(
                        existing, period_scores=record.period_scores, version=existing.version + 1
                    )
                    await fixture_repo.upsert(updated_entity)
                    updated += 1
                await session.commit()

                totals["fetched"] += len(records)
                totals["updated"] += updated
                totals["unchanged"] += unchanged
                totals["not_reconciled"] += not_reconciled
                totals["no_period_scores"] += no_period_scores
                print(
                    f"  {season.label}: fetched={len(records)} updated={updated} unchanged={unchanged} "
                    f"not_reconciled={not_reconciled} no_period_scores={no_period_scores}",
                    flush=True,
                )
                summary.append((competition.name, season.label, "DONE", None))

        print("\n== Totals ==", flush=True)
        for key, value in totals.items():
            print(f"{key}: {value}", flush=True)
        print("\n== Per-season summary ==", flush=True)
        for competition_name, label, status, error in summary:
            line = f"{competition_name} {label}: {status}"
            if error:
                line += f" ({error})"
            print(line, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
