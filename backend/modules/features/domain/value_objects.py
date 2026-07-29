"""Value objects for the Feature Intelligence Platform (docs/feature_catalog.md).

No framework imports — same domain-purity rule as every other module
(docs/architecture.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class FeatureCategory(str, Enum):
    """docs/feature_catalog.md §3 — the closed set every registered feature belongs to."""

    PROVIDER = "provider"
    HISTORICAL = "historical"
    LIVE = "live"
    ENGINEERED = "engineered"
    CONTEXTUAL = "contextual"
    TACTICAL = "tactical"
    TEAM = "team"
    PLAYER = "player"
    VENUE = "venue"
    COMPETITION = "competition"
    ENVIRONMENTAL = "environmental"
    PSYCHOLOGICAL = "psychological"
    AI_EXTRACTED = "ai_extracted"
    COMMUNITY_INTELLIGENCE = "community_intelligence"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    LEARNED = "learned"
    META = "meta"


class FeatureDataType(str, Enum):
    FLOAT = "float"
    INT = "int"
    BOOL = "bool"
    STRING = "string"
    CATEGORICAL = "categorical"


class EntityType(str, Enum):
    """What a feature value is *about* — matches the sports domain's core aggregates."""

    TEAM = "team"
    PLAYER = "player"
    FIXTURE = "fixture"
    COMPETITION = "competition"
    SEASON = "season"
    VENUE = "venue"


class FeatureStatus(str, Enum):
    """docs/feature_catalog.md §6 lifecycle: registration -> review -> active -> deprecated ->
    removed. No model may consume a feature that isn't ACTIVE (enforced by
    FeatureRegistrationService, not just convention)."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


class QualityFlag(str, Enum):
    """Attached to an offline value at write time — docs/feature_catalog.md §7 "Data Quality
    Validation"."""

    OK = "ok"
    OUT_OF_RANGE = "out_of_range"
    TYPE_MISMATCH = "type_mismatch"
    STALE = "stale"
    MISSING_IMPUTED = "missing_imputed"


@dataclass(frozen=True)
class FeatureKey:
    """Stable dotted identifier, e.g. ``football.team.form_index_last5``
    (docs/feature_catalog.md §1). Immutable once registered — a changed formula is a new
    version of the same key, never a new key."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or " " in self.value:
            raise ValueError(f"invalid feature key: {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class FeatureDefinitionId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class FeatureValueId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class FeatureValidationReportId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


class ValidationStatus(str, Enum):
    """Overall verdict of a FeatureValidationReport."""

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
