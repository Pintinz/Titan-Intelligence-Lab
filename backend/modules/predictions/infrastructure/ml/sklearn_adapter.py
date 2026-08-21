"""Generic scikit-learn `PredictionModelPort` adapter (Milestone 9.1 "Tree Models", "Linear
Models", "Kernel", "Probabilistic", "Neural" families) — one real, parametrized adapter class
serving all 8 non-boosting algorithms, the same "handful of real classes, not one per market"
posture `WeightedLogisticPredictor`/`WeightedLinearPredictor` already established
(docs/decisions.md — data-driven market registry).

Not every algorithm has a sensible classifier *and* regressor form:
- `GAUSSIAN_NB` is inherently probabilistic/classification-only (no regression counterpart).
- `LOGISTIC_REGRESSION` is inherently classification-only (`Ridge`/`ElasticNet` are its
  regression-shaped siblings in the "Linear Models" family instead).
Requesting an unsupported (algorithm, target_type) combination raises
`UnsupportedAlgorithmForTargetTypeError` rather than silently substituting a different algorithm.

Scale-sensitive algorithms (`LOGISTIC_REGRESSION`, `RIDGE`, `ELASTIC_NET`, `SVM`, `MLP`) are
wrapped in an `sklearn.pipeline.Pipeline` with a `StandardScaler` first stage (Milestone 9.1
Training Platform "Scaling" requirement) — this is real, not cosmetic: unscaled features across
`FeatureDefinition`s with very different natural ranges would otherwise dominate these
algorithms' gradients/distances. Tree ensembles (`RANDOM_FOREST`/`EXTRA_TREES`) and `GAUSSIAN_NB`
deliberately skip scaling — split-based trees are invariant to monotonic feature transforms, and
scaling would violate `GaussianNB`'s own per-feature distributional assumptions. Wrapping in a
`Pipeline` (rather than hand-rolling scaler persistence) means `serialize()`/`deserialize()` need
no special-casing — pickling the pipeline object carries the fitted scaler's mean/variance along
with the estimator automatically, and `predict_proba`/`decision_function` calls on `self._model`
forward transparently to the pipeline's final step exactly as they would for a bare estimator.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import ElasticNet, LogisticRegression, PoissonRegressor, Ridge, RidgeClassifier, SGDClassifier, TweedieRegressor
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC, SVR

from modules.predictions.domain.ml_value_objects import MLAlgorithm
from modules.predictions.domain.value_objects import TargetType
from modules.predictions.infrastructure.ml._math import feature_union, logit, multiclass_prediction, sigmoid, vectorize
from modules.predictions.ports.ml_model import (
    MIN_TRAINING_SAMPLES,
    InsufficientTrainingDataError,
    ModelNotFittedError,
    ModelPrediction,
    TrainingMetrics,
    TrainingSample,
    UnsupportedAlgorithmForTargetTypeError,
)

_CLASSIFICATION_ONLY = {MLAlgorithm.LOGISTIC_REGRESSION, MLAlgorithm.GAUSSIAN_NB}
# Statistical Baseline GLMs (Poisson/Tweedie) have no classification form — they model a count/
# continuous mean via a log-link, not a class probability. Requesting either for CLASSIFICATION
# raises UnsupportedAlgorithmForTargetTypeError, same posture as the _CLASSIFICATION_ONLY guard.
_REGRESSION_ONLY: set[MLAlgorithm] = {MLAlgorithm.POISSON_GLM, MLAlgorithm.TWEEDIE_GLM}
_SCALE_SENSITIVE = {MLAlgorithm.LOGISTIC_REGRESSION, MLAlgorithm.RIDGE, MLAlgorithm.ELASTIC_NET, MLAlgorithm.SVM, MLAlgorithm.MLP}


def _build_estimator(algorithm: MLAlgorithm, target_type: TargetType, params: dict):
    is_classification = target_type is TargetType.CLASSIFICATION

    if algorithm in _CLASSIFICATION_ONLY and not is_classification:
        raise UnsupportedAlgorithmForTargetTypeError(f"{algorithm.value} has no regression form")
    if algorithm in _REGRESSION_ONLY and is_classification:
        raise UnsupportedAlgorithmForTargetTypeError(f"{algorithm.value} has no classification form")

    if algorithm is MLAlgorithm.RANDOM_FOREST:
        estimator = RandomForestClassifier(**params) if is_classification else RandomForestRegressor(**params)
    elif algorithm is MLAlgorithm.EXTRA_TREES:
        estimator = ExtraTreesClassifier(**params) if is_classification else ExtraTreesRegressor(**params)
    elif algorithm is MLAlgorithm.LOGISTIC_REGRESSION:
        estimator = LogisticRegression(**params)
    elif algorithm is MLAlgorithm.RIDGE:
        estimator = RidgeClassifier(**params) if is_classification else Ridge(**params)
    elif algorithm is MLAlgorithm.ELASTIC_NET:
        estimator = (
            SGDClassifier(loss="log_loss", penalty="elasticnet", **params) if is_classification else ElasticNet(**params)
        )
    elif algorithm is MLAlgorithm.SVM:
        # SVC(probability=True) is deprecated (sklearn 1.9, removal 1.11) in favor of an explicit
        # calibration wrapper — same Platt-style internal calibration, just no longer implicit.
        estimator = CalibratedClassifierCV(SVC(**params), ensemble=False) if is_classification else SVR(**params)
    elif algorithm is MLAlgorithm.GAUSSIAN_NB:
        estimator = GaussianNB(**params)
    elif algorithm is MLAlgorithm.MLP:
        estimator = MLPClassifier(**params) if is_classification else MLPRegressor(**params)
    elif algorithm is MLAlgorithm.POISSON_GLM:
        estimator = PoissonRegressor(**params)
    elif algorithm is MLAlgorithm.TWEEDIE_GLM:
        # power=1.5 (compound Poisson-Gamma) is the default when unspecified — approximates
        # over-dispersed count variance without literally being negative-binomial (sklearn has no
        # native NB GLM); callers can override via `params={"power": ...}`.
        estimator = TweedieRegressor(power=params.get("power", 1.5), **{k: v for k, v in params.items() if k != "power"})
    else:
        raise UnsupportedAlgorithmForTargetTypeError(f"'{algorithm}' is not a scikit-learn algorithm")

    if algorithm in _SCALE_SENSITIVE:
        return Pipeline([("scaler", StandardScaler()), ("model", estimator)])
    return estimator


def _final_estimator(model):
    """Unwraps a `Pipeline`'s final step — scale-sensitive algorithms are wrapped, tree
    ensembles/GaussianNB are not; `feature_importance()` needs the bare estimator either way."""
    if isinstance(model, Pipeline):
        return model.named_steps["model"]
    return model


def _feature_importance_from_estimator(model, feature_order: list[str]) -> dict[str, float]:
    """Not every sklearn estimator exposes `feature_importances_`/`coef_` the same way —
    tree ensembles have the former, linear models the latter (magnitude, not sign, for
    importance ranking), SVM/GaussianNB/MLP expose neither so importance falls back to a
    uniform distribution (honest "no per-feature signal available" default, not a fabricated
    ranking)."""
    estimator = _final_estimator(model)
    if hasattr(estimator, "feature_importances_"):
        importances = np.asarray(estimator.feature_importances_, dtype=float)
    elif hasattr(estimator, "coef_"):
        importances = np.abs(np.asarray(estimator.coef_, dtype=float)).reshape(-1)
        if importances.shape[0] != len(feature_order):
            importances = importances[: len(feature_order)]
    else:
        n = len(feature_order) or 1
        return {key: 1.0 / n for key in feature_order} if feature_order else {}

    total = float(importances.sum()) or 1.0
    return {key: float(value) / total for key, value in zip(feature_order, importances)}


@dataclass
class SklearnAdapter:
    algorithm: MLAlgorithm = MLAlgorithm.RANDOM_FOREST
    target_type: TargetType = TargetType.CLASSIFICATION
    params: dict = field(default_factory=dict)
    feature_order: list[str] = field(default_factory=list)
    class_labels: tuple[str, ...] = field(default_factory=tuple)
    _model: object | None = field(default=None, repr=False)

    async def fit(
        self, samples: list[TrainingSample], validation_samples: list[TrainingSample] | None = None
    ) -> TrainingMetrics:
        # No sklearn estimator here takes an external eval_set for early stopping the way the
        # boosting adapters do — MLPClassifier/MLPRegressor's own `early_stopping` param (set via
        # `params`) carves an internal validation split instead. Accepted for `PredictionModelPort`
        # signature consistency, intentionally unused otherwise.
        del validation_samples
        if len(samples) < MIN_TRAINING_SAMPLES:
            raise InsufficientTrainingDataError(
                f"SklearnAdapter({self.algorithm.value}) requires >= {MIN_TRAINING_SAMPLES} samples, got {len(samples)}"
            )
        self.feature_order = feature_union(samples)
        X = np.array([vectorize(s.features, self.feature_order) for s in samples])
        y = np.array([s.label for s in samples])

        model = _build_estimator(self.algorithm, self.target_type, self.params)
        model.fit(X, y)
        predictions = model.predict(X)

        if self.target_type is TargetType.CLASSIFICATION:
            metric_name, metric_value = "train_accuracy", float(np.mean(predictions == y))
        else:
            metric_name, metric_value = "train_mae", float(np.mean(np.abs(predictions - y)))

        self._model = model
        return TrainingMetrics(sample_count=len(samples), metric_name=metric_name, metric_value=metric_value)

    def predict_one(self, features: dict[str, float]) -> ModelPrediction:
        if self._model is None:
            raise ModelNotFittedError(f"SklearnAdapter({self.algorithm.value}).predict_one called before fit()/deserialize()")
        x = np.array([vectorize(features, self.feature_order)])
        if self.target_type is TargetType.CLASSIFICATION:
            if self.class_labels:
                # Multiclass (2026-08-06). Confirmed live against football.correct_score's real
                # training data: RidgeClassifier has neither predict_proba nor a single-score
                # decision_function for multiclass — it returns one raw score per class instead.
                # Softmax-normalizing those scores is the direct multiclass generalization of the
                # binary path's own sigmoid(decision_function) proxy below — same honest-estimate
                # posture, just N-way instead of two-way.
                classes_seen = _final_estimator(self._model).classes_
                if hasattr(self._model, "predict_proba"):
                    probabilities = self._model.predict_proba(x)[0]
                else:
                    scores = np.asarray(self._model.decision_function(x)[0], dtype=float)
                    exp_scores = np.exp(scores - scores.max())
                    probabilities = exp_scores / exp_scores.sum()
                return multiclass_prediction(probabilities, classes_seen, self.class_labels)
            if hasattr(self._model, "predict_proba"):
                probability = float(self._model.predict_proba(x)[0][1])
            else:
                # RidgeClassifier/SGDClassifier(no predict_proba w/ some losses) — decision_function
                # squashed through sigmoid is the honest proxy, same shape as WeightedLogisticPredictor.
                probability = sigmoid(float(self._model.decision_function(x)[0]))
            return ModelPrediction(
                raw_score=logit(probability),
                probability=probability,
                value="positive" if probability >= 0.5 else "negative",
            )
        raw_value = float(self._model.predict(x)[0])
        return ModelPrediction(raw_score=raw_value, probability=sigmoid(raw_value), value=f"{raw_value:.4f}")

    def feature_importance(self) -> dict[str, float]:
        if self._model is None:
            raise ModelNotFittedError(f"SklearnAdapter({self.algorithm.value}).feature_importance called before fit()/deserialize()")
        return _feature_importance_from_estimator(self._model, self.feature_order)

    def is_fitted(self) -> bool:
        return self._model is not None

    def underlying_estimator(self):
        """Raw fitted estimator — for scale-sensitive algorithms this is the `Pipeline` (scaler +
        model), not the bare model, since SHAP needs to see the same input space `predict_one()`
        does. Used for SHAP `TreeExplainer`/`LinearExplainer`/`KernelExplainer` selection
        (Milestone 9.1 task #166). Returns ``None`` if not yet fitted."""
        return self._model

    def serialize(self) -> bytes:
        if self._model is None:
            raise ModelNotFittedError(f"SklearnAdapter({self.algorithm.value}).serialize called before fit()/deserialize()")
        return pickle.dumps(
            {
                "model": self._model,
                "feature_order": self.feature_order,
                "target_type": self.target_type,
                "algorithm": self.algorithm,
                "params": self.params,
                "class_labels": self.class_labels,
            }
        )

    def deserialize(self, payload: bytes) -> None:
        state = pickle.loads(payload)
        self._model = state["model"]
        self.feature_order = state["feature_order"]
        self.target_type = state["target_type"]
        self.algorithm = state["algorithm"]
        self.params = state["params"]
        self.class_labels = state.get("class_labels", ())
