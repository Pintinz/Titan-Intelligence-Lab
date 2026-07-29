"""SHAP Explainability domain (Milestone 9.1). Layered ON TOP of the existing Explainability
Engine (Milestone 9) — `PredictorOutput.feature_contributions` (a lightweight value*weight
approximation) keeps serving `ExplanationBundle.top_positive_features`/`top_negative_features`
unchanged; these are the real, additional Shapley-value-based artifacts SHAP integration adds
when the underlying predictor is a fitted `PredictionModelPort` (never for the weighted
predictors, which have no "model" for SHAP to introspect).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ShapExplanation:
    """Global/local SHAP importance for one prediction. ``decision_path`` is a plain-language
    reading of the top contributing features by |shap value| for ensembles where no single literal
    tree-traversal path exists (Milestone 9.1 spec's "Decision Paths" — honestly reinterpreted for
    ensemble models, documented rather than silently approximated as a real single-tree path that
    doesn't exist for a forest/boosting ensemble)."""

    local_shap_values: dict = field(default_factory=dict)  # feature_key -> this instance's SHAP value
    global_importance: dict = field(default_factory=dict)  # feature_key -> mean |SHAP value| across background
    base_value: float = 0.0
    interaction_values: dict = field(default_factory=dict)  # {(feature_a, feature_b): value} — tree models only
    decision_path: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class CounterfactualExplanation:
    """"What would have to change for the prediction to flip?" — a real, bounded greedy search
    over the top SHAP-ranked features (not a fabricated static answer): perturb the
    highest-|shap-value| feature(s) by a step proportional to the background data's own spread
    until the model's predicted class changes, or the search budget is exhausted."""

    changed_features: dict  # feature_key -> (original_value, counterfactual_value)
    original_value: str
    counterfactual_value: str | None  # None if no flip was found within the search budget
    found: bool


@dataclass(frozen=True)
class DependencePoint:
    feature_value: float
    shap_value: float


@dataclass(frozen=True)
class DependencePlotData:
    feature_key: str
    points: tuple = field(default_factory=tuple)  # tuple[DependencePoint, ...]
