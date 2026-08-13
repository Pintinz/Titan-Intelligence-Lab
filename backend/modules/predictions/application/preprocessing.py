"""Training Platform preprocessing (Milestone 9.1): missing-value imputation, outlier detection,
and feature selection over `TrainingSample`s — pure functions, no framework dependency, operating
purely on the domain-level sample/feature representation every `PredictionModelPort` adapter
already consumes.

Scaling/encoding are handled inside `SklearnAdapter` itself (a `sklearn.pipeline.Pipeline` with a
`StandardScaler` first stage for scale-sensitive algorithms) rather than here, since a fitted
scaler must travel with the model to inference time — see that module's docstring. What belongs
here is preprocessing that produces a *new dataset* (imputed values, a trimmed sample list, a
narrowed feature set), independent of which algorithm eventually trains on it.
"""

from __future__ import annotations

import statistics as pystats

from modules.predictions.ports.ml_model import TrainingSample


def impute_missing(samples: list[TrainingSample], feature_order: list[str], strategy: str = "zero") -> list[TrainingSample]:
    """Returns new `TrainingSample`s with every ``feature_order`` key present — ``"zero"`` fills
    0.0, ``"mean"`` fills the feature's own mean across ``samples`` that do have it (falling back
    to 0.0 if no sample has it at all)."""
    if strategy not in {"zero", "mean"}:
        raise ValueError(f"unsupported imputation strategy '{strategy}'")

    fill_values = {key: 0.0 for key in feature_order}
    if strategy == "mean":
        for key in feature_order:
            values = [s.features[key] for s in samples if key in s.features]
            if values:
                fill_values[key] = pystats.fmean(values)

    imputed = []
    for sample in samples:
        features = {key: sample.features.get(key, fill_values[key]) for key in feature_order}
        # Milestone 18: reference_time must survive this reconstruction — dataset_splitter.split()
        # (called later in TrainingPipelineService.train()) fails closed without it for every
        # temporal strategy.
        imputed.append(TrainingSample(features=features, label=sample.label, reference_time=sample.reference_time))
    return imputed


def detect_outliers(samples: list[TrainingSample], feature_order: list[str], z_threshold: float = 3.0) -> list[int]:
    """Returns the indices of ``samples`` where at least one feature's z-score (against that
    feature's own mean/stddev across ``samples``) exceeds ``z_threshold`` in magnitude. Flags,
    does not remove — the caller (`TrainingPipelineService`) decides whether to drop them."""
    stats = {}
    for key in feature_order:
        values = [s.features[key] for s in samples if key in s.features]
        if len(values) < 2:
            stats[key] = (0.0, 0.0)
            continue
        stats[key] = (pystats.fmean(values), pystats.pstdev(values))

    flagged = []
    for i, sample in enumerate(samples):
        for key in feature_order:
            mean, std = stats[key]
            if std == 0.0 or key not in sample.features:
                continue
            z = abs((sample.features[key] - mean) / std)
            if z > z_threshold:
                flagged.append(i)
                break
    return flagged


def select_features(
    samples: list[TrainingSample], feature_order: list[str], top_k: int, method: str = "correlation"
) -> list[str]:
    """Ranks ``feature_order`` and keeps the top ``top_k`` — ``"variance"`` ranks by each
    feature's own variance across ``samples`` (unsupervised — no label needed), ``"correlation"``
    ranks by |Pearson correlation| against ``label`` (supervised — usually the stronger signal
    for a specific market's prediction target). A feature with fewer than 2 distinct values, or
    zero variance, always ranks last regardless of method."""
    if method not in {"variance", "correlation"}:
        raise ValueError(f"unsupported feature selection method '{method}'")
    if top_k >= len(feature_order):
        return list(feature_order)

    scores: dict[str, float] = {}
    labels = [s.label for s in samples]
    for key in feature_order:
        values = [s.features.get(key, 0.0) for s in samples]
        if len(set(values)) < 2:
            scores[key] = -1.0
            continue
        if method == "variance":
            scores[key] = pystats.pvariance(values)
        else:
            scores[key] = abs(_pearson_correlation(values, labels))

    ranked = sorted(feature_order, key=lambda key: scores[key], reverse=True)
    return ranked[:top_k]


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    n = len(x)
    mean_x, mean_y = pystats.fmean(x), pystats.fmean(y)
    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    denom_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
    denom_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5
    if denom_x == 0.0 or denom_y == 0.0:
        return 0.0
    return numerator / (denom_x * denom_y)
