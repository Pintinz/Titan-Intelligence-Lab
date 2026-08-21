"""SQLAlchemy 2.x ORM models for the `sports` schema (docs/database_schema.md §2).

Uses SQLAlchemy's dialect-generic ``Uuid``/``JSON`` types rather than the Postgres-specific
dialect types, so the same model definitions run against Postgres in every real environment
and against SQLite in unit tests (see backend/tests/unit/modules/sports/conftest.py) — this is
a testing convenience, not a production-vs-test schema divergence: SQLAlchemy compiles
``Uuid``/``JSON`` to Postgres's native UUID/JSONB on a Postgres engine.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, MetaData, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="sports")


class Base(DeclarativeBase):
    metadata = metadata


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VersionedMixin:
    """Optimistic version counter + opaque provider attribution, bumped by the ingestion
    reconciler on every reconciled change (docs/roadmap.md Milestone 5 — "every entity must
    support versioning ... source tracking ... provider tracking"). Applied to every entity
    Milestone 5 actively ingests; remaining entities get it when their ingestion is wired
    (see the Entity Expansion Matrix in database_schema.md)."""

    version: Mapped[int] = mapped_column(Integer, default=1)
    provider_ref: Mapped[dict] = mapped_column(JSON, default=dict)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


class SportModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "sports"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="active")


class CountryModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "countries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))


class VenueModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "venues"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(120))
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surface: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")


class CompetitionModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "competitions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    sport_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sports.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(32))
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class SeasonModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "seasons"

    id: Mapped[uuid.UUID] = _uuid_pk()
    competition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("competitions.id"), index=True)
    label: Mapped[str] = mapped_column(String(64))
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="upcoming")


class TeamModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = _uuid_pk()
    sport_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sports.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str] = mapped_column(String(32))
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    venue_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("venues.id"), nullable=True, index=True)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class PlayerModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "players"

    id: Mapped[uuid.UUID] = _uuid_pk()
    sport_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sports.id"), index=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    position: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CoachingStaffModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "coaching_staff"

    id: Mapped[uuid.UUID] = _uuid_pk()
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    person_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(64))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class OfficialModel(TimestampMixin, Base):
    __tablename__ = "officials"

    id: Mapped[uuid.UUID] = _uuid_pk()
    sport_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sports.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(64))


class FixtureModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "fixtures"

    id: Mapped[uuid.UUID] = _uuid_pk()
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id"), index=True)
    home_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    venue_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("venues.id"), nullable=True, index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", index=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Sport-specific period-by-period score breakdown (quarters for basketball, innings for
    # baseball) — {"kind": "quarter"|"inning", "home": [...], "away": [...]}. None when the
    # sport's provider doesn't report period scores (football) or hasn't been synced yet.
    period_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class MatchModel(TimestampMixin, Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = _uuid_pk()
    fixture_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fixtures.id"), unique=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_state: Mapped[dict] = mapped_column(JSON, default=dict)


class MatchEventModel(TimestampMixin, Base):
    __tablename__ = "match_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), index=True)
    period: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    player_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("players.id"), nullable=True, index=True)


class TeamStatisticsModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "team_statistics"
    __table_args__ = (UniqueConstraint("match_id", "team_id", name="uq_team_statistics_match_team"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    stat_set: Mapped[dict] = mapped_column(JSON, default=dict)


class PlayerStatisticsModel(TimestampMixin, Base):
    __tablename__ = "player_statistics"

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), index=True)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), index=True)
    stat_set: Mapped[dict] = mapped_column(JSON, default=dict)


class MarketLineModel(TimestampMixin, Base):
    """POST-M24 Phase 6 — real, provider-normalized sportsbook quotes. Append-only (one row per
    observed quote, never overwritten in place — see `MarketLineRepositoryPort`'s docstring) so
    a line's real movement over time is preserved rather than lost to an upsert."""

    __tablename__ = "market_lines"

    id: Mapped[uuid.UUID] = _uuid_pk()
    fixture_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fixtures.id"), index=True)
    sport_code: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    bookmaker: Mapped[str] = mapped_column(String(128))
    market_type: Mapped[str] = mapped_column(String(32), index=True)
    selection: Mapped[str] = mapped_column(String(16))
    line: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    team_side: Mapped[str | None] = mapped_column(String(8), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class StandingModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "standings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id"), index=True)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rank: Mapped[int] = mapped_column(Integer)
    points: Mapped[float] = mapped_column(Float)
    record: Mapped[dict] = mapped_column(JSON, default=dict)


class LineupModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "lineups"
    __table_args__ = (UniqueConstraint("match_id", "team_id", name="uq_lineup_match_team"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    formation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    slots: Mapped[list] = mapped_column(JSON, default=list)
    # Milestone 4 provenance foundation (docs/milestone4_verification_report.md) — see
    # InjuryModel's own comment below for the shared semantics of this pair of columns.
    availability_classification: Mapped[str] = mapped_column(String(32), default="UNKNOWN_AVAILABILITY_TIME")
    information_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Milestone 5 (Verified Pre-Match Data Availability) — see
    # modules.ingestion.application.provenance's module docstring for fetched_at vs
    # information_available_at semantics, and Lineup/Injury/Transfer's domain entity comments.
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class InjuryModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "injuries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), index=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expected_return: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Milestone 4 provenance foundation. `reported_at` above is NOT a genuine report/publication
    # timestamp — confirmed by reading `ApiFootballAdapter.fetch_injuries`: it's populated from
    # the API-Football `/injuries` response's `fixture.date`, i.e. the KICKOFF of the fixture the
    # player is unavailable for, not when the injury became known. That endpoint reports no
    # report/publication timestamp at all. `availability_classification` is the honest
    # "VERIFIED_PRE_MATCH | VERIFIED_POST_MATCH | UNKNOWN_AVAILABILITY_TIME" verdict (same 3-state
    # concept as KNOWN_BEFORE_EVENT/UNKNOWN/KNOWN_AFTER_EVENT on the other structured-intelligence
    # tables below); `information_available_at`, when set, is a genuine verified availability
    # timestamp distinct from `reported_at` — never derived from `reported_at` itself. Defaults to
    # UNKNOWN_AVAILABILITY_TIME; only an explicit verification pass may promote a row to
    # VERIFIED_PRE_MATCH. Never auto-classified as pre-match — see EntityKind/leakage-prevention
    # tests in tests/unit/modules/sports/test_availability_classification.py.
    availability_classification: Mapped[str] = mapped_column(String(32), default="UNKNOWN_AVAILABILITY_TIME")
    information_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SuspensionModel(TimestampMixin, Base):
    __tablename__ = "suspensions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), index=True)
    reason: Mapped[str] = mapped_column(String(255))
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    availability_classification: Mapped[str] = mapped_column(String(32), default="UNKNOWN_AVAILABILITY_TIME")
    information_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TransferModel(TimestampMixin, VersionedMixin, Base):
    __tablename__ = "transfers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), index=True)
    from_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    to_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    transfer_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    availability_classification: Mapped[str] = mapped_column(String(32), default="UNKNOWN_AVAILABILITY_TIME")
    information_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RankingModel(TimestampMixin, Base):
    __tablename__ = "rankings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    sport_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sports.id"), index=True)
    scope: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    system: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
