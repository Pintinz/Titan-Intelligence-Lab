"""Entity Reconciliation Service (docs/roadmap.md Milestone 5 — "Canonical Domain
Normalization"). Turns validated provider DTOs into persisted, versioned domain entities,
using ``ProviderRefIndexRepositoryPort`` to resolve "have we seen this external id before" in
O(1) instead of scanning every row's ``provider_ref`` JSON column.

One reconciler class, one method per canonical entity — deliberately not a single generic
`_reconcile(dto)` dispatcher: each entity's field mapping and repository differ enough that a
forced-generic version would need as much per-entity branching internally anyway, just hidden
behind one signature instead of eleven readable ones. Shared boilerplate (ref-index lookup,
version bump, timeline emission) lives in three small private helpers used by all eleven.

Every reconcile call: 1) resolves existing identity via the ref index, 2) builds the
updated-or-new entity (version bumped on update), 3) persists it, 4) records the ref index
entry, 5) populates the Knowledge Graph, 6) emits a TimelineEvent. Steps 4-6 are what would
otherwise be "Audit Logging" (docs/roadmap.md Milestone 5) bolted on separately — here they're
just part of what reconciliation always does.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4

from modules.ingestion.domain.entities import ProviderRefIndexEntry, TimelineEvent
from modules.ingestion.domain.value_objects import EntityKind, TimelineEventId, TimelineEventType
from modules.ingestion.ports.repositories import ProviderRefIndexRepositoryPort, TimelineEventRepositoryPort
from modules.alerts.domain.value_objects import AlertType
from modules.alerts.ports.notifier import AlertNotifierPort
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.sports.domain.contracts.fixture import is_valid_fixture_transition, normalize_provider_fixture_status
from modules.sports.domain.entities import (
    Competition,
    Country,
    Fixture,
    Lineup,
    LineupSlot,
    Match,
    Player,
    Season,
    Sport,
    Standing,
    Team,
    TeamStatistics,
    Venue,
)
from modules.sports.domain.value_objects import (
    CompetitionId,
    CompetitionType,
    CountryId,
    DateRange,
    EntityId,
    FixtureId,
    FixtureStatus,
    LineupId,
    LineupRole,
    MatchId,
    PlayerId,
    ProviderRef,
    SeasonId,
    SeasonStatus,
    SportCode,
    SportId,
    TeamId,
    VenueId,
)
from modules.watchlist.domain.value_objects import WatchlistEntityType
from modules.predictions.application.outcome_resolution_service import OutcomeResolutionService
from modules.predictions.application.windowed_feature_engineering_service import FixtureFormDifferentialCalculator
from modules.sports.ports.provider_gateway import (
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderLineupRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
)
from modules.sports.ports.repositories import (
    CompetitionRepositoryPort,
    CountryRepositoryPort,
    FixtureRepositoryPort,
    LineupRepositoryPort,
    MatchRepositoryPort,
    PlayerRepositoryPort,
    SeasonRepositoryPort,
    SportRepositoryPort,
    StandingRepositoryPort,
    TeamRepositoryPort,
    TeamStatisticsRepositoryPort,
    VenueRepositoryPort,
)


def _merge_ref(existing: tuple[ProviderRef, ...], new_ref: ProviderRef) -> tuple[ProviderRef, ...]:
    return existing if new_ref in existing else existing + (new_ref,)


def _derive_season_start(season_label: str, now: datetime) -> datetime:
    """A brand-new season's real start date, not "whenever this reconciliation happened to run" —
    `_pick_current_season` (apps/api/routers/sports_router.py) orders seasons by `date_range.start`
    to decide which one is "current," so stamping it with `now` made that entirely dependent on
    reconciliation order rather than which season is actually current: re-syncing an old season
    after a new one made the old one look more "current." Every season label this codebase has
    ever produced is a bare year (api-football's numeric season year, football-data.org's implicit
    current season) for a European-convention competition, whose season runs August-May — August 1
    of the label year is a real, documented convention, not a fabricated date. Falls back to `now`
    for a label that doesn't parse as a bare year, matching the previous behavior exactly for any
    future non-European-convention sport/competition this doesn't apply to."""
    try:
        year = int(season_label)
    except ValueError:
        return now
    return datetime(year, 8, 1, tzinfo=now.tzinfo)


@dataclass
class EntityReconciliationService:
    sports: SportRepositoryPort
    countries: CountryRepositoryPort
    competitions: CompetitionRepositoryPort
    seasons: SeasonRepositoryPort
    venues: VenueRepositoryPort
    teams: TeamRepositoryPort
    players: PlayerRepositoryPort
    fixtures: FixtureRepositoryPort
    matches: MatchRepositoryPort
    team_statistics: TeamStatisticsRepositoryPort
    lineups: LineupRepositoryPort
    standings: StandingRepositoryPort
    ref_index: ProviderRefIndexRepositoryPort
    kg: KnowledgeGraphPopulationService
    timeline: TimelineEventRepositoryPort
    alerts: AlertNotifierPort | None = None
    outcome_resolver: OutcomeResolutionService | None = None
    # sport_code -> its FixtureFormDifferentialCalculator(s) (only football has any today — audit
    # fix 2026-08-02, see market_seeding.py's module docstring). A dict of tuples, not a single
    # calculator, so adding another sport's differential feature — or another stat_key for an
    # already-covered sport (2026-08-03: possession/shots/corners/fouls/cards joined
    # shots_on_target) — never needs another parameter here.
    form_differential_calculators: dict[str, tuple[FixtureFormDifferentialCalculator, ...]] = field(default_factory=dict)

    # -- shared helpers -----------------------------------------------------------------------

    async def _resolve(self, provider: str, external_id: str, kind: EntityKind) -> str | None:
        return await self.ref_index.get(provider, external_id, kind)

    async def _record_ref(self, provider: str, external_id: str, kind: EntityKind, entity_id: str) -> None:
        await self.ref_index.upsert(ProviderRefIndexEntry(provider, external_id, kind, entity_id))

    async def _emit(
        self, now: datetime, kind: EntityKind, entity_id: str, created: bool, sport_code: str | None = None,
        event_type: TimelineEventType | None = None,
    ) -> None:
        resolved_type = event_type or TimelineEventType.ENTITY_RECONCILED
        await self.timeline.record(
            TimelineEvent(
                id=TimelineEventId(uuid4()), event_type=resolved_type, occurred_at=now, sport_code=sport_code,
                entity_kind=kind, entity_id=entity_id, payload={"created": created},
            )
        )

    # -- Sport ---------------------------------------------------------------------------------

    async def reconcile_sport(self, code: SportCode, name: str, now: datetime) -> tuple[Sport, bool]:
        existing = await self.sports.get_by_code(code)
        created = existing is None
        entity = Sport(
            id=existing.id if existing else SportId(uuid4()), code=code, name=name,
            status=existing.status if existing else "active",
            version=(existing.version + 1) if existing else 1,
            provider_refs=existing.provider_refs if existing else (),
        )
        saved = await self.sports.upsert(entity)
        await self.kg.populate_sport(str(saved.id.value), now, name)
        await self._emit(now, EntityKind.SPORT, str(saved.id.value), created, sport_code=code.value)
        return saved, created

    # -- Country ---------------------------------------------------------------------------------

    async def reconcile_country(self, record: ProviderCountryRecord, now: datetime) -> tuple[Country, bool]:
        existing = await self.countries.get_by_code(record.code)
        created = existing is None
        entity = Country(
            id=existing.id if existing else CountryId(uuid4()), code=record.code, name=record.name,
            version=(existing.version + 1) if existing else 1,
            provider_refs=existing.provider_refs if existing else (),
        )
        saved = await self.countries.upsert(entity)
        await self.kg.populate_country(str(saved.id.value), now, record.code, record.name)
        await self._emit(now, EntityKind.COUNTRY, str(saved.id.value), created)
        return saved, created

    # -- Venue (no dedicated provider DTO — reconciled by name via a synthetic ref-index key) ---

    async def reconcile_venue(self, venue_name: str, provider: str, now: datetime) -> tuple[Venue, bool]:
        synthetic_id = f"venue:{venue_name}"
        existing_id = await self._resolve(provider, synthetic_id, EntityKind.VENUE)
        existing = await self.venues.get(VenueId(_as_uuid(existing_id))) if existing_id else None
        created = existing is None
        entity = Venue(
            id=existing.id if existing else VenueId(uuid4()), name=venue_name,
            city=existing.city if existing else "", country=existing.country if existing else "",
            version=(existing.version + 1) if existing else 1,
            provider_refs=existing.provider_refs if existing else (),
        )
        saved = await self.venues.upsert(entity)
        await self._record_ref(provider, synthetic_id, EntityKind.VENUE, str(saved.id.value))
        await self.kg.populate_venue(str(saved.id.value), now, venue_name)
        await self._emit(now, EntityKind.VENUE, str(saved.id.value), created)
        return saved, created

    # -- Competition -----------------------------------------------------------------------------

    async def reconcile_competition(
        self, competition_ref: str, provider: str, sport_id: SportId, now: datetime,
        name: str | None = None, logo_url: str | None = None,
    ) -> tuple[Competition, bool]:
        existing_id = await self._resolve(provider, competition_ref, EntityKind.COMPETITION)
        existing = await self.competitions.get(CompetitionId(_as_uuid(existing_id))) if existing_id else None
        created = existing is None
        entity = Competition(
            id=existing.id if existing else CompetitionId(uuid4()), sport_id=sport_id,
            name=name or (existing.name if existing else competition_ref),
            type=existing.type if existing else CompetitionType.LEAGUE,
            country=existing.country if existing else None,
            version=(existing.version + 1) if existing else 1,
            logo_url=logo_url if logo_url is not None else (existing.logo_url if existing else None),
        )
        saved = await self.competitions.upsert(entity)
        await self._record_ref(provider, competition_ref, EntityKind.COMPETITION, str(saved.id.value))
        await self.kg.populate_competition(str(saved.id.value), str(sport_id.value), now, name=entity.name)
        await self._emit(now, EntityKind.COMPETITION, str(saved.id.value), created)
        return saved, created

    # -- Season -----------------------------------------------------------------------------------

    async def reconcile_season(
        self, competition_ref: str, season_label: str, provider: str, competition_id: CompetitionId, now: datetime
    ) -> tuple[Season, bool]:
        synthetic_id = f"{competition_ref}:{season_label}"
        existing_id = await self._resolve(provider, synthetic_id, EntityKind.SEASON)
        existing = await self.seasons.get(SeasonId(_as_uuid(existing_id))) if existing_id else None
        created = existing is None
        entity = Season(
            id=existing.id if existing else SeasonId(uuid4()), competition_id=competition_id, label=season_label,
            date_range=existing.date_range if existing else DateRange(start=_derive_season_start(season_label, now)),
            status=existing.status if existing else SeasonStatus.ACTIVE,
            version=(existing.version + 1) if existing else 1,
        )
        saved = await self.seasons.upsert(entity)
        await self._record_ref(provider, synthetic_id, EntityKind.SEASON, str(saved.id.value))
        await self.kg.populate_season(str(saved.id.value), str(competition_id.value), now, label=season_label)
        await self._emit(now, EntityKind.SEASON, str(saved.id.value), created)
        return saved, created

    # -- Team -------------------------------------------------------------------------------------

    async def reconcile_team(
        self, record: ProviderTeamRecord, sport_id: SportId, now: datetime, venue_id: VenueId | None = None
    ) -> tuple[Team, bool]:
        existing_id = await self._resolve(record.external_ref.provider, record.external_ref.external_id, EntityKind.TEAM)
        existing = await self.teams.get(TeamId(_as_uuid(existing_id))) if existing_id else None
        created = existing is None
        entity = Team(
            id=existing.id if existing else TeamId(uuid4()), sport_id=sport_id, name=record.name,
            short_name=record.short_name, country=record.country,
            venue_id=venue_id or (existing.venue_id if existing else None),
            version=(existing.version + 1) if existing else 1,
            provider_refs=_merge_ref(existing.provider_refs if existing else (), record.external_ref),
            logo_url=record.logo_url or (existing.logo_url if existing else None),
        )
        saved = await self.teams.upsert(entity)
        await self._record_ref(record.external_ref.provider, record.external_ref.external_id, EntityKind.TEAM, str(saved.id.value))
        await self.kg.populate_team(str(saved.id.value), str(sport_id.value), now, name=record.name)
        await self._emit(now, EntityKind.TEAM, str(saved.id.value), created)
        return saved, created

    async def reconcile_team_competition(self, team_id: TeamId, competition_id: CompetitionId, now: datetime) -> None:
        await self.kg.populate_team_competition(str(team_id.value), str(competition_id.value), now)

    # -- Player -----------------------------------------------------------------------------------

    async def reconcile_player(
        self, record: ProviderPlayerRecord, sport_id: SportId, now: datetime
    ) -> tuple[Player, bool]:
        team_id_str = await self._resolve(record.team_ref.provider, record.team_ref.external_id, EntityKind.TEAM)
        existing_id = await self._resolve(record.external_ref.provider, record.external_ref.external_id, EntityKind.PLAYER)
        existing = await self.players.get(PlayerId(_as_uuid(existing_id))) if existing_id else None
        created = existing is None
        entity = Player(
            id=existing.id if existing else PlayerId(uuid4()), sport_id=sport_id, name=record.name,
            date_of_birth=record.date_of_birth, position=record.position,
            team_id=TeamId(_as_uuid(team_id_str)) if team_id_str else (existing.team_id if existing else None),
            version=(existing.version + 1) if existing else 1,
            provider_refs=_merge_ref(existing.provider_refs if existing else (), record.external_ref),
        )
        saved = await self.players.upsert(entity)
        await self._record_ref(record.external_ref.provider, record.external_ref.external_id, EntityKind.PLAYER, str(saved.id.value))
        await self.kg.populate_player(
            str(saved.id.value), str(sport_id.value), now, team_id=team_id_str, name=record.name
        )
        await self._emit(now, EntityKind.PLAYER, str(saved.id.value), created)
        return saved, created

    # -- Fixture ----------------------------------------------------------------------------------

    @staticmethod
    def _resolve_fixture_status(existing: Fixture | None, raw_status: str | None) -> FixtureStatus:
        """Previously always froze at ``existing.status`` (or SCHEDULED for a new fixture),
        forever — even ``sync_live_fixtures``'s 30-second poll never actually moved a fixture
        past SCHEDULED, so kickoff/live/final-result never happened anywhere in the system. Now
        applies the provider's reported status through ``Fixture.transition_to``, which itself
        rejects illegal transitions (e.g. a flaky provider briefly reporting a match live again
        after FT) — on rejection this keeps the fixture's current status rather than raising and
        failing the whole sync run over one bad record."""
        if existing is None:
            return normalize_provider_fixture_status(raw_status)
        target = normalize_provider_fixture_status(raw_status)
        if target == existing.status:
            return existing.status
        if not is_valid_fixture_transition(existing.status, target):
            return existing.status
        return target

    async def _find_fixture_by_teams_and_date(
        self, home_team_id: TeamId, away_team_id: TeamId, scheduled_at: datetime
    ) -> Fixture | None:
        """Cross-provider fixture-identity fallback, used only when `reconcile_fixture` is called
        with `match_by_teams_and_date=True` (today: only the football-data.org upcoming-fixture
        sync path). A second provider's own external fixture id never matches the first
        provider's, so the exact `(provider, external_id)` lookup in `reconcile_fixture` always
        misses for a fixture another provider already created — this recognizes "same real-world
        match" by (home team, away team, kickoff within a day) instead, so a second provider's
        report of an already-known fixture updates it rather than creating a duplicate. Returns
        None (safe default: create a new fixture) unless exactly one candidate is found — an
        ambiguous multi-match is treated as "don't guess"."""
        window = timedelta(days=1)
        candidates = await self.fixtures.find_by_teams_and_date_window(
            home_team_id, away_team_id, scheduled_at - window, scheduled_at + window
        )
        return candidates[0] if len(candidates) == 1 else None

    async def reconcile_fixture(
        self, record: ProviderFixtureRecord, season_id: SeasonId, now: datetime, venue_id: VenueId | None = None,
        sport_code: str | None = None, match_by_teams_and_date: bool = False,
    ) -> tuple[Fixture, bool]:
        home_id = await self._resolve(record.home_team_ref.provider, record.home_team_ref.external_id, EntityKind.TEAM)
        away_id = await self._resolve(record.away_team_ref.provider, record.away_team_ref.external_id, EntityKind.TEAM)
        if home_id is None or away_id is None:
            raise ReconciliationDependencyError(
                f"fixture {record.external_ref.external_id} references teams not yet reconciled"
            )
        existing_id = await self._resolve(record.external_ref.provider, record.external_ref.external_id, EntityKind.FIXTURE)
        existing = await self.fixtures.get(FixtureId(_as_uuid(existing_id))) if existing_id else None
        if existing is None and match_by_teams_and_date:
            existing = await self._find_fixture_by_teams_and_date(
                TeamId(_as_uuid(home_id)), TeamId(_as_uuid(away_id)), record.scheduled_at
            )
        created = existing is None
        status = self._resolve_fixture_status(existing, record.status)
        entity = Fixture(
            id=existing.id if existing else FixtureId(uuid4()), season_id=season_id,
            home_team_id=TeamId(_as_uuid(home_id)), away_team_id=TeamId(_as_uuid(away_id)),
            venue_id=venue_id or (existing.venue_id if existing else None), scheduled_at=record.scheduled_at,
            status=status,
            version=(existing.version + 1) if existing else 1,
            provider_refs=_merge_ref(existing.provider_refs if existing else (), record.external_ref),
            home_score=record.home_score if record.home_score is not None else (existing.home_score if existing else None),
            away_score=record.away_score if record.away_score is not None else (existing.away_score if existing else None),
        )
        saved = await self.fixtures.upsert(entity)
        await self._record_ref(record.external_ref.provider, record.external_ref.external_id, EntityKind.FIXTURE, str(saved.id.value))
        await self.kg.populate_fixture(
            str(saved.id.value), home_id, away_id, now, venue_id=str(venue_id.value) if venue_id else None
        )
        await self._emit(
            now, EntityKind.FIXTURE, str(saved.id.value), created,
            event_type=TimelineEventType.FIXTURE_CREATED if created else TimelineEventType.FIXTURE_UPDATED,
        )
        if not created and existing is not None and status != existing.status:
            await self._notify_fixture_status_change(saved, home_id, away_id, now)
        if saved.status is FixtureStatus.COMPLETED and saved.home_score is not None and saved.away_score is not None:
            await self._resolve_prediction_outcomes(saved, now)
        await self._compute_form_differential(saved, sport_code, now)
        return saved, created

    async def _compute_form_differential(self, fixture: Fixture, sport_code: str | None, now: datetime) -> None:
        """Fixture-keyed home-vs-away rolling form differential(s) — the real features
        `PredictionContextBuilder` can actually resolve for a match-level prediction request
        (audit fix 2026-08-02, see market_seeding.py's module docstring). Computed on every
        reconciliation, not gated behind COMPLETED, since pre-match team form is exactly what a
        prediction needs before kickoff. Silently skipped for a sport with no calculator
        registered (only football has any today) or when the caller didn't pass sport_code."""
        if sport_code is None:
            return
        calculators = self.form_differential_calculators.get(sport_code, ())
        for calculator in calculators:
            await calculator.compute_and_write(str(fixture.id.value), fixture.home_team_id, fixture.away_team_id, now)

    async def _resolve_prediction_outcomes(self, fixture: Fixture, now: datetime) -> None:
        if self.outcome_resolver is None:
            return
        await self.outcome_resolver.resolve_for_fixture(
            str(fixture.id.value), fixture.home_score, fixture.away_score, now
        )

    async def _notify_fixture_status_change(self, fixture: Fixture, home_id: str, away_id: str, now: datetime) -> None:
        if self.alerts is None:
            return
        alert_type = (
            AlertType.KICKOFF if fixture.status is FixtureStatus.LIVE
            else AlertType.FINAL_RESULT if fixture.status is FixtureStatus.COMPLETED
            else None
        )
        if alert_type is None:
            return
        home = await self.teams.get(fixture.home_team_id)
        away = await self.teams.get(fixture.away_team_id)
        matchup = f"{home.name if home else 'Home'} vs {away.name if away else 'Away'}"
        title = "Kickoff" if alert_type is AlertType.KICKOFF else "Full time"
        body = f"{matchup} has kicked off." if alert_type is AlertType.KICKOFF else f"{matchup} has finished."
        fixture_id = str(fixture.id.value)
        await self.alerts.notify_watchers(WatchlistEntityType.FIXTURE, fixture_id, alert_type, title, body, now)
        # "Favorite Team" alerts: notify anyone following either team too, not just fixture watchers.
        for team_id in {home_id, away_id}:
            await self.alerts.notify_watchers(WatchlistEntityType.TEAM, team_id, alert_type, title, body, now)

    # -- Match --------------------------------------------------------------------------------------

    async def get_or_create_match(self, fixture_id: FixtureId, now: datetime) -> Match:
        """`Match` (started_at/ended_at/final_state) has no provider-side identity of its own —
        `MatchModel.fixture_id` is a unique FK, so it always exists 1:1 with its `Fixture` — there
        is nothing to reconcile against a provider the way Team/Player/Fixture rows are. Callers
        that need a `MatchId` (e.g. `reconcile_team_statistics`) call this first rather than
        constructing one, so the row is created on first use instead of needing its own sync step."""
        existing = await self.matches.get_by_fixture(fixture_id)
        if existing is not None:
            return existing
        return await self.matches.upsert(Match(id=MatchId(uuid4()), fixture_id=fixture_id, started_at=None, ended_at=None))

    # -- Team Statistics ("Match Statistics") ------------------------------------------------------

    async def reconcile_team_statistics(
        self, record: ProviderTeamStatisticsRecord, match_id: MatchId, now: datetime
    ) -> tuple[TeamStatistics, bool]:
        team_id_str = await self._resolve(record.team_ref.provider, record.team_ref.external_id, EntityKind.TEAM)
        if team_id_str is None:
            raise ReconciliationDependencyError(f"team {record.team_ref.external_id} not yet reconciled")
        team_id = TeamId(_as_uuid(team_id_str))

        existing = await self.team_statistics.get_for_match_team(match_id, team_id)
        created = existing is None
        entity = TeamStatistics(
            id=existing.id if existing else EntityId(uuid4()), match_id=match_id, team_id=team_id,
            stat_set=record.stat_set, version=(existing.version + 1) if existing else 1,
            provider_refs=_merge_ref(
                existing.provider_refs if existing else (),
                ProviderRef(provider=record.team_ref.provider, external_id=record.fixture_ref.external_id),
            ),
        )
        saved = await self.team_statistics.upsert(entity)
        await self.kg.populate_team_statistics(str(match_id.value), str(team_id.value), now)
        await self._emit(
            now, EntityKind.TEAM_STATISTICS, str(saved.id.value), created,
            event_type=TimelineEventType.STATISTICS_FINALIZED,
        )
        return saved, created

    # -- Lineup -------------------------------------------------------------------------------------

    async def reconcile_lineup(
        self, record: ProviderLineupRecord, match_id: MatchId, now: datetime
    ) -> tuple[Lineup, bool, list[str]]:
        """Returns ``(lineup, created, unresolved_player_refs)`` — a slot whose player hasn't
        been reconciled yet is skipped and reported rather than failing the whole lineup."""
        team_id_str = await self._resolve(record.team_ref.provider, record.team_ref.external_id, EntityKind.TEAM)
        if team_id_str is None:
            raise ReconciliationDependencyError(f"team {record.team_ref.external_id} not yet reconciled")
        team_id = TeamId(_as_uuid(team_id_str))

        slots = []
        unresolved: list[str] = []
        for slot in record.slots:
            player_id_str = await self._resolve(slot.player_ref.provider, slot.player_ref.external_id, EntityKind.PLAYER)
            if player_id_str is None:
                unresolved.append(slot.player_ref.external_id)
                continue
            slots.append(
                LineupSlot(
                    player_id=PlayerId(_as_uuid(player_id_str)), role=LineupRole(slot.role),
                    position=slot.position, shirt_number=slot.shirt_number,
                )
            )

        existing = await self.lineups.get_for_match_team(match_id, team_id)
        created = existing is None
        entity = Lineup(
            id=existing.id if existing else LineupId(uuid4()), match_id=match_id, team_id=team_id,
            formation=record.formation, slots=tuple(slots), version=(existing.version + 1) if existing else 1,
        )
        saved = await self.lineups.upsert(entity)
        await self._emit(now, EntityKind.LINEUP, str(saved.id.value), created)
        return saved, created, unresolved

    # -- Standing -------------------------------------------------------------------------------------

    async def reconcile_standing(
        self, record: ProviderStandingRecord, season_id: SeasonId, now: datetime
    ) -> Standing:
        """Standings are point-in-time snapshots — every call inserts a new row (the sync
        time IS the snapshot time), preserving history rather than overwriting in place."""
        team_id_str = await self._resolve(record.team_ref.provider, record.team_ref.external_id, EntityKind.TEAM)
        if team_id_str is None:
            raise ReconciliationDependencyError(f"team {record.team_ref.external_id} not yet reconciled")
        team_id = TeamId(_as_uuid(team_id_str))

        entity = Standing(
            id=EntityId(uuid4()), season_id=season_id, team_id=team_id, snapshot_at=now,
            rank=record.rank, points=record.points, record=record.record,
        )
        saved = await self.standings.upsert(entity)
        await self.kg.populate_standing(str(team_id.value), str(season_id.value), now, rank=record.rank, points=record.points)
        await self._emit(now, EntityKind.STANDING, str(saved.id.value), created=True)
        return saved


class ReconciliationDependencyError(RuntimeError):
    """A record references another entity (team, fixture, player) that hasn't been reconciled
    yet — the orchestrator must sync dependencies in order (Sport -> Competition -> Season ->
    Venue/Team -> Player -> Fixture -> Statistics/Lineup/Standing)."""


def _as_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)
