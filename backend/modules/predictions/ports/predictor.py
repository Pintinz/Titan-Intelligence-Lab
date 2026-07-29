"""Predictor port — the only place a probability/value may originate (Milestone 9 spec:
"Predictions must never originate from an LLM... Predictions originate only from engineered
features, historical data, feature store, knowledge graph, validated statistics, approved
feature calculators.").

A `PredictorPort` implementation is written against a `MarketKind` (the small, finite
computational-strategy taxonomy in modules.predictions.domain.value_objects), never against a
single named market — dozens of `MarketDefinition` rows across every sport share the same
handful of real predictor classes (docs/decisions.md — data-driven market registry). No
provider/framework/model-vendor import belongs here or in any implementation of it
(docs/architecture.md §2 independence rules).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from modules.predictions.domain.value_objects import MarketKind


@dataclass(frozen=True)
class PredictorOutput:
    """What every `PredictorPort.predict()` call returns, regardless of `MarketKind` — the raw,
    uncalibrated signal `ProbabilityCalibrationEngine` (Part 4) turns into a published
    probability, plus per-feature signed contributions the Explainability Engine ranks into
    top-positive/top-negative features without re-deriving them."""

    raw_score: float  # uncalibrated score, e.g. a logistic pre-sigmoid value or weighted sum
    probability: float  # this predictor's own [0, 1] estimate, pre-calibration
    value: str  # the predicted label/outcome, stringified (e.g. "home_win", "over")
    feature_contributions: dict[str, float] = field(default_factory=dict)


class PredictorPort(Protocol):
    market_kind: MarketKind

    async def predict(
        self, market_kind: MarketKind, features: dict[str, float], mapping_weights: dict[str, float]
    ) -> PredictorOutput:
        """``features`` is the market's resolved feature snapshot (already filtered to its
        registered Feature-to-Market mapping — no predictor may see a feature outside that
        mapping). ``mapping_weights`` are the corresponding `FeatureMarketMapping.weight` values,
        keyed the same as ``features``."""
        ...
