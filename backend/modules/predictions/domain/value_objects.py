"""Value objects for the Prediction Intelligence Platform (Milestone 9,
docs/prediction_markets.md, docs/database_schema.md §4).

No framework imports — same domain-purity rule as every other module
(docs/architecture.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class MarketKind(str, Enum):
    """The small, finite set of reusable computational *strategies* a market needs. Markets
    themselves are data (`MarketDefinition` rows, one per named market across every sport);
    kinds are the shapes `PredictorPort` implementations are written against, so dozens of named
    markets per sport are served by a handful of real predictor classes rather than one bespoke
    class per market (docs/decisions.md — data-driven market registry)."""

    BINARY = "binary"  # two-outcome markets: moneyline, match winner, set winner, NRFI/YRFI
    SPREAD = "spread"  # point spread / run line / handicap
    TOTAL = "total"  # over/under total points/runs/sets
    TEAM_TOTAL = "team_total"  # one team's/side's total
    PLAYER_PROP = "player_prop"  # rebounds/assists/strikeouts/etc — regression-shaped
    CORRECT_SCORE = "correct_score"  # exact score / exact set-count distribution
    RACE_TO = "race_to"  # race to N points
    SEGMENT_WINNER = "segment_winner"  # quarter/half/inning/set winner — binary, scoped to a segment


class MarketStatus(str, Enum):
    """docs lifecycle: Draft -> Review -> Approved -> Production -> Deprecated -> Archived ->
    Removed. Only PRODUCTION markets may participate in prediction generation."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    REMOVED = "removed"


class ModelStatus(str, Enum):
    """Champion/Challenger lifecycle. Exactly one model per market may be CHAMPION at a time —
    enforced by `ModelRegistryService`, not just convention."""

    CANDIDATE = "candidate"
    CHALLENGER = "challenger"
    CHAMPION = "champion"
    RETIRED = "retired"


class PredictionStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    VOIDED = "voided"


class TargetType(str, Enum):
    CLASSIFICATION = "classification"
    REGRESSION = "regression"


class AuditAction(str, Enum):
    """Every named Admin Action (Part 6) plus the baseline lifecycle event every prediction
    generates automatically."""

    GENERATED = "generated"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ROLLED_BACK = "rolled_back"
    RECOMPUTED = "recomputed"
    REPROCESSED = "reprocessed"
    RETRIED = "retried"
    ARCHIVED = "archived"
    EXPORTED = "exported"


@dataclass(frozen=True)
class MarketId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class FeatureMarketMappingId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ModelId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class PredictionId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class PredictionOutcomeId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ModelEvaluationId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class ExperimentId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class PredictionAuditId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)
