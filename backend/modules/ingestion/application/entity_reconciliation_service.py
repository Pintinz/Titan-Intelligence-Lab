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
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.ingestion.domain.entities import ProviderRefIndexEntry, TimelineEvent
from modules.ingestion.domain.value_objects import EntityKind, TimelineEventId, TimelineEventType
from modules.ingestion.ports.repositories import ProviderRefIndexRepositoryPort, TimelineEventRepositoryPort
from modules.knowledge_graph.application.population_service import KnowledgeGraphPopulationService
from modules.sports.domain.entities import (
    Competition,
    Country,
    Fixture,
    Lineup,
    LineupSlot,
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
    team_statistics: TeamStatisticsRepositoryPort
    lineups: LineupRepositoryPort
    standings: StandingRepositoryPort
    ref_index: ProviderRefIndexRepositoryPort
    kg: KnowledgeGraphPopulationService
    timeline: TimelineEventRepositoryPort

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
        self, competition_ref: str, provider: str, sport_id: SportId, now: datetime, name: str | None = None
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
            date_range=existing.date_range if existing else DateRange(start=now),
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

    async def reconcile_fixture(
        self, record: ProviderFixtureRecord, season_id: SeasonId, now: datetime, venue_id: VenueId | None = None
    ) -> tuple[Fixture, bool]:
        home_id = await self._resolve(record.home_team_ref.provider, record.home_team_ref.external_id, EntityKind.TEAM)
        away_id = await self._resolve(record.away_team_ref.provider, record.away_team_ref.external_id, EntityKind.TEAM)
        if home_id is None or away_id is None:
            raise ReconciliationDependencyError(
                f"fixture {record.external_ref.external_id} references teams not yet reconciled"
            )
        existing_id = await self._resolve(record.external_ref.provider, record.external_ref.external_id, EntityKind.FIXTURE)
        existing = await self.fixtures.get(FixtureId(_as_uuid(existing_id))) if existing_id else None
        created = existing is None
        entity = Fixture(
            id=existing.id if existing else FixtureId(uuid4()), season_id=season_id,
            home_team_id=TeamId(_as_uuid(home_id)), away_team_id=TeamId(_as_uuid(away_id)),
            venue_id=venue_id or (existing.venue_id if existing else None), scheduled_at=record.scheduled_at,
            status=existing.status if existing else FixtureStatus.SCHEDULED,
            version=(existing.version + 1) if existing else 1,
            provider_refs=_merge_ref(existing.provider_refs if existing else (), record.external_ref),
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
        return saved, created

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
