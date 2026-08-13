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

from modules.ingestion.application.provenance import LINEUP_PREMATCH_WINDOW_MINUTES, classify_availability
from modules.ingestion.domain.entities import ProviderRefIndexEntry, TimelineEvent
from modules.ingestion.domain.value_objects import EntityKind, SyncTrigger, TimelineEventId, TimelineEventType
from modules.ingestion.ports.repositories import ProviderRefIndexRepositoryPort, TimelineEventRepositoryPort
from modules.alerts.domain.value_objects import AlertType
from modules.alerts.ports.notifier import AlertNotifierPort
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.sports.domain.contracts.fixture import is_valid_fixture_transition, normalize_provider_fixture_status
from modules.sports.domain.entities import (
    CoachingStaffMember,
    Competition,
    Country,
    Fixture,
    Injury,
    Lineup,
    LineupSlot,
    Match,
    Player,
    Season,
    Sport,
    Standing,
    Team,
    TeamStatistics,
    Transfer,
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
from modules.predictions.application.news_market_impact_engine import NewsMarketImpactEngine
from modules.predictions.application.outcome_resolution_service import OutcomeResolutionService
from modules.predictions.application.windowed_feature_engineering_service import (
    FixtureFormDifferentialCalculator,
    LineupContinuityCalculator,
    TransferActivityCalculator,
)
from modules.sports.ports.provider_gateway import (
    ProviderCoachRecord,
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderInjuryRecord,
    ProviderLineupRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
    ProviderTransferRecord,
)
from modules.sports.ports.repositories import (
    CoachingStaffRepositoryPort,
    CompetitionRepositoryPort,
    CountryRepositoryPort,
    FixtureRepositoryPort,
    InjuryRepositoryPort,
    LineupRepositoryPort,
    MatchRepositoryPort,
    PlayerRepositoryPort,
    SeasonRepositoryPort,
    SportRepositoryPort,
    StandingRepositoryPort,
    TeamRepositoryPort,
    TeamStatisticsRepositoryPort,
    TransferRepositoryPort,
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
    injuries: InjuryRepositoryPort
    transfers: TransferRepositoryPort
    coaching_staff: CoachingStaffRepositoryPort
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
    # Milestone 6 — sport_code -> (home, away) LineupContinuityCalculator pair, same
    # dict-by-sport-code shape as form_differential_calculators above (and for the same reason:
    # lineups only exist for football today, but a future sport must not silently inherit
    # football's calculators). Empty dict default means every existing caller that doesn't pass
    # fixture_id/home_team_id keeps working exactly as before.
    lineup_continuity_calculators: dict[str, tuple[LineupContinuityCalculator, LineupContinuityCalculator]] = field(default_factory=dict)
    # Milestone 7 — sport_code -> (home, away) TransferActivityCalculator pair, same
    # dict-by-sport-code shape as the two fields above and for the same reason. Unlike lineup
    # continuity (only fires from reconcile_lineup, which already has fixture context via
    # sync_lineups), transfer activity is computed from reconcile_fixture directly — a transfer
    # record has no fixture of its own to attach to, so the signal is derived per-fixture the
    # same way form_differential_calculators already is.
    transfer_activity_calculators: dict[str, tuple[TransferActivityCalculator, TransferActivityCalculator]] = field(default_factory=dict)
    # Milestone 9 — sport_code -> one NewsMarketImpactEngine (unlike the home/away calculator
    # pairs above, one engine instance handles both sides — `compute_and_write` takes a `side`
    # parameter instead, since it needs to scan a full roster per call regardless of side).
    news_market_impact_engines: dict[str, NewsMarketImpactEngine] = field(default_factory=dict)

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
        if existing_id is None and record.cross_provider_ref is not None:
            # Deterministic auto-merge: the provider itself claims this is the same club as an
            # already-reconciled team under a different provider — see ProviderTeamRecord's
            # `cross_provider_ref` docstring. Only engages the first time this record's own
            # external_ref is seen; once reconciled it resolves normally like any other team.
            existing_id = await self._resolve(
                record.cross_provider_ref.provider, record.cross_provider_ref.external_id, EntityKind.TEAM
            )
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
    def _resolve_fixture_status(
        existing: Fixture | None, raw_status: str | None, *, allow_skip_live: bool = False
    ) -> FixtureStatus:
        """Previously always froze at ``existing.status`` (or SCHEDULED for a new fixture),
        forever — even ``sync_live_fixtures``'s 30-second poll never actually moved a fixture
        past SCHEDULED, so kickoff/live/final-result never happened anywhere in the system. Now
        applies the provider's reported status through ``Fixture.transition_to``, which itself
        rejects illegal transitions (e.g. a flaky provider briefly reporting a match live again
        after FT) — on rejection this keeps the fixture's current status rather than raising and
        failing the whole sync run over one bad record.

        ``allow_skip_live`` is the one deliberate, narrow exception to that lifecycle: it's set
        only by ``sync_completed_fixtures``'s football-data.org path, whose free-tier adapter
        structurally never reports IN_PLAY (it only ever polls SCHEDULED/TIMED, then later
        FINISHED — see ``FootballDataOrgAdapter``'s module docstring), so a real, legitimate
        finished match would otherwise be permanently rejected by the SCHEDULED->COMPLETED ban and
        sit stuck at SCHEDULED forever. Every other transition rule (including the "never go
        backward out of COMPLETED" rule this exception does not touch) still applies unchanged."""
        if existing is None:
            return normalize_provider_fixture_status(raw_status)
        target = normalize_provider_fixture_status(raw_status)
        if target == existing.status:
            return existing.status
        if is_valid_fixture_transition(existing.status, target):
            return target
        if allow_skip_live and existing.status is FixtureStatus.SCHEDULED and target is FixtureStatus.COMPLETED:
            return target
        return existing.status

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
        sport_code: str | None = None, match_by_teams_and_date: bool = False, allow_skip_live: bool = False,
        preserve_existing_score: bool = False,
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
        status = self._resolve_fixture_status(existing, record.status, allow_skip_live=allow_skip_live)
        # `preserve_existing_score`: a supplementary (non-authoritative) source's own score never
        # overwrites one an existing fixture already has — only fills in if genuinely absent.
        # Default (False) keeps the long-standing "a fetched score always wins" behavior every
        # existing caller (api-football, football-data.org) already relies on; this is opt-in
        # per-caller, not a global behavior change (see SyncOrchestrator.sync_completed_fixtures).
        existing_has_score = existing is not None and existing.home_score is not None and existing.away_score is not None
        score_locked = preserve_existing_score and existing_has_score
        entity = Fixture(
            id=existing.id if existing else FixtureId(uuid4()), season_id=season_id,
            home_team_id=TeamId(_as_uuid(home_id)), away_team_id=TeamId(_as_uuid(away_id)),
            venue_id=venue_id or (existing.venue_id if existing else None), scheduled_at=record.scheduled_at,
            status=status,
            version=(existing.version + 1) if existing else 1,
            provider_refs=_merge_ref(existing.provider_refs if existing else (), record.external_ref),
            home_score=existing.home_score if score_locked else (record.home_score if record.home_score is not None else (existing.home_score if existing else None)),
            away_score=existing.away_score if score_locked else (record.away_score if record.away_score is not None else (existing.away_score if existing else None)),
            period_scores=existing.period_scores if score_locked else (record.period_scores if record.period_scores is not None else (existing.period_scores if existing else None)),
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
        await self._compute_transfer_activity(saved, sport_code, now)
        await self._compute_news_market_impact(saved, sport_code, now)
        return saved, created

    async def _compute_news_market_impact(self, fixture: Fixture, sport_code: str | None, now: datetime) -> None:
        """Milestone 9 — same "every reconciliation, not gated on completion" reasoning as
        `_compute_form_differential`/`_compute_transfer_activity` above. Like transfer activity,
        a `NewsEvent` has no fixture of its own to attach to (it affects a player/team across
        every future fixture, not one specific match), so the signal is derived per-fixture here.

        Milestone 10: passes this fixture's own `scheduled_at` as `kickoff` — the direct,
        fixture-specific "no post-kickoff information" guard `NewsMarketImpactEngine` now applies
        on top of its existing TTL-window check."""
        if sport_code is None:
            return
        engine = self.news_market_impact_engines.get(sport_code)
        if engine is None:
            return
        fixture_id = str(fixture.id.value)
        await engine.compute_and_write(fixture_id, fixture.home_team_id, "home", now, kickoff=fixture.scheduled_at)
        await engine.compute_and_write(fixture_id, fixture.away_team_id, "away", now, kickoff=fixture.scheduled_at)

    async def _compute_transfer_activity(self, fixture: Fixture, sport_code: str | None, now: datetime) -> None:
        """Milestone 7 — fixture-keyed home/away squad-churn signal, computed on every
        reconciliation exactly like `_compute_form_differential` above (same reasoning: pre-match
        squad state is what a prediction needs before kickoff, not just after). Silently skipped
        for a sport with no calculator registered or when the caller didn't pass sport_code."""
        if sport_code is None:
            return
        calculators = self.transfer_activity_calculators.get(sport_code, ())
        if not calculators:
            return
        home_calculator, away_calculator = calculators
        fixture_id = str(fixture.id.value)
        await home_calculator.compute_and_write(fixture_id, fixture.home_team_id, now)
        await away_calculator.compute_and_write(fixture_id, fixture.away_team_id, now)

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
        self, record: ProviderLineupRecord, match_id: MatchId, now: datetime, *,
        trigger: SyncTrigger = SyncTrigger.MANUAL, sync_run_id: str | None = None,
        kickoff: datetime | None = None, fixture_status: FixtureStatus | None = None,
        fixture_id: str | None = None, home_team_id: TeamId | None = None, sport_code: str | None = None,
    ) -> tuple[Lineup, bool, list[str]]:
        """Returns ``(lineup, created, unresolved_player_refs)`` — a slot whose player hasn't
        been reconciled yet is skipped and reported rather than failing the whole lineup.

        Milestone 5 (Verified Pre-Match Data Availability): ``trigger``/``kickoff``/
        ``fixture_status`` feed `classify_availability` (modules.ingestion.application.provenance)
        — defaults are deliberately conservative (``SyncTrigger.MANUAL``, no kickoff) so any
        caller that doesn't pass them (existing tests, ad-hoc scripts) gets the same
        ``UNKNOWN_AVAILABILITY_TIME`` result this method always produced before this milestone,
        never an accidental ``VERIFIED_PRE_MATCH`` promotion.

        Milestone 6: ``fixture_id``/``home_team_id`` (both optional, same conservative-default
        posture) let this method pick the right home/away `LineupContinuityCalculator` — needed
        because the feature is written under `EntityType.FIXTURE`, and this method otherwise only
        knows `match_id`, not the fixture or which side `team_id` resolves to."""
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

        availability = classify_availability(
            trigger=trigger, sync_succeeded=True, validated=True, applicable=True, sync_time=now,
            kickoff=kickoff, prematch_window_minutes=LINEUP_PREMATCH_WINDOW_MINUTES, fixture_status=fixture_status,
        )

        existing = await self.lineups.get_for_match_team(match_id, team_id)
        created = existing is None
        entity = Lineup(
            id=existing.id if existing else LineupId(uuid4()), match_id=match_id, team_id=team_id,
            formation=record.formation, slots=tuple(slots), version=(existing.version + 1) if existing else 1,
            availability_classification=availability.classification.value,
            information_available_at=availability.information_available_at,
            fetched_at=now, sync_run_id=sync_run_id,
        )
        saved = await self.lineups.upsert(entity)
        await self._emit(now, EntityKind.LINEUP, str(saved.id.value), created)

        calculators = self.lineup_continuity_calculators.get(sport_code, ()) if sport_code else ()
        if calculators and fixture_id is not None and home_team_id is not None:
            home_calc, away_calc = calculators
            calculator = home_calc if team_id == home_team_id else away_calc
            await calculator.compute_and_write(fixture_id, team_id, saved, now)

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

    # -- Injury -------------------------------------------------------------------------------

    async def reconcile_injury(
        self, record: ProviderInjuryRecord, now: datetime, *,
        trigger: SyncTrigger = SyncTrigger.MANUAL, sync_run_id: str | None = None,
    ) -> tuple[Injury, bool]:
        """One row per player, updated in place on each sync (like Lineup/TeamStatistics, not
        appended like Standing) — the provider's `/injuries` endpoint always reports a player's
        *current* unavailability, not a historical log, so re-syncing the same player's injury
        naturally means "here's the latest known status," not a new event. The ref-index key is
        synthetic (player, not the record itself, since the provider has no persistent injury-
        record id) so the same player's row is found and updated rather than duplicated.

        Milestone 5: `has_genuine_timestamp=False` is hardcoded below, not entity-specific data —
        no connected provider adapter supplies a real injury report/publication timestamp today
        (see `ApiFootballAdapter.fetch_injuries`'s docstring: `reported_at` is actually the
        fixture's kickoff). This means an injury never reaches VERIFIED_PRE_MATCH today regardless
        of `trigger`, exactly per the spec's explicit "do not mark VERIFIED_PRE_MATCH merely
        because it was retrieved by a scheduled task" instruction — flip this the day a provider
        genuinely supplies one, not before."""
        player_id_str = await self._resolve(record.player_ref.provider, record.player_ref.external_id, EntityKind.PLAYER)
        if player_id_str is None:
            raise ReconciliationDependencyError(f"player {record.player_ref.external_id} not yet reconciled")
        player_id = PlayerId(_as_uuid(player_id_str))

        synthetic_id = f"injury:{record.player_ref.external_id}"
        existing_id = await self._resolve(record.player_ref.provider, synthetic_id, EntityKind.INJURY)
        existing = await self.injuries.get(EntityId(_as_uuid(existing_id))) if existing_id else None
        created = existing is None
        availability = classify_availability(
            trigger=trigger, sync_succeeded=True, validated=True, applicable=True, sync_time=now,
            has_genuine_timestamp=False,
        )
        entity = Injury(
            id=existing.id if existing else EntityId(uuid4()),
            player_id=player_id,
            reported_at=record.reported_at or now,
            status=record.status,
            reason=record.reason,
            expected_return=None,
            version=(existing.version + 1) if existing else 1,
            provider_refs=_merge_ref(existing.provider_refs if existing else (), record.player_ref),
            availability_classification=availability.classification.value,
            information_available_at=availability.information_available_at,
            fetched_at=now, sync_run_id=sync_run_id,
        )
        saved = await self.injuries.upsert(entity)
        await self._record_ref(record.player_ref.provider, synthetic_id, EntityKind.INJURY, str(saved.id.value))
        await self._emit(now, EntityKind.INJURY, str(saved.id.value), created)
        return saved, created

    # -- Transfer -----------------------------------------------------------------------------

    async def reconcile_transfer(
        self, record: ProviderTransferRecord, now: datetime, *,
        trigger: SyncTrigger = SyncTrigger.MANUAL, sync_run_id: str | None = None,
    ) -> Transfer:
        """Unlike Injury, every distinct transfer is a genuine historical event — the synthetic
        ref-index key includes the effective date and destination team so re-syncing a player's
        transfer history is idempotent (same move never duplicates) while two different real
        moves for the same player both persist.

        Milestone 5: unlike Injury, no provider field here is actively wrong/mislabeled — a
        transfer just has no separate "announced_at" (only `effective_date`, its own real but
        distinct field, per the spec's explicit "do not conflate effective/announcement/
        registration dates" instruction). `information_available_at` is never derived from
        `effective_date` — it's the reconciliation `now`, exactly like every other entity, gated
        the same way (only a genuine `LIVE_SCHEDULED` sync can produce VERIFIED_PRE_MATCH). No
        kickoff-proximity gate applies — a transfer isn't bound to one fixture's kickoff the way a
        lineup is; it affects a player's squad status across every future fixture."""
        availability = classify_availability(
            trigger=trigger, sync_succeeded=True, validated=True, applicable=True, sync_time=now,
        )
        from_team_id = None
        if record.from_team_ref is not None:
            from_team_id_str = await self._resolve(record.from_team_ref.provider, record.from_team_ref.external_id, EntityKind.TEAM)
            from_team_id = TeamId(_as_uuid(from_team_id_str)) if from_team_id_str else None
        to_team_id = None
        if record.to_team_ref is not None:
            to_team_id_str = await self._resolve(record.to_team_ref.provider, record.to_team_ref.external_id, EntityKind.TEAM)
            to_team_id = TeamId(_as_uuid(to_team_id_str)) if to_team_id_str else None

        player_id_str = await self._resolve(record.player_ref.provider, record.player_ref.external_id, EntityKind.PLAYER)
        if player_id_str is None:
            raise ReconciliationDependencyError(f"player {record.player_ref.external_id} not yet reconciled")
        player_id = PlayerId(_as_uuid(player_id_str))

        synthetic_id = f"transfer:{record.player_ref.external_id}:{record.effective_date.date().isoformat()}:{to_team_id or from_team_id}"
        existing_id = await self._resolve(record.player_ref.provider, synthetic_id, EntityKind.TRANSFER)
        existing = await self.transfers.get(EntityId(_as_uuid(existing_id))) if existing_id else None
        entity = Transfer(
            id=existing.id if existing else EntityId(uuid4()),
            player_id=player_id, from_team_id=from_team_id, to_team_id=to_team_id,
            effective_date=record.effective_date, transfer_type=record.transfer_type,
            version=(existing.version + 1) if existing else 1,
            provider_refs=_merge_ref(existing.provider_refs if existing else (), record.player_ref),
            availability_classification=availability.classification.value,
            information_available_at=availability.information_available_at,
            fetched_at=now, sync_run_id=sync_run_id,
        )
        saved = await self.transfers.upsert(entity)
        await self._record_ref(record.player_ref.provider, synthetic_id, EntityKind.TRANSFER, str(saved.id.value))
        await self._emit(now, EntityKind.TRANSFER, str(saved.id.value), created=existing is None)
        return saved

    # -- Coaching staff -------------------------------------------------------------------------

    async def reconcile_coaching_staff(
        self, record: ProviderCoachRecord, now: datetime
    ) -> tuple[CoachingStaffMember, bool]:
        """Time-aware: if the currently-active (``valid_to is None``) coach for this team/role is
        a *different* person, that row is closed (``valid_to`` set to ``now``) and a new row is
        created for the incoming person — history is never overwritten. If it's the same person,
        this is a no-op re-confirmation, not a new row."""
        team_id_str = await self._resolve(record.team_ref.provider, record.team_ref.external_id, EntityKind.TEAM)
        if team_id_str is None:
            raise ReconciliationDependencyError(f"team {record.team_ref.external_id} not yet reconciled")
        team_id = TeamId(_as_uuid(team_id_str))

        current = await self.coaching_staff.get_current_by_team(team_id, record.role)
        if current is not None and current.person_name == record.person_name:
            return current, False

        if current is not None:
            closed = CoachingStaffMember(
                id=current.id, team_id=current.team_id, person_name=current.person_name, role=current.role,
                valid_from=current.valid_from, valid_to=now, version=current.version + 1,
                provider_refs=current.provider_refs,
            )
            await self.coaching_staff.upsert(closed)

        entity = CoachingStaffMember(
            id=EntityId(uuid4()), team_id=team_id, person_name=record.person_name, role=record.role,
            valid_from=now, valid_to=None, version=1, provider_refs=(record.team_ref,),
        )
        saved = await self.coaching_staff.upsert(entity)
        await self._emit(now, EntityKind.COACHING_STAFF, str(saved.id.value), created=True)
        return saved, True


class ReconciliationDependencyError(RuntimeError):
    """A record references another entity (team, fixture, player) that hasn't been reconciled
    yet — the orchestrator must sync dependencies in order (Sport -> Competition -> Season ->
    Venue/Team -> Player -> Fixture -> Statistics/Lineup/Standing)."""


def _as_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)
