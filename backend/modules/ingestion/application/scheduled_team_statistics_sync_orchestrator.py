"""Scheduled Team Statistics Sync Orchestrator.

Real gap found live (2026-08-26) — a completed fixture's "Match Statistics" panel
(`match-review-page.tsx`) honestly reads "TitanIQ hasn't recorded detailed match statistics for
this fixture yet" for every recently-completed match, because `SyncOrchestrator
.sync_team_statistics_for_fixture` (fetch/validate/reconcile were already real and fully built,
audit fix 2026-08-02) has never had anything call it automatically — reachable only via a manual
admin endpoint (`POST /api/v1/admin/sync/{sport_code}/statistics/{fixture_id}`) or a one-off
backfill script. `ingestion.sync_completed_fixtures` (Beat-scheduled, every
`PROVIDER_POLL_INTERVAL_SECONDS`) syncs a fixture's own final score/status, and reconciling that
completion already auto-triggers outcome resolution (`EntityReconciliationService
._resolve_prediction_outcomes`) — but never team statistics, a genuinely separate provider fetch.

This orchestrator is that missing loop: for every completed fixture within `lookback_hours` (real
box-score data is only available shortly after a match ends — no point sweeping fixtures from
months ago on every run), sync team statistics unless that fixture's `Match` already has both
sides' `TeamStatistics` rows. Checking first rather than relying purely on `sync_team_statistics_
for_fixture`'s own checkpoint/lock (`DEFAULT_MIN_SYNC_INTERVAL_SECONDS`) matters here specifically
because a completed match's box score is permanent — once synced, this orchestrator should never
touch that fixture again, not just skip it for a few minutes.

Real, deeper gap found live verifying this fix (2026-08-26): `sync_team_statistics_for_fixture`
calls the provider named by `fixture.provider_refs[0]` (same convention the pre-existing manual
admin endpoint already used) — but every one of the 10 recently-completed EPL fixtures checked
live was reconciled *only* via football-data.org, which has no team-statistics endpoint at all.
api-sports.io is the one provider this codebase integrates with that actually supplies box-score
stats, but its own football sync is pinned to the free-tier's 2022-2024 season window
(`beat_schedule.py`), so it never ingests (or cross-provider-matches into) a current fixture
football-data.org supplied. This orchestrator honestly reports that as `"no_data_from_provider"`,
distinct from a real failure — no amount of scheduling fixes this without either extending
api-sports.io's season coverage or a provider capable of supplying stats for these fixtures, both
real data-source decisions outside this orchestrator's scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from modules.ingestion.application.sync_orchestrator import SyncOrchestrator
from modules.sports.domain.entities import Fixture
from modules.sports.ports.plugin_registry import SportPluginRegistryPort
from modules.sports.ports.repositories import FixtureRepositoryPort, MatchRepositoryPort, SportRepositoryPort, TeamStatisticsRepositoryPort

# Real box-score data is published by providers shortly after a match ends, not months later — a
# 14-day lookback comfortably covers a match still worth syncing (including a retry window for a
# fixture whose provider hadn't published stats yet the first time this swept past it) without
# scanning a sport's entire multi-season completed-fixture history on every run.
DEFAULT_LOOKBACK_HOURS = 14 * 24


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """Same fix as `SyncOrchestrator`'s own `_ensure_aware` — SQLite/aiosqlite drops tzinfo on
    read-back (docs/decisions.md ADR-007); a naive value is assumed UTC and stamped to match
    `reference`'s awareness before comparison."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


@dataclass(frozen=True)
class TeamStatisticsSyncOutcome:
    fixture_id: str
    status: str
    """"synced" | "already_present" | "no_data_from_provider" (the sync call itself succeeded but
    fetched zero records — real gap found live: a fixture reconciled only via football-data.org
    has no matching api-sports.io entry to pull box-score stats from, since api-sports.io's own
    football sync is pinned to its free-tier's 2022-2024 season window; honestly distinct from a
    real failure, not conflated with it) | "skipped" (no provider reference, or a real sync
    failure — see `reason`)."""
    reason: str | None = None


@dataclass
class ScheduledTeamStatisticsSyncOrchestrator:
    sync: SyncOrchestrator
    sports: SportRepositoryPort
    fixtures: FixtureRepositoryPort
    matches: MatchRepositoryPort
    team_statistics: TeamStatisticsRepositoryPort
    sport_plugins: SportPluginRegistryPort
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS

    async def run(self, now: datetime) -> list[TeamStatisticsSyncOutcome]:
        outcomes: list[TeamStatisticsSyncOutcome] = []
        for plugin in self.sport_plugins.all():
            sport = await self.sports.get_by_code(plugin.code)
            if sport is None:
                continue
            fixtures = await self.fixtures.list_by_sport(sport.id, status="completed")
            for fixture in fixtures:
                if not self._within_window(fixture.scheduled_at, now):
                    continue
                outcomes.append(await self._sync_one(plugin.code.value, fixture, now))
        return outcomes

    def _within_window(self, scheduled_at: datetime, now: datetime) -> bool:
        scheduled_at = _ensure_aware(scheduled_at, now)
        return now - scheduled_at <= timedelta(hours=self.lookback_hours)

    async def _sync_one(self, sport_code: str, fixture: Fixture, now: datetime) -> TeamStatisticsSyncOutcome:
        fixture_id = str(fixture.id)
        if not fixture.provider_refs:
            return TeamStatisticsSyncOutcome(fixture_id=fixture_id, status="skipped", reason="fixture has no provider reference")

        match = await self.matches.get_by_fixture(fixture.id)
        if match is not None:
            existing = await self.team_statistics.list_by_match(match.id)
            if len(existing) >= 2:
                return TeamStatisticsSyncOutcome(fixture_id=fixture_id, status="already_present")

        try:
            run = await self.sync.sync_team_statistics_for_fixture(sport_code, fixture.provider_refs[0], fixture_id, now)
        except Exception as exc:  # noqa: BLE001 — one fixture's failure must never stop the sweep
            return TeamStatisticsSyncOutcome(fixture_id=fixture_id, status="skipped", reason=f"sync failed: {exc}")

        # A `SyncRun` that succeeded without raising can still have fetched zero real records —
        # `run` is `None` when `_run_sync`'s own checkpoint/lock skipped the attempt entirely, and
        # `records_fetched == 0` when the provider call itself returned nothing (the fixture's
        # only linked provider doesn't publish stats for it) OR failed outright (e.g.
        # ProviderRouter._guard_same_provider refusing a cross-provider fixture-id mismatch —
        # real incident, 2026-08-30). Neither is a genuine "stats now exist" outcome, so both must
        # be reported honestly rather than as "synced" — and a real failure's own `error_message`
        # is surfaced verbatim rather than collapsed into the same generic "no data" reason a
        # provider that legitimately has nothing to report would get.
        if run is not None and run.error_message:
            return TeamStatisticsSyncOutcome(fixture_id=fixture_id, status="skipped", reason=run.error_message)
        if run is None or run.records_fetched == 0:
            return TeamStatisticsSyncOutcome(
                fixture_id=fixture_id, status="no_data_from_provider",
                reason=f"provider {fixture.provider_refs[0].provider!r} returned no team statistics for this fixture",
            )
        return TeamStatisticsSyncOutcome(fixture_id=fixture_id, status="synced")
