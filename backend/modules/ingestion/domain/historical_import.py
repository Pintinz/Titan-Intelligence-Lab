"""POST-M24 Phase 4 — provider-agnostic historical import contract.

A `HistoricalFixtureRecord` is the canonical shape any historical source (Kaggle CSV, a future
Retrosheet/Football-Reference importer, an admin-uploaded file) must produce. It deliberately
mirrors `ProviderFixtureRecord`/`ProviderTeamRecord` (`modules.sports.ports.provider_gateway`)
in spirit but stays a pre-resolution DTO: team and competition identity here are raw strings from
the source file, not yet-verified `ProviderRef`s, because a historical CSV has no notion of
TitanIQ's (or any live provider's) internal ids. `HistoricalImportService` is what turns these into
real `ProviderRef`s and hands off to the *existing* `EntityReconciliationService` — this module
holds no reconciliation logic of its own (see that service's own docstring for why: "one matching
engine", not a second one).

Every write this produces is tagged `SyncTrigger.BACKFILL` (see `HistoricalImportService`) and
never becomes `VERIFIED_PRE_MATCH` — historical rows carry a match *date*, never a real
information-availability time, which is exactly the distinction `classify_availability`
(`modules.ingestion.application.provenance`) already enforces for every other entity kind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from modules.sports.domain.value_objects import SportCode


class ImportMode(str, Enum):
    """`IMPORT` is never the default anywhere this enum is consumed — every entry point requires
    an explicit, affirmative choice of `IMPORT` to write anything."""

    DRY_RUN = "dry_run"  # parse + resolve entirely in memory; zero repository calls of any kind
    VALIDATE = "validate"  # DRY_RUN plus a read-only check against real DB state (team/competition matches)
    IMPORT = "import"  # DRY_RUN/VALIDATE's exact resolution, then real writes via EntityReconciliationService


@dataclass(frozen=True)
class HistoricalOddsQuote:
    """One real, provider-reported historical sportsbook quote attached to a
    `HistoricalFixtureRecord` — same canonical shape as `modules.sports.domain.entities.MarketLine`/
    `modules.sports.ports.provider_gateway.ProviderMarketLineRecord` (bookmaker/market_type/
    selection/line/price), but pre-resolution: identified by the record's own `source_record_id`,
    not yet a real `FixtureId`. `HistoricalImportService` writes these into `MarketLine` using the
    exact `FixtureId` its own fixture reconciliation just resolved for the same record — never a
    second, independent fixture match, and never fabricated when a source column is blank."""

    bookmaker: str
    market_type: str  # MarketLineType's string value, kept plain here for the same reason
    # ProviderMarketLineRecord does — no domain-enum dependency at this pre-resolution layer
    selection: str  # MarketSelection's string value ("HOME"/"AWAY"/"DRAW"/"OVER"/"UNDER")
    line: float | None
    price: float


@dataclass(frozen=True)
class HistoricalTeamStatistics:
    """One side's real match-level statistics for a `HistoricalFixtureRecord`, when the source
    reports them — keyed by the same stat_set vocabulary the existing rolling-form-differential
    calculators already read (`_ADDITIONAL_FOOTBALL_STAT_KEYS` in
    `windowed_feature_engineering_service.py`: shots_on_target, shots_total, corners, fouls,
    cards_yellow). A key the source doesn't report is simply absent from `stat_set` — never
    fabricated, never defaulted to 0."""

    stat_set: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HistoricalFixtureRecord:
    """One historical match, as reported by the source file — pre-resolution: team and
    competition names are the source's own raw strings, not yet matched to any TitanIQ entity."""

    source_key: str  # e.g. "kaggle_international_football_results" — namespaces this source's own ProviderRefs
    source_record_id: str  # stable per-row identity within the source (idempotency key)
    sport: SportCode
    competition_ref: str  # the source's own competition identifier (code, slug, or name — whatever it has)
    competition_name: str
    season_label: str
    scheduled_at: datetime
    home_team_name: str
    away_team_name: str
    home_score: int | None = None
    away_score: int | None = None
    neutral_venue: bool = False
    # Real historical bookmaker quotes for this match, when the source genuinely reports them —
    # empty for every source that doesn't (every existing call site's default, unchanged).
    odds: tuple[HistoricalOddsQuote, ...] = ()
    # Real per-side match statistics, when the source genuinely reports them — `None` (the
    # default) for every existing call site, unchanged.
    home_statistics: HistoricalTeamStatistics | None = None
    away_statistics: HistoricalTeamStatistics | None = None


class QuarantineReason(str, Enum):
    AMBIGUOUS_TEAM = "ambiguous_team"  # 2+ existing teams share the same normalized name
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_DATE = "invalid_date"
    UNPARSEABLE_ROW = "unparseable_row"


@dataclass(frozen=True)
class QuarantinedRecord:
    source_record_id: str
    reason: QuarantineReason
    detail: str


@dataclass
class HistoricalImportReport:
    """Everything Phase 4 Step 25 requires a real import run to be able to answer: total seen,
    what happened to each, and what was dropped and why — no silent truncation."""

    mode: ImportMode
    source_key: str
    sport: SportCode
    total_records: int = 0
    rejected_rows: int = 0  # failed to parse at the source-reader level, never became a candidate record
    fixtures_created: int = 0
    fixtures_updated: int = 0  # matched an existing fixture (same source id, or teams+date convergence)
    teams_created: int = 0
    teams_matched: int = 0  # resolved to an existing team by exact normalized name
    odds_quotes_recorded: int = 0  # real MarketLine rows written — one per real, non-blank source column
    statistics_recorded: int = 0  # real TeamStatistics rows written — one per side with real stat_set data
    competitions_touched: set[str] = field(default_factory=set)
    quarantined: list[QuarantinedRecord] = field(default_factory=list)

    @property
    def quarantined_count(self) -> int:
        return len(self.quarantined)
