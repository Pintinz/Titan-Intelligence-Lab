"""Confidence Engine (Milestone 9 Part 4): turns the nine named confidence factors into a single
validated `ConfidenceBreakdown`.

Three factors are naturally per-feature and get real aggregation here — `feature_quality` and
`feature_freshness` are averaged, `data_completeness` is the presence ratio, all computed across
the market's resolved feature snapshot. The remaining six are pass-through factors this engine
clamps into [0, 1] rather than re-derives, because each is already the output of an existing
service this milestone composes: `historical_accuracy` and `model_reliability` from
`ModelEvaluation`/`PredictionOutcome` history (Model Registry's territory), `knowledge_graph_completeness`
from Milestone 7's Knowledge Graph, `news_reliability`/`community_reliability` from Milestone 8's
`SourceReliabilityService`, and `prediction_stability` from recent `Prediction` history for the
same subject+market. Gathering those six is the Prediction Context Builder's job (Milestone 9
task #132) — this engine only aggregates and validates what it's handed.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.predictions.domain.entities import ConfidenceBreakdown


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


@dataclass(frozen=True)
class FeatureConfidenceInput:
    """Per-feature confidence signal for one entry in a market's resolved feature snapshot."""

    feature_key: str
    quality_score: float  # 0-1, from FeatureQualityEngine (Milestone 4)
    freshness_score: float  # 0-1, 1.0 = computed just now, decaying with staleness
    is_present: bool  # False if this feature was missing from the resolved snapshot


@dataclass(frozen=True)
class ConfidenceInputs:
    features: tuple[FeatureConfidenceInput, ...]
    historical_accuracy: float
    knowledge_graph_completeness: float
    news_reliability: float
    community_reliability: float
    model_reliability: float
    prediction_stability: float


@dataclass
class ConfidenceEngine:
    def compute(self, inputs: ConfidenceInputs) -> ConfidenceBreakdown:
        if inputs.features:
            feature_quality = sum(f.quality_score for f in inputs.features) / len(inputs.features)
            feature_freshness = sum(f.freshness_score for f in inputs.features) / len(inputs.features)
            data_completeness = sum(1 for f in inputs.features if f.is_present) / len(inputs.features)
        else:
            # No features resolved at all is the worst case, not an unknown one — zero, not a
            # default midpoint, so a market with nothing behind it can never look confident.
            feature_quality = 0.0
            feature_freshness = 0.0
            data_completeness = 0.0

        return ConfidenceBreakdown(
            feature_quality=_clamp(feature_quality),
            feature_freshness=_clamp(feature_freshness),
            historical_accuracy=_clamp(inputs.historical_accuracy),
            knowledge_graph_completeness=_clamp(inputs.knowledge_graph_completeness),
            news_reliability=_clamp(inputs.news_reliability),
            community_reliability=_clamp(inputs.community_reliability),
            data_completeness=_clamp(data_completeness),
            model_reliability=_clamp(inputs.model_reliability),
            prediction_stability=_clamp(inputs.prediction_stability),
        )
