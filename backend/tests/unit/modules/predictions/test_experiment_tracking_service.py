from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.experiment_tracking_service import (
    ExperimentNotFoundError,
    ExperimentTrackingService,
    InvalidExperimentDecisionError,
)
from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.domain.model_selection import CandidateSpec, ModelSelectionResult
from modules.predictions.domain.validation import (
    CrossValidationResult,
    FoldResult,
    HPOResult,
    HPOStrategy,
    HPOTrial,
    ValidationStrategy,
)
from modules.predictions.domain.value_objects import MarketId


@pytest.fixture
def service(experiment_repo):
    return ExperimentTrackingService(experiments=experiment_repo)


@pytest.fixture
def market_id():
    return MarketId(uuid4())


@pytest.fixture
def now():
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _cv_result() -> CrossValidationResult:
    return CrossValidationResult(
        strategy=ValidationStrategy.K_FOLD,
        fold_results=(FoldResult(fold_index=0, metric_name="accuracy", metric_value=0.8, sample_count=10),),
        mean_metric=0.8,
        std_metric=0.0,
    )


def _hpo_result() -> HPOResult:
    return HPOResult(
        strategy=HPOStrategy.RANDOM_SEARCH,
        trials=(HPOTrial(trial_index=0, params={"n_estimators": 100}, metric_value=0.9),),
        best_params={"n_estimators": 100},
        best_metric_value=0.9,
    )


class TestRecordValidation:
    async def test_records_experiment_with_pending_decision(self, service, market_id, now):
        experiment = await service.record_validation(market_id, _cv_result(), now)
        assert experiment.market_id == market_id
        assert experiment.decision == "pending"
        assert experiment.config == {"kind": "validation", "strategy": "k_fold", "fold_count": 1}
        assert experiment.metrics == {"mean_metric": 0.8, "std_metric": 0.0}


class TestRecordHPO:
    async def test_records_experiment_with_best_params_as_metrics(self, service, market_id, now):
        experiment = await service.record_hpo(market_id, _hpo_result(), now)
        assert experiment.config == {"kind": "hpo", "strategy": "random_search", "trial_count": 1}
        assert experiment.metrics == {"best_metric_value": 0.9, "param.n_estimators": 100}


class TestCompare:
    async def test_returns_experiments_for_market_only(self, service, market_id, now):
        other_market = MarketId(uuid4())
        await service.record_validation(market_id, _cv_result(), now)
        await service.record_validation(other_market, _cv_result(), now)

        results = await service.compare(market_id)

        assert len(results) == 1
        assert results[0].market_id == market_id


class TestRecordModelSelection:
    async def test_persists_every_non_skipped_candidates_score_not_just_the_winners(self, service, market_id, now):
        """Statistical-baseline charter audit fix: a losing baseline's score must survive in the
        persisted `Experiment`, not just the winner's — this is what makes "did ML actually beat
        the baseline" reconstructable later."""
        winner = CandidateSpec(MLAlgorithm.RANDOM_FOREST, MLFramework.SKLEARN)
        baseline = CandidateSpec(MLAlgorithm.RIDGE, MLFramework.SKLEARN, is_baseline=True)
        skipped = CandidateSpec(MLAlgorithm.GAUSSIAN_NB, MLFramework.SKLEARN)

        result = ModelSelectionResult(
            winning_candidate=winner,
            winning_model=object(),
            ranking_metric="mae",
            ranking_value=0.5,
            all_candidates=(winner, baseline, skipped),
            skipped_candidates=((skipped, "unsupported for target type"),),
            candidate_scores=((winner, 0.5), (baseline, 0.9)),
        )

        experiment = await service.record_model_selection(market_id, result, now)

        assert experiment.metrics["ranking.mae"] == 0.5
        assert experiment.metrics["candidate.random_forest"] == 0.5
        assert experiment.metrics["candidate.ridge"] == 0.9
        assert "candidate.gaussian_nb" not in experiment.metrics
        assert experiment.config["baseline_candidates"] == ["ridge"]
        assert experiment.config["winner_is_baseline"] is False

    async def test_flags_when_the_baseline_itself_wins(self, service, market_id, now):
        baseline = CandidateSpec(MLAlgorithm.POISSON_GLM, MLFramework.SKLEARN, is_baseline=True)
        result = ModelSelectionResult(
            winning_candidate=baseline,
            winning_model=object(),
            ranking_metric="mae",
            ranking_value=0.3,
            all_candidates=(baseline,),
            candidate_scores=((baseline, 0.3),),
        )

        experiment = await service.record_model_selection(market_id, result, now)

        assert experiment.config["winner_is_baseline"] is True


class TestDecide:
    async def test_updates_decision(self, service, market_id, now):
        experiment = await service.record_validation(market_id, _cv_result(), now)
        updated = await service.decide(experiment.id, "promoted")
        assert updated.decision == "promoted"

    async def test_invalid_decision_raises(self, service, market_id, now):
        experiment = await service.record_validation(market_id, _cv_result(), now)
        with pytest.raises(InvalidExperimentDecisionError):
            await service.decide(experiment.id, "maybe")

    async def test_unknown_experiment_raises(self, service):
        from modules.predictions.domain.value_objects import ExperimentId

        with pytest.raises(ExperimentNotFoundError):
            await service.decide(ExperimentId(uuid4()), "promoted")
