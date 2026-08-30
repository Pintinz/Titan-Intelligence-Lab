"""Feature Intelligence Platform entities (docs/feature_catalog.md §1, docs/database_schema.md
§3). Every field in the "Feature Documentation" checklist maps to a field here — a feature
without one of these isn't fully documented and can't reach ACTIVE (see
FeatureRegistrationService)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
    FeatureValidationReportId,
    FeatureValueId,
    QualityFlag,
    ValidationStatus,
)


@dataclass
class FeatureDefinition:
    id: FeatureDefinitionId
    feature_key: FeatureKey
    name: str
    description: str
    sport_code: str  # matches modules.sports.domain.value_objects.SportCode.value
    category: FeatureCategory
    formula: str
    data_type: FeatureDataType
    owner: str
    entity_type: EntityType
    unit: str | None = None
    expected_range: tuple[float, float] | None = None
    update_frequency: str = "unspecified"
    online_ttl_seconds: int = 3600
    source_provider_key: str | None = None  # loose reference to admin.providers.key — see ADR-016
    version: int = 1
    status: FeatureStatus = FeatureStatus.DRAFT
    dependencies: tuple[FeatureKey, ...] = field(default_factory=tuple)
    leakage_reviewed: bool = False
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    deprecated_at: datetime | None = None
    # Milestone 4 provenance foundation — "PRE_MATCH_SAFE" | "POST_MATCH_ONLY" |
    # "POINT_IN_TIME_REQUIRED" | "UNKNOWN_PROVENANCE".
    leakage_classification: str = "UNKNOWN_PROVENANCE"

    def is_consumable(self) -> bool:
        """Only ACTIVE features may be wired into a model's training config
        (docs/feature_catalog.md: "no model may consume an undocumented feature")."""
        return self.status is FeatureStatus.ACTIVE

    def is_market_safe(self) -> bool:
        """Only an explicitly reviewed PRE_MATCH_SAFE classification may back a market's live
        prediction/training feature set (Milestone 4 Rule 8, tightened 2026-08-30 forensic audit
        finding #3) — checked by `FeatureMarketMappingService.map_feature()`/`reconcile_feature()`.

        Previously this only excluded POST_MATCH_ONLY, which meant POINT_IN_TIME_REQUIRED and
        UNKNOWN_PROVENANCE — the default for every feature nobody has explicitly classified —
        both silently passed as safe. UNKNOWN_PROVENANCE is not a statement that a feature is
        safe, it is a statement that nobody has checked; treating it as safe defeats the point of
        having a classification at all. Fails closed now: a feature earns market-safe status by
        being explicitly marked PRE_MATCH_SAFE at registration (see the six windowed calculators,
        the news/manager-change features, and each sport's SINGLE_RECORD_FEATURES block), not by
        default."""
        return self.leakage_classification == "PRE_MATCH_SAFE"


@dataclass
class FeatureDefinitionVersionSnapshot:
    """Append-only history — one row per version transition, so "Version History"
    (docs/feature_catalog.md §1) is queryable without mutating or losing prior definitions."""

    feature_key: FeatureKey
    version: int
    snapshot: FeatureDefinition
    recorded_at: datetime


@dataclass
class FeatureValue:
    """One offline (Postgres) feature observation — the audited historical record. The online
    (Redis) copy is a low-latency read cache of the *same* value, never an independent source
    of truth (docs/database_schema.md §3)."""

    id: FeatureValueId
    feature_key: FeatureKey
    entity_type: EntityType
    entity_id: str  # stringified UUID of the Team/Player/Fixture/... this value is about
    as_of: datetime
    value: float | int | str | bool
    quality_flags: tuple[QualityFlag, ...] = field(default_factory=lambda: (QualityFlag.OK,))


@dataclass
class FeatureLineageEdge:
    """``feature_key`` depends on ``depends_on_feature_key`` — the graph
    FeatureLineageService validates for cycles and unregistered references."""

    feature_key: FeatureKey
    depends_on_feature_key: FeatureKey


@dataclass
class FeatureDriftReport:
    """Data model only — no drift *computation* exists yet; the statistical drift-detection
    algorithm is Milestone 11 (Outcome Learning Engine), wired to this same table."""

    feature_key: FeatureKey
    window: str
    drift_score: float
    method: str
    detected_at: datetime


@dataclass
class FeatureValidationReport:
    """The output of one FeatureQualityEngine.run_validation() call — a persisted, point-in-time
    verdict on a feature's data quality, not a live/recomputed-on-read value. "Last Validation"
    is this report's ``validated_at``; "Validation History" is the list of these
    (docs/feature_catalog.md, Feature Quality Intelligence)."""

    id: FeatureValidationReportId
    feature_key: FeatureKey
    validated_at: datetime
    sample_size: int
    quality_score: float | None
    freshness_score: float | None
    reliability_score: float | None
    completeness_score: float | None
    missing_pct: float | None
    outlier_pct: float | None
    null_pct: float | None
    invalid_pct: float | None
    duplicate_pct: float | None
    coverage_pct: float | None
    status: ValidationStatus
    issues: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class FeatureComputationLog:
    """One recorded computation event for a feature — duration/memory of producing a value.
    Recorded by the (future) ingestion/feature-engineering pipeline, not by this platform
    itself; "Computation Cost", "Average Computation Time", and "Memory Footprint" are all
    derived from a window of these logs."""

    feature_key: FeatureKey
    recorded_at: datetime
    duration_ms: float
    memory_bytes: int | None = None


@dataclass
class FeatureConsumer:
    """Registers that some downstream consumer (a prediction market, model, or report) uses
    this feature — "Consumer Models" (docs/feature_catalog.md §1). Empty until Milestone 6+
    models exist to register themselves; the mechanism is real, the data just isn't yet."""

    feature_key: FeatureKey
    consumer_key: str
    registered_at: datetime


@dataclass
class FeatureUsageRecord:
    """Daily read-count bucket for a feature — same shape as
    ``modules.admin.domain.entities.ProviderUsageRecord``, deliberately: it's the same
    "count events into calendar-day buckets" pattern applied to feature reads instead of
    provider requests."""

    feature_key: FeatureKey
    window_key: str  # "2026-07-25"
    read_count: int = 0
