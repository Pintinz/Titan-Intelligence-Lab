"""Pure probability-scoring metrics shared by training-time candidate ranking
(`training_pipeline_service.py`) and post-hoc Challenger-vs-Champion comparison
(`model_comparison_service.py`) — one implementation, not two, so both places rank models by the
identical formula (Continuous Outcome Learning Engine spec §8: "For probability predictions
prioritize: 1. Log Loss  2. Brier Score  3. Calibration ...").

No framework imports — same domain-purity rule as every other module (docs/architecture.md §2).
"""

from __future__ import annotations

import math

_EPS = 1e-15


def log_loss(probabilities_of_true_class: list[float]) -> float:
    """Mean binary cross-entropy: for each sample, the probability the model assigned to
    whichever class actually happened (already resolved by the caller — binary classification
    passes `probability` or `1 - probability` depending on the realized label; multiclass passes
    `distribution[true_label]`). Clipped to `[eps, 1-eps]` so a model assigning a hard 0.0 to the
    true class doesn't produce `-inf` and poison the ranking with an unusable value."""
    if not probabilities_of_true_class:
        return 0.0
    clipped = (min(max(p, _EPS), 1.0 - _EPS) for p in probabilities_of_true_class)
    return -sum(math.log(p) for p in clipped) / len(probabilities_of_true_class)
