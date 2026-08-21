"""ML platform value objects (Milestone 9.1 "Enterprise Machine Learning Platform").

Additive to `modules.predictions.domain.value_objects` — `ModelDefinition.algorithm`/
`ModelDefinition.framework` remain plain strings (docs/decisions.md ADR-008: persistence stays
enum-free so a new algorithm never needs a migration), these enums exist purely so application
and infrastructure code gets type safety and a single source of truth for the concrete names
Milestone 9.1 introduces.
"""

from __future__ import annotations

from enum import Enum


class MLFramework(str, Enum):
    LIGHTGBM = "lightgbm"
    XGBOOST = "xgboost"
    CATBOOST = "catboost"
    SKLEARN = "sklearn"
    # Statistical-baseline charter, Phase 3 — a real 1:1 framework->adapter mapping for
    # `FootballGoalsPoissonAdapter`, matching the convention every other framework already
    # establishes, rather than overloading SKLEARN to sometimes mean SklearnAdapter.
    POISSON_GOALS = "poisson_goals"


class MLAlgorithm(str, Enum):
    """The 11 concrete production algorithms named by the Milestone 9.1 spec, grouped by family:
    Gradient Boosting x3 (one per framework), Tree Models x2, Linear Models x3, Kernel x1,
    Probabilistic x1, Neural x1 — plus two Statistical Baseline GLMs (regression-only) added per
    the "every trainable market should have a simple statistical baseline" charter."""

    # Gradient Boosting
    LIGHTGBM_GBM = "lightgbm_gbm"
    XGBOOST_GBM = "xgboost_gbm"
    CATBOOST_GBM = "catboost_gbm"
    # Tree Models
    RANDOM_FOREST = "random_forest"
    EXTRA_TREES = "extra_trees"
    # Linear Models
    LOGISTIC_REGRESSION = "logistic_regression"
    RIDGE = "ridge"
    ELASTIC_NET = "elastic_net"
    # Kernel
    SVM = "svm"
    # Probabilistic
    GAUSSIAN_NB = "gaussian_nb"
    # Neural
    MLP = "mlp"
    # Statistical Baseline (regression-only GLMs — count/continuous targets)
    POISSON_GLM = "poisson_glm"
    TWEEDIE_GLM = "tweedie_glm"
    # Statistical Baseline (football goals/score markets — see FootballGoalsPoissonAdapter)
    POISSON_GOALS_MODEL = "poisson_goals_model"


ALGORITHM_FRAMEWORK: dict[MLAlgorithm, MLFramework] = {
    MLAlgorithm.LIGHTGBM_GBM: MLFramework.LIGHTGBM,
    MLAlgorithm.XGBOOST_GBM: MLFramework.XGBOOST,
    MLAlgorithm.CATBOOST_GBM: MLFramework.CATBOOST,
    MLAlgorithm.RANDOM_FOREST: MLFramework.SKLEARN,
    MLAlgorithm.EXTRA_TREES: MLFramework.SKLEARN,
    MLAlgorithm.LOGISTIC_REGRESSION: MLFramework.SKLEARN,
    MLAlgorithm.RIDGE: MLFramework.SKLEARN,
    MLAlgorithm.ELASTIC_NET: MLFramework.SKLEARN,
    MLAlgorithm.SVM: MLFramework.SKLEARN,
    MLAlgorithm.GAUSSIAN_NB: MLFramework.SKLEARN,
    MLAlgorithm.MLP: MLFramework.SKLEARN,
    MLAlgorithm.POISSON_GLM: MLFramework.SKLEARN,
    MLAlgorithm.TWEEDIE_GLM: MLFramework.SKLEARN,
}


class EnsembleMethod(str, Enum):
    """Milestone 9.1 "Ensemble Learning" — combination strategies over a set of already-fitted
    `PredictionModelPort` members, all sharing one market's `feature_order`."""

    SOFT_VOTING = "soft_voting"
    HARD_VOTING = "hard_voting"
    WEIGHTED_VOTING = "weighted_voting"
    STACKING = "stacking"
    BLENDING = "blending"
    DYNAMIC = "dynamic"
