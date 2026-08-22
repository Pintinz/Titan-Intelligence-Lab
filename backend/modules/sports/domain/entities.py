"""Core sport-agnostic domain entities (docs/database_schema.md §2).

Sport-specific variation lives in each entity's ``stat_set``/``payload`` dict, validated
against the owning sport plugin's StatisticSchema/MatchEventTypeCatalog at the application
layer — these classes hold no framework imports and no persistence concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.sports.domain.contracts.competition import SeasonLifecycleRules
from modules.sports.domain.contracts.fixture import is_valid_fixture_transition
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
    MarketLineId,
    MarketLineType,
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


@dataclass
class Sport:
    id: SportId
    code: SportCode
    name: str
    status: str = "active"
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class Country:
    """Reference/lookup entity — docs/roadmap.md Milestone 5 Entity Expansion Matrix.

    Existing string ``country`` fields on Venue/Team/Competition are left as-is this
    milestone (no breaking migration); linking them to this table via FK is a follow-up
    normalization task, not part of Milestone 5's scope (see decisions.md)."""

    id: CountryId
    code: str  # ISO 3166-1 alpha-2, e.g. "GB"
    name: str
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class Venue:
    id: VenueId
    name: str
    city: str
    country: str
    capacity: int | None = None
    surface: str | None = None
    timezone: str = "UTC"
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class Competition:
    id: CompetitionId
    sport_id: SportId
    name: str
    type: CompetitionType
    country: str | None
    tier: int | None = None
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)
    logo_url: str | None = None


@dataclass
class Season:
    id: SeasonId
    competition_id: CompetitionId
    label: str
    date_range: DateRange
    status: SeasonStatus = SeasonStatus.UPCOMING
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)

    def transition_to(self, target: SeasonStatus) -> "Season":
        if target not in SeasonLifecycleRules[self.status]:
            raise ValueError(f"cannot transition season from {self.status} to {target}")
        return Season(
            id=self.id,
            competition_id=self.competition_id,
            label=self.label,
            date_range=self.date_range,
            status=target,
            version=self.version,
            provider_refs=self.provider_refs,
        )


@dataclass
class Team:
    id: TeamId
    sport_id: SportId
    name: str
    short_name: str
    country: str | None
    venue_id: VenueId | None = None
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)
    logo_url: str | None = None


@dataclass
class Player:
    id: PlayerId
    sport_id: SportId
    name: str
    date_of_birth: datetime | None
    position: str | None
    team_id: TeamId | None = None
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class CoachingStaffMember:
    """Time-aware: ``valid_to is None`` means still in the role. A departure never overwrites
    the row in place — reconciliation closes it (sets ``valid_to``) and creates a new one for a
    successor, so team history is never lost (docs/roadmap.md Milestone 5 Entity Expansion
    Matrix note: gets VersionedMixin/provider tracking once its ingestion is wired)."""

    id: EntityId
    team_id: TeamId | None
    person_name: str
    role: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class Official:
    id: EntityId
    sport_id: SportId
    name: str
    role: str


@dataclass
class Fixture:
    id: FixtureId
    season_id: SeasonId
    home_team_id: TeamId
    away_team_id: TeamId
    venue_id: VenueId | None
    scheduled_at: datetime
    status: FixtureStatus = FixtureStatus.SCHEDULED
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)
    home_score: int | None = None
    away_score: int | None = None
    period_scores: dict | None = None
    # Real-world provenance, not a duplicate of `provider_ref`'s per-mutation optimistic-lock
    # bookkeeping: the last time this fixture was actually confirmed against a live provider
    # sync (EntityReconciliationService.reconcile_fixture), so a caller can tell "current" from
    # "hasn't been re-verified in a while" without inferring it from `updated_at` (which also
    # bumps for unrelated administrative edits). `source_ids`/cross-provider identity already
    # live in ProviderRefIndexModel (modules.ingestion) — not duplicated here.
    last_verified_at: datetime | None = None

    def transition_to(self, target: FixtureStatus) -> "Fixture":
        if not is_valid_fixture_transition(self.status, target):
            raise ValueError(f"cannot transition fixture from {self.status} to {target}")
        return Fixture(
            id=self.id,
            season_id=self.season_id,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            venue_id=self.venue_id,
            scheduled_at=self.scheduled_at,
            status=target,
            version=self.version,
            provider_refs=self.provider_refs,
            home_score=self.home_score,
            away_score=self.away_score,
            period_scores=self.period_scores,
            last_verified_at=self.last_verified_at,
        )


@dataclass
class Match:
    id: MatchId
    fixture_id: FixtureId
    started_at: datetime | None
    ended_at: datetime | None
    final_state: dict = field(default_factory=dict)


@dataclass
class MatchEvent:
    id: EntityId
    match_id: MatchId
    period: int
    event_type: str
    payload: dict = field(default_factory=dict)
    team_id: TeamId | None = None
    player_id: PlayerId | None = None


@dataclass
class TeamStatistics:
    id: EntityId
    match_id: MatchId
    team_id: TeamId
    stat_set: dict = field(default_factory=dict)
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class PlayerStatistics:
    id: EntityId
    match_id: MatchId
    player_id: PlayerId
    stat_set: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MarketLine:
    """POST-M24 Phase 6 — one real, provider-independent sportsbook quote for one fixture.

    Canonical, not provider-specific: a bookmaker's raw bet name/shape is normalized into
    `market_type`/`selection`/`line`/`price` at the adapter boundary (see `provider_gateway
    .ProviderMarketLineRecord`) before it ever reaches this entity — no `ApiBasketballOdds` or
    `ApiBaseballOdds` subtype exists, per the phase's explicit "provider-specific data belongs
    behind adapters" rule.

    `line` is `None` for `MarketLineType.MONEYLINE` (price-only, no point/run adjustment) and a
    real number for SPREAD/TOTAL/TEAM_TOTAL. `observed_at` is the bookmaker's own quote
    timestamp when the provider genuinely supplies one; `fetched_at` is always TitanIQ's own
    retrieval time and is never substituted for `observed_at` when the provider's timestamp is
    missing — a `None` `observed_at` means "temporal provenance unknown," not "just now."
    """

    id: MarketLineId
    fixture_id: FixtureId
    sport_code: str
    provider: str
    bookmaker: str
    market_type: MarketLineType
    selection: str
    line: float | None
    price: float
    fetched_at: datetime
    observed_at: datetime | None = None
    # Which side this line is quoted for — meaningful (and required to resolve) only for
    # TEAM_TOTAL, whose real shape is two independent OVER/UNDER markets, one per team; `None`
    # for MONEYLINE/SPREAD/TOTAL, whose `selection` alone is already unambiguous.
    team_side: str | None = None
    version: int = 1


@dataclass
class Standing:
    id: EntityId
    season_id: SeasonId
    team_id: TeamId
    snapshot_at: datetime
    rank: int
    points: float
    record: dict = field(default_factory=dict)
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)


@dataclass
class LineupSlot:
    """One player's inclusion in a Lineup — not a standalone aggregate, always embedded in a
    Lineup's starters/substitutes tuples."""

    player_id: PlayerId
    role: LineupRole
    position: str | None = None
    shirt_number: int | None = None


@dataclass
class Lineup:
    """A team's full lineup for one match — docs/roadmap.md Milestone 5 Entity Expansion
    Matrix. One Lineup per (match, team) pair."""

    id: LineupId
    match_id: MatchId
    team_id: TeamId
    formation: str | None = None
    slots: tuple[LineupSlot, ...] = field(default_factory=tuple)
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)
    availability_classification: str = "UNKNOWN_AVAILABILITY_TIME"
    information_available_at: datetime | None = None
    # Milestone 5 (Verified Pre-Match Data Availability) — when the provider response was
    # retrieved, recorded unconditionally on every successful fetch regardless of provenance
    # (distinct from `information_available_at`, populated only when the fetch also satisfies
    # the pre-match provenance rule — see modules.ingestion.application.provenance).
    fetched_at: datetime | None = None
    # Traceability to the exact SyncRun that produced this record (Milestone 5 §11 — "why does
    # TitanIQ believe this was available before kickoff must be reconstructable from stored
    # provenance"). Stored as a plain str (SyncRunId.value) to avoid a domain-layer dependency
    # from modules.sports on modules.ingestion's value objects.
    sync_run_id: str | None = None

    def starters(self) -> tuple[LineupSlot, ...]:
        return tuple(s for s in self.slots if s.role is LineupRole.STARTER)

    def substitutes(self) -> tuple[LineupSlot, ...]:
        return tuple(s for s in self.slots if s.role is LineupRole.SUBSTITUTE)


@dataclass
class Injury:
    """``status`` and ``reason`` carry the provider's own raw text (e.g. API-Football's
    ``player.type``/``player.reason`` — "Missing Fixture"/"Hamstring") rather than a normalized
    enum with no real backing states; ``expected_return`` stays ``None`` unless a provider
    genuinely reports one — never inferred."""

    id: EntityId
    player_id: PlayerId
    reported_at: datetime
    status: str
    reason: str | None = None
    expected_return: datetime | None = None
    source_ref: ProviderRef | None = None
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)
    # Milestone 4 provenance foundation — see InjuryModel's docstring (persistence/models.py)
    # for why `reported_at` above must never be treated as proof this was known pre-kickoff.
    # "VERIFIED_PRE_MATCH" | "VERIFIED_POST_MATCH" | "UNKNOWN_AVAILABILITY_TIME"; defaults
    # honestly to unknown, never auto-classified as pre-match.
    availability_classification: str = "UNKNOWN_AVAILABILITY_TIME"
    information_available_at: datetime | None = None
    fetched_at: datetime | None = None
    sync_run_id: str | None = None


@dataclass
class Suspension:
    id: EntityId
    player_id: PlayerId
    reason: str
    start_date: datetime
    end_date: datetime | None = None
    availability_classification: str = "UNKNOWN_AVAILABILITY_TIME"
    information_available_at: datetime | None = None
    fetched_at: datetime | None = None
    sync_run_id: str | None = None


@dataclass
class Transfer:
    """A confirmed transfer record only — ``transfer_type`` is the provider's raw fee/type text
    (e.g. "Loan", "Free", "€25.5M"); there is no rumour/negotiating/medical staging here
    because no connected provider reports pre-confirmation transfer stages (see
    modules/intelligence's NewsEventType.TRANSFER for that signal instead)."""

    id: EntityId
    player_id: PlayerId
    from_team_id: TeamId | None
    to_team_id: TeamId | None
    effective_date: datetime
    transfer_type: str | None = None
    version: int = 1
    provider_refs: tuple[ProviderRef, ...] = field(default_factory=tuple)
    availability_classification: str = "UNKNOWN_AVAILABILITY_TIME"
    information_available_at: datetime | None = None
    fetched_at: datetime | None = None
    sync_run_id: str | None = None


@dataclass
class Ranking:
    id: EntityId
    sport_id: SportId
    scope: str  # "team" | "player"
    entity_id: EntityId
    system: str
    value: float
    as_of: datetime
