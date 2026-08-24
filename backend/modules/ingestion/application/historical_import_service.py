"""POST-M24 Phase 4 — HistoricalImportService.

Turns a `HistoricalSourcePort`'s raw records into real TitanIQ entities by delegating every write
to the *existing* `EntityReconciliationService` — this service resolves identity (team name ->
existing team or new team; competition ref -> a historical-source-scoped competition) and then
calls `reconcile_team`/`reconcile_competition`/`reconcile_season`/`reconcile_fixture` exactly as
any other provider sync does. It never writes to a repository directly and never re-implements
matching: team-name matching reuses `_normalize_name` (`CrossProviderTeamMappingService`'s own
normalization rule) at the read layer — this class never calls that service itself, since its
write path (`confirm_mappings`) is hardcoded to the football-data.org provider key, but the pure
normalization function it uses is correct and safe to reuse for any source's raw team names.

Every entity this writes carries a `ProviderRef(provider=f"historical:{source.source_key}", ...)`
— a distinct provider namespace per historical source, never colliding with a live provider's own
refs, and easy to audit or reverse (every `provider_ref_index` row starting with "historical:" is
exactly and only what this service ever wrote).

Team resolution hierarchy (Phase 4 Step 9's ordering, as implemented here):
  1. Exact normalized-name match against exactly one existing team for the sport -> reuse it.
  2. Exact normalized-name match against 2+ existing teams (genuine ambiguity) -> quarantine.
  3. No match at all -> create a new team (this *is* historical enrichment's job: Kaggle team
     rosters routinely include clubs no live provider has synced yet).

Competitions never auto-merge into an existing live-provider competition (e.g. api-football's own
"English Premier League") — each historical source's competitions reconcile into their own
`historical:{source_key}` provider namespace instead. Auto-merging on a name match here would risk
exactly the "EPL vs Premier League vs English Premier League" false-identity Phase 4's own master
prompt warns against; an operator can merge two competitions later via the same admin tooling any
other cross-provider competition merge would use.

Provenance: `SyncTrigger.BACKFILL` is recorded on the `SyncRun` this service creates (IMPORT mode
only — DRY_RUN/VALIDATE never create one, since neither writes anything). It never sets
`VERIFIED_PRE_MATCH` anywhere: `EntityReconciliationService.reconcile_fixture` sets no availability
classification at all (that machinery — `classify_availability`, `modules.ingestion.application.
provenance` — is specific to Lineup/Injury/Transfer/Suspension), so there is no availability gate
to satisfy or bypass here. Historical fixtures import as fixture identity + final score only, never
as a pre-match feature source — nothing this service writes ever reaches `DatasetBuilder` as a
gated pre-match feature, because it never writes a feature at all.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.ingestion.application.cross_provider_team_mapping_service import _normalize_name
from modules.ingestion.application.entity_reconciliation_service import EntityReconciliationService
from modules.ingestion.domain.entities import ProviderRefIndexEntry, SyncRun
from modules.ingestion.domain.historical_import import (
    HistoricalImportReport,
    ImportMode,
    QuarantinedRecord,
    QuarantineReason,
)
from modules.ingestion.domain.value_objects import EntityKind, SyncRunId, SyncStatus, SyncTrigger
from modules.ingestion.ports.historical_source import HistoricalSourcePort
from modules.ingestion.ports.repositories import SyncRunRepositoryPort
from modules.sports.domain.entities import MarketLine
from modules.sports.domain.value_objects import MarketLineId, MarketLineType, ProviderRef, SportCode
from modules.sports.ports.provider_gateway import (
    ProviderFixtureRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
)
from modules.sports.ports.repositories import MarketLineRepositoryPort


@dataclass(frozen=True)
class _ResolvedTeam:
    external_ref: ProviderRef
    matched_existing_id: str | None  # set only when resolved to a pre-existing team


@dataclass
class HistoricalImportService:
    reconciler: EntityReconciliationService
    sync_runs: SyncRunRepositoryPort | None = None
    market_lines: MarketLineRepositoryPort | None = None

    async def import_file(
        self, source: HistoricalSourcePort, file_path: str, sport_code: SportCode, mode: ImportMode, now: datetime,
    ) -> HistoricalImportReport:
        sport = await self.reconciler.sports.get_by_code(sport_code)
        if sport is None:
            raise ValueError(
                f"sport {sport_code.value!r} has never been reconciled — historical import never creates a Sport"
            )
        read_result = source.read_records(file_path)
        report = HistoricalImportReport(
            mode=mode, source_key=source.source_key, sport=sport_code,
            total_records=len(read_result.records) + len(read_result.rejected),
            rejected_rows=len(read_result.rejected),
        )
        report.quarantined.extend(read_result.rejected)

        existing_teams = await self.reconciler.teams.list_by_sport(sport.id)
        name_counts = Counter(_normalize_name(t.name) for t in existing_teams)
        by_normalized_name = {}
        for team in existing_teams:
            by_normalized_name.setdefault(_normalize_name(team.name), team)

        sync_run: SyncRun | None = None
        if mode is ImportMode.IMPORT and self.sync_runs is not None:
            sync_run = await self.sync_runs.record(
                SyncRun(
                    id=SyncRunId(uuid4()), sport_code=sport_code.value, entity_kind=EntityKind.FIXTURE,
                    scope_key=f"historical:{source.source_key}", trigger=SyncTrigger.BACKFILL,
                    status=SyncStatus.RUNNING, started_at=now,
                )
            )

        for record in read_result.records:
            provider = f"historical:{record.source_key}"
            resolution = self._resolve_teams(record, provider, name_counts, by_normalized_name)
            if isinstance(resolution, QuarantinedRecord):
                report.quarantined.append(resolution)
                continue
            home_team, away_team = resolution
            report.competitions_touched.add(record.competition_ref)
            for resolved in (home_team, away_team):
                if resolved.matched_existing_id is not None:
                    report.teams_matched += 1
                else:
                    report.teams_created += 1

            if mode is not ImportMode.IMPORT:
                # DRY_RUN/VALIDATE never write, but the report still owes an honest
                # would-create-vs-would-update count — answered with a pure read against the ref
                # index (the same identity check `reconcile_fixture` itself would make), never a
                # write of any kind.
                already_exists = await self.reconciler.ref_index.get(provider, record.source_record_id, EntityKind.FIXTURE)
                if already_exists is not None:
                    report.fixtures_updated += 1
                else:
                    report.fixtures_created += 1
                report.odds_quotes_recorded += len(record.odds)
                continue

            for resolved, raw_name in ((home_team, record.home_team_name), (away_team, record.away_team_name)):
                if resolved.matched_existing_id is not None:
                    await self.reconciler.ref_index.upsert(
                        ProviderRefIndexEntry(
                            provider=resolved.external_ref.provider, external_id=resolved.external_ref.external_id,
                            entity_kind=EntityKind.TEAM, entity_id=resolved.matched_existing_id,
                        )
                    )
                else:
                    await self.reconciler.reconcile_team(
                        ProviderTeamRecord(
                            external_ref=resolved.external_ref, name=raw_name, short_name=raw_name[:30], country=None,
                        ),
                        sport.id, now,
                    )

            competition, _ = await self.reconciler.reconcile_competition(
                record.competition_ref, provider, sport.id, now, name=record.competition_name,
            )
            season, _ = await self.reconciler.reconcile_season(
                record.competition_ref, record.season_label, provider, competition.id, now,
            )
            has_score = record.home_score is not None and record.away_score is not None
            fixture_record = ProviderFixtureRecord(
                external_ref=ProviderRef(provider, record.source_record_id),
                home_team_ref=home_team.external_ref, away_team_ref=away_team.external_ref,
                scheduled_at=record.scheduled_at, competition_ref=record.competition_ref,
                season_label=record.season_label, status="FT" if has_score else "NS",
                home_score=record.home_score, away_score=record.away_score,
            )
            # Look-ahead leakage fix (2026-08-23 audit): `now` here is one shared import-run
            # timestamp for the *entire* file, correct for bookkeeping (created_at, ref-index,
            # timeline events) but never a valid feature cutoff for a specific historical fixture —
            # without `feature_as_of`, every fixture in this file would compute pre-match form as
            # if it already knew every later fixture's result too. Each fixture gets its own real
            # kickoff as the cutoff instead.
            fixture, created = await self.reconciler.reconcile_fixture(
                fixture_record, season.id, now, sport_code=sport_code.value,
                match_by_teams_and_date=True, preserve_existing_score=True,
                feature_as_of=record.scheduled_at,
            )
            if created:
                report.fixtures_created += 1
            else:
                report.fixtures_updated += 1

            if (record.home_statistics or record.away_statistics) and has_score:
                # Real per-side match statistics for this exact fixture — written against the
                # `Match` the same `FixtureId` reconciliation just resolved, via the *existing*
                # `get_or_create_match`/`reconcile_team_statistics` pair every live provider stats
                # sync already uses (one write path, not a second one). Only written for a
                # completed match (`has_score`) — statistics for a fixture with no final score
                # would be a contradiction this service never fabricates.
                match = await self.reconciler.get_or_create_match(fixture.id, now)
                for resolved, stats in ((home_team, record.home_statistics), (away_team, record.away_statistics)):
                    if stats is None or not stats.stat_set:
                        continue
                    await self.reconciler.reconcile_team_statistics(
                        ProviderTeamStatisticsRecord(
                            fixture_ref=fixture_record.external_ref, team_ref=resolved.external_ref,
                            stat_set=stats.stat_set,
                        ),
                        match.id, now,
                    )
                    report.statistics_recorded += 1

            if record.odds and self.market_lines is not None:
                # Real historical bookmaker quotes for this exact fixture — written against the
                # `FixtureId` reconciliation just resolved above, never a second, independent
                # fixture match (one matching engine). `fetched_at` is this import's own real
                # retrieval time; `observed_at` stays unset (`None`) since the source reports no
                # separate quote timestamp — never substituted, per `MarketLine`'s own documented
                # "unknown, not just now" rule.
                for quote in record.odds:
                    await self.market_lines.record(
                        MarketLine(
                            id=MarketLineId(uuid4()), fixture_id=fixture.id, sport_code=sport_code.value,
                            provider=provider, bookmaker=quote.bookmaker,
                            market_type=MarketLineType(quote.market_type),
                            selection=quote.selection, line=quote.line, price=quote.price, fetched_at=now,
                        )
                    )
                    report.odds_quotes_recorded += 1

        if sync_run is not None and self.sync_runs is not None:
            sync_run.status = SyncStatus.SUCCEEDED if not report.quarantined else SyncStatus.PARTIAL
            sync_run.finished_at = now
            sync_run.records_fetched = report.total_records
            sync_run.records_created = report.fixtures_created
            sync_run.records_updated = report.fixtures_updated
            sync_run.records_rejected = report.quarantined_count
            await self.sync_runs.update(sync_run)

        return report

    @staticmethod
    def _resolve_teams(
        record, provider: str, name_counts: Counter, by_normalized_name: dict,
    ) -> tuple[_ResolvedTeam, _ResolvedTeam] | QuarantinedRecord:
        resolved: list[_ResolvedTeam] = []
        for name in (record.home_team_name, record.away_team_name):
            normalized = _normalize_name(name)
            if name_counts.get(normalized, 0) > 1:
                return QuarantinedRecord(
                    source_record_id=record.source_record_id, reason=QuarantineReason.AMBIGUOUS_TEAM,
                    detail=f"'{name}' normalizes to '{normalized}', matching {name_counts[normalized]} existing teams",
                )
            existing = by_normalized_name.get(normalized)
            resolved.append(
                _ResolvedTeam(
                    external_ref=ProviderRef(provider, normalized),
                    matched_existing_id=str(existing.id.value) if existing else None,
                )
            )
        return resolved[0], resolved[1]
