"""Champion Validation + Calibration (Phase 3, Workstream A).

For a market's Champion model, honestly reconstructs a chronological calibration/test split from
the newest slice of its real outcome history (this codebase's `DatasetBuilder`/`Dataset` persist
no train/val/test split at all — see this module's own audit note below — so a fresh split is
derived here every run, not read from anywhere), evaluates the Champion's raw ("uncalibrated")
probabilities against two real recalibration candidates — Platt/sigmoid and isotonic, both via
scikit-learn's own `CalibratedClassifierCV` wrapping a `FrozenEstimator` (no bespoke calibration
math) — persists a `CalibrationReport` for every binary-market candidate evaluated (not just the
winner, per the Phase 3 command's own instruction), and only when a candidate empirically and
materially improves probability quality registers a new CHALLENGER model version wrapping the same
fitted classifier plus the winning calibration mapping. Never retrains the base classifier, never
touches the Champion in place, never auto-promotes to CHAMPION — that stays a separate, explicit
`ModelRegistryService.promote_to_champion` call this service's caller makes only after reviewing
the recorded decision, mirroring that service's own existing separation of "register a challenger"
from "promote it."

**Honestly-documented limitation** (same "documented proxy, not fabricated" posture as
`calibration_fitting_service.py`'s own docstring): since no split is ever persisted anywhere in
this codebase, this service cannot prove the reserved chronological tail was entirely excluded
from the Champion's original training run — it can only reason that the newest slice of the full
dataset is the least likely to have been part of whatever earlier held-out fold `TIME_SERIES_SPLIT`
used when the Champion was originally trained. Treated as the best available honest
reconstruction given the data that actually exists, not claimed as a leak-proof guarantee.

**Multiclass markets** (`football.match_winner`, `football.first_half_winner`,
`football.second_half_winner`, `football.correct_score`) have no reliability-curve/ECE concept —
`CalibrationReportBuilder` is a binary-only tool (Milestone 9.1) and forcing a 3-/37-way
probability vector into it would fabricate a number with no real meaning. These markets are
compared on log loss instead (a proper scoring rule that's well-defined for any number of
classes) and get no `CalibrationReport` row — the decision is recorded in the returned
`ChampionValidationResult` and the Phase 3 report, not silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import log_loss as sk_log_loss
from sklearn.pipeline import Pipeline

from modules.predictions.application.calibration_reporting_service import CalibrationReportBuilder
from modules.predictions.application.dataset_builder_service import DatasetBuilder
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.domain.calibration import CalibrationMethod, CalibrationReport
from modules.predictions.domain.ml_value_objects import MLAlgorithm
from modules.predictions.domain.entities import MarketDefinition
from modules.predictions.domain.value_objects import MarketId, MarketStatus, ModelId, TargetType
from modules.predictions.infrastructure.ml.football_goals_poisson_adapter import (
    FootballGoalsPoissonAdapter,
    PoissonGridClassifierView,
)
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService, compute_artifact_checksum
from modules.predictions.infrastructure.ml.sklearn_adapter import SklearnAdapter
from modules.predictions.ports.ml_model import ModelArtifactStorePort
from modules.predictions.ports.repositories import CalibrationReportRepositoryPort, MarketRepositoryPort, ModelRepositoryPort

MIN_CALIBRATION_SAMPLES = 20
MIN_TEST_SAMPLES = 20
HOLDOUT_FRACTION = 0.3  # fraction of the full chronological dataset reserved for calib+test
ECE_IMPROVEMENT_THRESHOLD = 0.15  # relative ECE improvement required to prefer a candidate (binary)
BRIER_DEGRADATION_TOLERANCE = 0.02  # Brier allowed to worsen by at most this relative amount
LOG_LOSS_IMPROVEMENT_THRESHOLD = 0.02  # relative log-loss improvement required (multiclass)


class CalibrationBlockedError(ValueError):
    """Raised when a market's Champion cannot be validated this run — no Champion, no usable
    estimator, or too few chronologically-referenced held-out samples. Never silently skipped;
    callers must catch and record the reason (Phase 3 §49 STOP-condition posture)."""


@dataclass(frozen=True)
class CalibrationCandidateResult:
    method: CalibrationMethod
    report: CalibrationReport | None  # None for multiclass markets — see module docstring
    log_loss: float
    sample_count: int
    excluded_unseen_class_count: int = 0
    """Multiclass only — held-out samples whose true label had no probability column in the
    fitted model (never observed during training) and so were excluded from log loss, not scored
    as wrong. 0 for every binary market."""


@dataclass(frozen=True)
class ChampionValidationResult:
    market_key: str
    model_id: ModelId
    algorithm: str
    is_multiclass: bool
    calibration_sample_count: int
    test_sample_count: int
    candidates: tuple[CalibrationCandidateResult, ...]
    winner: CalibrationMethod
    decision_reason: str
    promoted_model_id: ModelId | None = None


@dataclass(frozen=True)
class ValidationSweepOutcome:
    """One PRODUCTION market's result from `validate_all_production_markets` — a market whose
    Champion couldn't be validated this run (no Champion yet, too few chronologically-referenced
    samples, etc.) is recorded with an honest `reason`, never silently dropped from the sweep."""

    market_key: str
    validated: bool
    result: ChampionValidationResult | None = None
    reason: str | None = None


@dataclass
class CalibrationValidationService:
    dataset_builder: DatasetBuilder
    model_loader: ModelLoaderService
    models: ModelRepositoryPort
    calibration_reports: CalibrationReportRepositoryPort
    model_registry: ModelRegistryService
    artifact_store: ModelArtifactStorePort
    markets: MarketRepositoryPort | None = None
    """Phase 3 audit fix — optional (default `None`) so existing callers that construct this
    service without it (the manual `scripts/phase3_champion_calibration_validation.py` runner)
    keep working unchanged; required only by `validate_all_production_markets`, the periodic sweep
    a Celery beat task now calls (see module docstring's own audit note: this service previously
    had zero scheduled callers)."""
    report_builder: CalibrationReportBuilder = field(default_factory=CalibrationReportBuilder)

    async def validate_all_production_markets(self, now: datetime) -> list[ValidationSweepOutcome]:
        """Checked, and validated where enough real held-out history exists, every PRODUCTION
        market's Champion — mirrors `CalibrationFittingService.fit_all_production_markets`'s own
        sweep shape. One market's `CalibrationBlockedError` never stops the rest of the sweep."""
        assert self.markets is not None, "validate_all_production_markets requires `markets` to be wired"
        outcomes: list[ValidationSweepOutcome] = []
        for market in await self.markets.list_by_status(MarketStatus.PRODUCTION):
            outcomes.append(await self._validate_market_safe(market, now))
        return outcomes

    async def _validate_market_safe(self, market: MarketDefinition, now: datetime) -> ValidationSweepOutcome:
        try:
            result = await self.validate_market(market.id, market.market_key, now)
            return ValidationSweepOutcome(market_key=market.market_key, validated=True, result=result)
        except CalibrationBlockedError as exc:
            return ValidationSweepOutcome(market_key=market.market_key, validated=False, reason=str(exc))

    async def validate_market(self, market_id: MarketId, market_key: str, now: datetime) -> ChampionValidationResult:
        champion = await self.models.get_champion(market_id)
        if champion is None:
            raise CalibrationBlockedError(f"{market_key}: no champion model")

        dataset = await self.dataset_builder.build(market_id, now)
        samples = sorted(
            (s for s in dataset.samples if s.reference_time is not None), key=lambda s: s.reference_time
        )
        if len(samples) < MIN_CALIBRATION_SAMPLES + MIN_TEST_SAMPLES:
            raise CalibrationBlockedError(
                f"{market_key}: only {len(samples)} chronologically-referenced samples, need "
                f">= {MIN_CALIBRATION_SAMPLES + MIN_TEST_SAMPLES}"
            )

        tail_size = max(int(len(samples) * HOLDOUT_FRACTION), MIN_CALIBRATION_SAMPLES + MIN_TEST_SAMPLES)
        tail = samples[-tail_size:]
        split_point = len(tail) // 2
        calibration_samples = tail[:split_point]
        test_samples = tail[split_point:]
        if len(calibration_samples) < MIN_CALIBRATION_SAMPLES or len(test_samples) < MIN_TEST_SAMPLES:
            raise CalibrationBlockedError(
                f"{market_key}: chronological tail too small to split "
                f"({len(calibration_samples)} calibration / {len(test_samples)} test)"
            )

        adapter = await self.model_loader.load(
            champion.id, champion.framework, champion.algorithm, TargetType.CLASSIFICATION, champion.artifact_ref
        )
        # The `TargetType.CLASSIFICATION` passed above is only a constructor placeholder for the
        # empty adapter `model_loader.load()` builds before `deserialize()` restores its real,
        # originally-trained `target_type` from the artifact payload — this whole method (Platt/
        # isotonic recalibration, log-loss/ECE comparison) is a classification-only concept with
        # no regression equivalent anywhere in this codebase. Confirmed live:
        # basketball.game_total_points_prediction is a real REGRESSION-target PRODUCTION market
        # (CatBoostRegressor Champion) with zero guard here before this fix, which crashed with
        # `AttributeError: 'CatBoostRegressor' object has no attribute 'decision_function'` and,
        # same as the Poisson/LightGBM defects above, aborted `validate_all_production_markets`'s
        # sweep for every other PRODUCTION market too.
        if adapter.target_type is not TargetType.CLASSIFICATION:
            raise CalibrationBlockedError(
                f"{market_key}: target_type={adapter.target_type.value} — calibration validation "
                "is a classification-only concept, not applicable to a regression-shaped market"
            )
        estimator = adapter.underlying_estimator()
        if estimator is None:
            raise CalibrationBlockedError(f"{market_key}: champion artifact has no usable estimator")

        feature_order = adapter.feature_order
        class_labels = adapter.class_labels
        is_multiclass = bool(class_labels)
        if isinstance(adapter, FootballGoalsPoissonAdapter):
            # `underlying_estimator()` returns the raw `(home_model, away_model)` GLM pair for
            # this adapter — neither has `predict_proba`/`decision_function`, which crashed this
            # method with `AttributeError: 'tuple' object has no attribute 'decision_function'`
            # (confirmed live against football.correct_score's real PRODUCTION Champion). Wrap it
            # in the real scikit-learn-classifier-shaped view instead — see
            # `PoissonGridClassifierView`'s own docstring.
            classes = np.arange(len(class_labels)) if is_multiclass else np.array([0, 1])
            estimator = PoissonGridClassifierView(adapter=adapter, classes_=classes)
        if is_multiclass:
            # The frozen base estimator's own `classes_` was set during its original `fit()` on
            # float-typed labels (see the label-dtype note below) — sklearn's internal calibration
            # fold bookkeeping needs it to be an actual integer dtype. Same values, just the
            # correct dtype; this doesn't change what the estimator predicts. `classes_` is a
            # read-only proxy property on a `Pipeline` (scale-sensitive algorithms), so the fix
            # must target the pipeline's final step, same unwrap `SklearnAdapter` itself uses.
            target = estimator.named_steps["model"] if isinstance(estimator, Pipeline) else estimator
            if hasattr(target, "classes_"):
                try:
                    target.classes_ = np.asarray(target.classes_).astype(int)
                except AttributeError:
                    # Confirmed live: LightGBM/XGBoost/CatBoost's sklearn wrapper classes expose
                    # `classes_` as a read-only computed property with no setter (unlike sklearn's
                    # own native classifiers, where it's a plain settable instance attribute) —
                    # crashed the whole PRODUCTION sweep on the first LightGBM multiclass Champion
                    # encountered. Every one of those wrappers already derives `classes_` from
                    # `np.unique(y)` internally during its own `fit()`, which is already a real
                    # integer dtype for these libraries regardless of the float-labeled `y` this
                    # codebase trains on — so there is nothing to honestly fix here, just nothing
                    # this call needs to (or can) do.
                    pass

        X_calib = _vectorize(calibration_samples, feature_order)
        X_test = _vectorize(test_samples, feature_order)
        # Multiclass labels are integer-valued class-index floats (see `TrainingSample.label`'s
        # own docstring); scikit-learn's internal `CalibratedClassifierCV` fold bookkeeping fancy-
        # indexes by `estimator.classes_`, which requires an actual integer dtype — a genuinely
        # float `classes_` (inherited from fitting on float labels) raises `IndexError` deep
        # inside sklearn. Binary labels stay float (0.0/1.0), matching every other consumer.
        label_dtype = int if is_multiclass else float
        y_calib = np.array([s.label for s in calibration_samples], dtype=label_dtype)
        y_test = np.array([s.label for s in test_samples], dtype=label_dtype)

        candidates: list[CalibrationCandidateResult] = [
            self._evaluate(CalibrationMethod.NONE, estimator, X_test, y_test, is_multiclass, now)
        ]

        # A high-cardinality multiclass market (football.correct_score's 37-cell grid) can have
        # calibration-set classes represented by a single example — scikit-learn's internal
        # cross-validated calibration-curve fitting needs at least 2 per class to stratify at all;
        # with only 1, folds end up seeing a different class set than `classes_` declares, and
        # sklearn's own fold-reconciliation code raises `IndexError` rather than a clean message.
        # Honestly skipped (uncalibrated result still reported) rather than crashing the market.
        min_class_count = min(np.unique(y_calib, return_counts=True)[1]) if len(y_calib) else 0
        if is_multiclass and min_class_count < 2:
            return_candidates_only_uncalibrated = True
        else:
            return_candidates_only_uncalibrated = False

        if not return_candidates_only_uncalibrated:
            for method, sk_method in (
                (CalibrationMethod.PLATT_SCALING, "sigmoid"),
                (CalibrationMethod.ISOTONIC_REGRESSION, "isotonic"),
            ):
                try:
                    calibrated = CalibratedClassifierCV(FrozenEstimator(estimator), method=sk_method)
                    calibrated.fit(X_calib, y_calib)
                except (ValueError, IndexError):
                    # e.g. isotonic degenerate on too few per-class calibration samples, or a
                    # sparse-multiclass fold mismatch — an honestly skipped candidate, not a
                    # crashed market validation.
                    continue
                candidates.append(self._evaluate(method, calibrated, X_test, y_test, is_multiclass, now))

        for candidate in candidates:
            if candidate.report is not None:
                await self.calibration_reports.record(champion.id, candidate.report)

        winner, reason = _decide_winner(candidates, is_multiclass)

        promoted_model_id = None
        if winner.method is not CalibrationMethod.NONE:
            challenger = await self._register_calibrated_challenger(
                champion=champion,
                market_id=market_id,
                method=winner.method,
                X_calib=X_calib,
                y_calib=y_calib,
                estimator=estimator,
                feature_order=feature_order,
                class_labels=class_labels,
                now=now,
            )
            promoted_model_id = challenger.id

        return ChampionValidationResult(
            market_key=market_key,
            model_id=champion.id,
            algorithm=champion.algorithm,
            is_multiclass=is_multiclass,
            calibration_sample_count=len(calibration_samples),
            test_sample_count=len(test_samples),
            candidates=tuple(candidates),
            winner=winner.method,
            decision_reason=reason,
            promoted_model_id=promoted_model_id,
        )

    def _evaluate(self, method, estimator, X_test, y_test, is_multiclass, now):
        proba = _predict_proba(estimator, X_test, is_multiclass)
        if is_multiclass:
            # `estimator.classes_` is the real fitted class set — for a market with as many
            # possible outcomes as football.correct_score's 37-cell grid, a rare scoreline can
            # genuinely have zero training examples and so no probability column at all. Scoring
            # against `range(proba.shape[1])` would silently assume a dense 0..n-1 label space;
            # a held-out sample whose true label the model never saw is honestly excluded from
            # log loss (it cannot be scored against a model with no probability mass reserved for
            # it) rather than crashing the whole market's validation or fabricating a score.
            classes = np.asarray(estimator.classes_)
            scoreable = np.isin(y_test, classes)
            excluded = int((~scoreable).sum())
            y_scoreable = y_test[scoreable]
            proba_scoreable = proba[scoreable]
            ll = float(sk_log_loss(y_scoreable, proba_scoreable, labels=list(classes))) if len(y_scoreable) else float("nan")
            return CalibrationCandidateResult(
                method=method, report=None, log_loss=ll, sample_count=len(y_scoreable), excluded_unseen_class_count=excluded
            )
        positive_proba = proba[:, 1] if proba.ndim == 2 else np.asarray(proba)
        pairs = list(zip((float(p) for p in positive_proba), (bool(v) for v in y_test)))
        report = self.report_builder.build(method, pairs, now)
        ll = float(sk_log_loss(y_test, positive_proba, labels=[0, 1]))
        return CalibrationCandidateResult(method=method, report=report, log_loss=ll, sample_count=len(y_test))

    async def _register_calibrated_challenger(
        self, champion, market_id, method, X_calib, y_calib, estimator, feature_order, class_labels, now
    ):
        sk_method = "sigmoid" if method is CalibrationMethod.PLATT_SCALING else "isotonic"
        calibrated = CalibratedClassifierCV(FrozenEstimator(estimator), method=sk_method)
        calibrated.fit(X_calib, y_calib)

        new_adapter = SklearnAdapter(
            algorithm=MLAlgorithm(champion.algorithm),
            target_type=TargetType.CLASSIFICATION,
            feature_order=list(feature_order),
            class_labels=class_labels,
        )
        new_adapter._model = calibrated
        payload = new_adapter.serialize()

        existing_versions = [m.version for m in await self.models.list_by_market(market_id)]
        next_version = max(existing_versions, default=champion.version) + 1
        artifact_key = f"{champion.model_key}.{champion.algorithm}/v{next_version}_calibrated_{sk_method}.bin"
        artifact_ref = await self.artifact_store.save(artifact_key, payload)
        artifact_checksum = compute_artifact_checksum(payload)

        registered = await self.model_registry.register(
            market_id=market_id,
            model_key=champion.model_key,
            version=next_version,
            algorithm=champion.algorithm,
            calibration_ref=method.value,
            now=now,
            framework=champion.framework,
            dataset_version=champion.dataset_version,
            feature_versions=champion.feature_versions,
            artifact_ref=artifact_ref,
            trained_at=now,
            artifact_checksum=artifact_checksum,
        )
        return await self.model_registry.promote_to_challenger(registered.id)


def _predict_proba(estimator, X, is_multiclass: bool) -> np.ndarray:
    """`RidgeClassifier`/`SGDClassifier`(some losses) expose no `predict_proba` — the same honest
    `decision_function` -> sigmoid/softmax proxy `SklearnAdapter.predict_one()` already uses for
    live inference (`sklearn_adapter.py`), applied vectorized here for evaluation. Every
    `CalibratedClassifierCV`-wrapped candidate always has real `predict_proba` (that's its whole
    purpose), so this fallback only ever fires for the raw uncalibrated estimator."""
    if hasattr(estimator, "predict_proba"):
        return estimator.predict_proba(X)
    scores = np.asarray(estimator.decision_function(X), dtype=float)
    if is_multiclass:
        exp_scores = np.exp(scores - scores.max(axis=1, keepdims=True))
        return exp_scores / exp_scores.sum(axis=1, keepdims=True)
    positive = 1.0 / (1.0 + np.exp(-scores))
    return np.column_stack([1.0 - positive, positive])


def _vectorize(samples, feature_order):
    return np.array([[s.features.get(key, 0.0) for key in feature_order] for s in samples])


def _decide_winner(
    candidates: list[CalibrationCandidateResult], is_multiclass: bool
) -> tuple[CalibrationCandidateResult, str]:
    baseline = next(c for c in candidates if c.method is CalibrationMethod.NONE)
    best = baseline
    reason = "no calibrated candidate materially improved probability quality; retained uncalibrated Champion"

    for candidate in candidates:
        if candidate.method is CalibrationMethod.NONE:
            continue
        if is_multiclass:
            improvement = (baseline.log_loss - candidate.log_loss) / baseline.log_loss if baseline.log_loss else 0.0
            if improvement >= LOG_LOSS_IMPROVEMENT_THRESHOLD and candidate.log_loss < best.log_loss:
                best = candidate
                reason = f"{candidate.method.value} improved log loss by {improvement:.1%} over uncalibrated"
        else:
            ece_baseline = baseline.report.expected_calibration_error
            ece_candidate = candidate.report.expected_calibration_error
            brier_baseline = baseline.report.brier_score
            brier_candidate = candidate.report.brier_score
            ece_improvement = (ece_baseline - ece_candidate) / ece_baseline if ece_baseline else 0.0
            brier_degradation = (brier_candidate - brier_baseline) / brier_baseline if brier_baseline else 0.0
            best_ece = best.report.expected_calibration_error if best.report else ece_baseline
            if (
                ece_improvement >= ECE_IMPROVEMENT_THRESHOLD
                and brier_degradation <= BRIER_DEGRADATION_TOLERANCE
                and ece_candidate < best_ece
            ):
                best = candidate
                reason = (
                    f"{candidate.method.value} improved ECE by {ece_improvement:.1%} "
                    f"(Brier change {brier_degradation:+.1%}) over uncalibrated"
                )
    return best, reason
