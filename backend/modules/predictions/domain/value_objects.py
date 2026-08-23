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

    BINARY = "binary"  # two-outcome markets: moneyline, match winner (draw-less sports), set winner, NRFI/YRFI
    SPREAD = "spread"  # point spread / run line / handicap
    TOTAL = "total"  # over/under total points/runs/sets
    TEAM_TOTAL = "team_total"  # one team's/side's total
    PLAYER_PROP = "player_prop"  # rebounds/assists/strikeouts/etc — regression-shaped
    CORRECT_SCORE = "correct_score"  # exact score / exact set-count distribution
    RACE_TO = "race_to"  # race to N points
    SEGMENT_WINNER = "segment_winner"  # quarter/half/inning/set winner — binary, scoped to a segment
    # Milestone 9.2 Phase 3 — genuinely 3-outcome markets where a draw is possible (football match
    # winner). Deliberately distinct from BINARY: `WeightedLogisticPredictor`'s single sigmoid
    # structurally cannot express a third outcome, so this needs its own predictor strategy
    # (`WeightedOrdinalPredictor`, weighted_scoring.py) rather than relabeling a binary call.
    HOME_DRAW_AWAY = "home_draw_away"


class OutcomeType(str, Enum):
    """The real-world *label space* a market's resolved outcome belongs to (Milestone 9.2 —
    Market Registry & Prediction Domain Normalization). Distinct from `MarketKind`: `MarketKind`
    is which generic predictor *strategy* serves a market (docs/decisions.md); `OutcomeType` is
    what the market's actual answer looks like once resolved against a real result, e.g.
    ``HOME_DRAW_AWAY`` -> ``("HOME_WIN", "DRAW", "AWAY_WIN")``. Introduced specifically to replace
    the generic predictor's ``"positive"``/``"negative"`` output labels with explicit, market-real
    values (see `modules.predictions.domain.market_outcome_registry`) — this enum only names the
    *shape* of a market's allowed values; the concrete `allowed_values` tuple lives per-market in
    `MarketOutcomeSpec`."""

    HOME_DRAW_AWAY = "home_draw_away"  # 3-way: HOME_WIN / DRAW / AWAY_WIN
    HOME_AWAY = "home_away"  # 2-way winner, no draw possible in this sport
    DOUBLE_CHANCE = "double_chance"  # HOME_OR_DRAW / HOME_OR_AWAY / DRAW_OR_AWAY
    BINARY_YES_NO = "binary_yes_no"  # YES / NO (e.g. BTTS)
    OVER_UNDER = "over_under"  # OVER / UNDER against a market-specific line
    HOME_COVER_AWAY_COVER = "home_cover_away_cover"  # spread/handicap/run-line coverage
    CORRECT_SCORE = "correct_score"  # finite scoreline grid + an "OTHER" catch-all
    CORRECT_SET_SCORE = "correct_set_score"  # finite set-count grid (best-of-N sports)
    GOAL_RANGE = "goal_range"  # finite total-goals bucket grid, e.g. "0-1" / "2-3" / "4-5" / "6+"


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
    # A pre-Milestone-9.2 prediction whose stored `value` ("positive"/"negative") could not be
    # deterministically remapped onto its market's real outcome labels — never invented, always
    # marked explicit so it reads as "unknown," not silently reinterpreted as some real label.
    LEGACY_UNRESOLVED = "legacy_unresolved"


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


@dataclass(frozen=True)
class ChallengerEvaluationId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class PredictionCreditId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class PredictionRewardEventId:
    value: UUID

    def __str__(self) -> str:
        return str(self.value)
