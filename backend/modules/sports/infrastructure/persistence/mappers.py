"""Bidirectional mapping between domain entities and ORM models.

Keeps the ORM model shape (dict-based provider_ref column, docs/database_schema.md §1) out of
the domain layer, and keeps typed domain value objects (TeamId, ProviderRef, ...) out of the
persistence layer's row shape.
"""

from __future__ import annotations

import uuid

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
from modules.sports.infrastructure.persistence.models import (
    CoachingStaffModel,
    CompetitionModel,
    CountryModel,
    FixtureModel,
    InjuryModel,
    LineupModel,
    MatchModel,
    PlayerModel,
    SeasonModel,
    SportModel,
    StandingModel,
    TeamModel,
    TeamStatisticsModel,
    TransferModel,
    VenueModel,
)


def sport_to_domain(model: SportModel) -> Sport:
    return Sport(
        id=SportId(model.id),
        code=SportCode(model.code),
        name=model.name,
        status=model.status,
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
    )


def sport_to_model(entity: Sport, model: SportModel | None = None) -> SportModel:
    model = model or SportModel(id=entity.id.value)
    model.code = entity.code.value
    model.name = entity.name
    model.status = entity.status
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    return model


def country_to_domain(model: CountryModel) -> Country:
    return Country(
        id=CountryId(model.id), code=model.code, name=model.name,
        version=model.version, provider_refs=_provider_refs_from_dict(model.provider_ref),
    )


def country_to_model(entity: Country, model: CountryModel | None = None) -> CountryModel:
    model = model or CountryModel(id=entity.id.value)
    model.code = entity.code
    model.name = entity.name
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    return model


def _provider_refs_to_dict(refs: tuple[ProviderRef, ...]) -> dict[str, str]:
    return {ref.provider: ref.external_id for ref in refs}


def _provider_refs_from_dict(data: dict[str, str]) -> tuple[ProviderRef, ...]:
    return tuple(ProviderRef(provider=k, external_id=v) for k, v in data.items())


def venue_to_domain(model: VenueModel) -> Venue:
    return Venue(
        id=VenueId(model.id),
        name=model.name,
        city=model.city,
        country=model.country,
        capacity=model.capacity,
        surface=model.surface,
        timezone=model.timezone,
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
    )


def venue_to_model(entity: Venue, model: VenueModel | None = None) -> VenueModel:
    model = model or VenueModel(id=entity.id.value)
    model.name = entity.name
    model.city = entity.city
    model.country = entity.country
    model.capacity = entity.capacity
    model.surface = entity.surface
    model.timezone = entity.timezone
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    return model


def team_to_domain(model: TeamModel) -> Team:
    return Team(
        id=TeamId(model.id),
        sport_id=SportId(model.sport_id),
        name=model.name,
        short_name=model.short_name,
        country=model.country,
        venue_id=VenueId(model.venue_id) if model.venue_id else None,
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
        logo_url=model.logo_url,
    )


def team_to_model(entity: Team, model: TeamModel | None = None) -> TeamModel:
    model = model or TeamModel(id=entity.id.value)
    model.sport_id = entity.sport_id.value
    model.name = entity.name
    model.short_name = entity.short_name
    model.country = entity.country
    model.venue_id = entity.venue_id.value if entity.venue_id else None
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    model.logo_url = entity.logo_url
    return model


def player_to_domain(model: PlayerModel) -> Player:
    return Player(
        id=PlayerId(model.id),
        sport_id=SportId(model.sport_id),
        name=model.name,
        date_of_birth=model.date_of_birth,
        position=model.position,
        team_id=TeamId(model.team_id) if model.team_id else None,
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
    )


def player_to_model(entity: Player, model: PlayerModel | None = None) -> PlayerModel:
    model = model or PlayerModel(id=entity.id.value)
    model.sport_id = entity.sport_id.value
    model.name = entity.name
    model.date_of_birth = entity.date_of_birth
    model.position = entity.position
    model.team_id = entity.team_id.value if entity.team_id else None
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    return model


def competition_to_domain(model: CompetitionModel) -> Competition:
    return Competition(
        id=CompetitionId(model.id),
        sport_id=SportId(model.sport_id),
        name=model.name,
        type=CompetitionType(model.type),
        country=model.country,
        tier=model.tier,
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
        logo_url=model.logo_url,
    )


def competition_to_model(
    entity: Competition, model: CompetitionModel | None = None
) -> CompetitionModel:
    model = model or CompetitionModel(id=entity.id.value)
    model.sport_id = entity.sport_id.value
    model.name = entity.name
    model.type = entity.type.value
    model.country = entity.country
    model.tier = entity.tier
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    model.logo_url = entity.logo_url
    return model


def season_to_domain(model: SeasonModel) -> Season:
    return Season(
        id=SeasonId(model.id),
        competition_id=CompetitionId(model.competition_id),
        label=model.label,
        date_range=DateRange(start=model.start_date, end=model.end_date),
        status=SeasonStatus(model.status),
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
    )


def season_to_model(entity: Season, model: SeasonModel | None = None) -> SeasonModel:
    model = model or SeasonModel(id=entity.id.value)
    model.competition_id = entity.competition_id.value
    model.label = entity.label
    model.start_date = entity.date_range.start
    model.end_date = entity.date_range.end
    model.status = entity.status.value
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    return model


def fixture_to_domain(model: FixtureModel) -> Fixture:
    return Fixture(
        id=FixtureId(model.id),
        season_id=SeasonId(model.season_id),
        home_team_id=TeamId(model.home_team_id),
        away_team_id=TeamId(model.away_team_id),
        venue_id=VenueId(model.venue_id) if model.venue_id else None,
        scheduled_at=model.scheduled_at,
        status=FixtureStatus(model.status),
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
        home_score=model.home_score,
        away_score=model.away_score,
        period_scores=model.period_scores,
    )


def fixture_to_model(entity: Fixture, model: FixtureModel | None = None) -> FixtureModel:
    model = model or FixtureModel(id=entity.id.value)
    model.season_id = entity.season_id.value
    model.home_team_id = entity.home_team_id.value
    model.away_team_id = entity.away_team_id.value
    model.venue_id = entity.venue_id.value if entity.venue_id else None
    model.scheduled_at = entity.scheduled_at
    model.status = entity.status.value
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    model.home_score = entity.home_score
    model.away_score = entity.away_score
    model.period_scores = entity.period_scores
    return model


def standing_to_domain(model: StandingModel) -> Standing:
    return Standing(
        id=EntityId(model.id),
        season_id=SeasonId(model.season_id),
        team_id=TeamId(model.team_id),
        snapshot_at=model.snapshot_at,
        rank=model.rank,
        points=model.points,
        record=model.record,
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
    )


def standing_to_model(entity: Standing, model: StandingModel | None = None) -> StandingModel:
    model = model or StandingModel(id=entity.id.value)
    model.season_id = entity.season_id.value
    model.team_id = entity.team_id.value
    model.snapshot_at = entity.snapshot_at
    model.rank = entity.rank
    model.points = entity.points
    model.record = entity.record
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    return model


def match_to_domain(model: MatchModel) -> Match:
    return Match(
        id=MatchId(model.id),
        fixture_id=FixtureId(model.fixture_id),
        started_at=model.started_at,
        ended_at=model.ended_at,
        final_state=model.final_state,
    )


def match_to_model(entity: Match, model: MatchModel | None = None) -> MatchModel:
    model = model or MatchModel(id=entity.id.value)
    model.fixture_id = entity.fixture_id.value
    model.started_at = entity.started_at
    model.ended_at = entity.ended_at
    model.final_state = entity.final_state
    return model


def team_statistics_to_domain(model: TeamStatisticsModel) -> TeamStatistics:
    return TeamStatistics(
        id=EntityId(model.id),
        match_id=MatchId(model.match_id),
        team_id=TeamId(model.team_id),
        stat_set=model.stat_set,
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
    )


def team_statistics_to_model(
    entity: TeamStatistics, model: TeamStatisticsModel | None = None
) -> TeamStatisticsModel:
    model = model or TeamStatisticsModel(id=entity.id.value)
    model.match_id = entity.match_id.value
    model.team_id = entity.team_id.value
    model.stat_set = entity.stat_set
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    return model


def _lineup_slot_to_dict(slot: LineupSlot) -> dict:
    return {
        "player_id": str(slot.player_id.value),
        "role": slot.role.value,
        "position": slot.position,
        "shirt_number": slot.shirt_number,
    }


def _lineup_slot_from_dict(payload: dict) -> LineupSlot:
    return LineupSlot(
        player_id=PlayerId(uuid.UUID(payload["player_id"])),
        role=LineupRole(payload["role"]),
        position=payload.get("position"),
        shirt_number=payload.get("shirt_number"),
    )


def lineup_to_domain(model: LineupModel) -> Lineup:
    return Lineup(
        id=LineupId(model.id),
        match_id=MatchId(model.match_id),
        team_id=TeamId(model.team_id),
        formation=model.formation,
        slots=tuple(_lineup_slot_from_dict(s) for s in model.slots),
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
        availability_classification=model.availability_classification,
        information_available_at=model.information_available_at,
        fetched_at=model.fetched_at,
        sync_run_id=model.sync_run_id,
    )


def lineup_to_model(entity: Lineup, model: LineupModel | None = None) -> LineupModel:
    model = model or LineupModel(id=entity.id.value)
    model.match_id = entity.match_id.value
    model.team_id = entity.team_id.value
    model.formation = entity.formation
    model.slots = [_lineup_slot_to_dict(s) for s in entity.slots]
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    model.availability_classification = entity.availability_classification
    model.information_available_at = entity.information_available_at
    model.fetched_at = entity.fetched_at
    model.sync_run_id = entity.sync_run_id
    return model


def injury_to_domain(model: InjuryModel) -> Injury:
    return Injury(
        id=EntityId(model.id),
        player_id=PlayerId(model.player_id),
        reported_at=model.reported_at,
        status=model.status,
        reason=model.reason,
        expected_return=model.expected_return,
        source_ref=None,
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
        availability_classification=model.availability_classification,
        information_available_at=model.information_available_at,
        fetched_at=model.fetched_at,
        sync_run_id=model.sync_run_id,
    )


def injury_to_model(entity: Injury, model: InjuryModel | None = None) -> InjuryModel:
    model = model or InjuryModel(id=entity.id.value)
    model.player_id = entity.player_id.value
    model.reported_at = entity.reported_at
    model.status = entity.status
    model.reason = entity.reason
    model.expected_return = entity.expected_return
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    model.availability_classification = entity.availability_classification
    model.information_available_at = entity.information_available_at
    model.fetched_at = entity.fetched_at
    model.sync_run_id = entity.sync_run_id
    return model


def transfer_to_domain(model: TransferModel) -> Transfer:
    return Transfer(
        id=EntityId(model.id),
        player_id=PlayerId(model.player_id),
        from_team_id=TeamId(model.from_team_id) if model.from_team_id else None,
        to_team_id=TeamId(model.to_team_id) if model.to_team_id else None,
        effective_date=model.effective_date,
        transfer_type=model.transfer_type,
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
        availability_classification=model.availability_classification,
        information_available_at=model.information_available_at,
        fetched_at=model.fetched_at,
        sync_run_id=model.sync_run_id,
    )


def transfer_to_model(entity: Transfer, model: TransferModel | None = None) -> TransferModel:
    model = model or TransferModel(id=entity.id.value)
    model.player_id = entity.player_id.value
    model.from_team_id = entity.from_team_id.value if entity.from_team_id else None
    model.to_team_id = entity.to_team_id.value if entity.to_team_id else None
    model.effective_date = entity.effective_date
    model.transfer_type = entity.transfer_type
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    model.availability_classification = entity.availability_classification
    model.information_available_at = entity.information_available_at
    model.fetched_at = entity.fetched_at
    model.sync_run_id = entity.sync_run_id
    return model


def coaching_staff_to_domain(model: CoachingStaffModel) -> CoachingStaffMember:
    return CoachingStaffMember(
        id=EntityId(model.id),
        team_id=TeamId(model.team_id) if model.team_id else None,
        person_name=model.person_name,
        role=model.role,
        valid_from=model.valid_from,
        valid_to=model.valid_to,
        version=model.version,
        provider_refs=_provider_refs_from_dict(model.provider_ref),
    )


def coaching_staff_to_model(
    entity: CoachingStaffMember, model: CoachingStaffModel | None = None
) -> CoachingStaffModel:
    model = model or CoachingStaffModel(id=entity.id.value)
    model.team_id = entity.team_id.value if entity.team_id else None
    model.person_name = entity.person_name
    model.role = entity.role
    model.valid_from = entity.valid_from
    model.valid_to = entity.valid_to
    model.version = entity.version
    model.provider_ref = _provider_refs_to_dict(entity.provider_refs)
    return model
