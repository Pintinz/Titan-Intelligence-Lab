from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.predictions.application.challenger_evaluation_service import ChallengerEvaluationService
from modules.predictions.application.dataset_builder_service import DatasetBuilder
from modules.predictions.application.dataset_registry_service import DatasetRegistryService
from modules.predictions.application.experiment_tracking_service import ExperimentTrackingService
from modules.predictions.application.model_registry_service import ModelRegistryService
from modules.predictions.application.model_selection_service import AutomaticModelSelectionService
from modules.predictions.application.scheduled_retraining_orchestrator import (
    DIXON_COLES_ELIGIBLE_MARKETS,
    MIN_TRAINING_POOL_AFTER_HOLDOUT,
    NEGATIVE_BINOMIAL_ELIGIBLE_MARKETS,
    POISSON_ELIGIBLE_MARKETS,
    SYSTEM_APPROVER,
    ScheduledRetrainingOrchestrator,
)
from modules.predictions.application.training_pipeline_service import RetrainingScheduler, TrainingPipelineService
from modules.predictions.domain.dataset import (
    Dataset,
    DatasetId,
    DatasetLineage,
    DatasetStatistics,
    DatasetStatus,
)
from modules.predictions.domain.entities import (
    ConfidenceBreakdown,
    ExplanationBundle,
    MarketDefinition,
    ModelDefinition,
    Prediction,
    PredictionOutcome,
)
from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.domain.model_comparison import ComparisonVerdict
from modules.predictions.domain.model_selection import CandidateSpec
from modules.predictions.domain.value_objects import (
    MarketId,
    MarketKind,
    MarketStatus,
    ModelId,
    ModelStatus,
    PredictionId,
    PredictionOutcomeId,
    PredictionStatus,
    TargetType,
)
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.infrastructure.persistence.in_memory_model_comparison_repository import (
    InMemoryModelComparisonRepository,
)

T0 = datetime(2026, 8, 2, tzinfo=timezone.utc)

FAST_CANDIDATES = (
    CandidateSpec(MLAlgorithm.RANDOM_FOREST, MLFramework.SKLEARN),
    CandidateSpec(MLAlgorithm.LOGISTIC_REGRESSION, MLFramework.SKLEARN),
)

CONFIDENCE = ConfidenceBreakdown(*([0.7] * 9))


@dataclass
class _ExperimentRepoFake:
    store: dict = field(default_factory=dict)

    async def get(self, experiment_id):
        return self.store.get(experiment_id)

    async def record(self, experiment):
        self.store[experiment.id] = experiment
        return experiment

    async def update(self, experiment):
        self.store[experiment.id] = experiment
        return experiment

    async def list_by_market(self, market_id, limit=50):
        return [e for e in self.store.values() if e.market_id == market_id][:limit]


@dataclass
class _InMemoryArtifactStore:
    store: dict = field(default_factory=dict)

    async def save(self, key: str, payload: bytes) -> str:
        self.store[key] = payload
        return key

    async def load(self, ref: str) -> bytes:
        return self.store[ref]


def _market(market_key="football.both_teams_to_score") -> MarketDefinition:
    return MarketDefinition(
        id=MarketId(uuid4()), market_key=market_key, sport_code="football", name="Test",
        category="goals", market_kind=MarketKind.BINARY, target_type=TargetType.CLASSIFICATION,
        status=MarketStatus.PRODUCTION,
    )


def _stale_dataset(market_id: MarketId, now: datetime) -> Dataset:
    return Dataset(
        id=DatasetId(uuid4()), market_id=market_id, version=1, content_hash="stale",
        samples=[], statistics=DatasetStatistics(sample_count=0, feature_count=0, positive_rate=None),
        lineage=DatasetLineage(market_id=market_id, source_prediction_ids=(), feature_keys=(), built_at=now - timedelta(days=8)),
        status=DatasetStatus.APPROVED, created_at=now - timedelta(days=8),
    )


def _fresh_dataset(market_id: MarketId, now: datetime) -> Dataset:
    return Dataset(
        id=DatasetId(uuid4()), market_id=market_id, version=1, content_hash="fresh",
        samples=[], statistics=DatasetStatistics(sample_count=0, feature_count=0, positive_rate=None),
        lineage=DatasetLineage(market_id=market_id, source_prediction_ids=(), feature_keys=(), built_at=now),
        status=DatasetStatus.APPROVED, created_at=now,
    )


async def _seed_champion(model_repo, market: MarketDefinition) -> ModelDefinition:
    """An already-live CHAMPION — the "this market has an established life" scenario every
    pre-existing test in this file assumes (staleness/drift retraining, human-gated promotion).
    Distinct from the bootstrap ("never trained") scenario the ML-architecture consolidation
    (2026-08-04) added, where a market genuinely has no CHAMPION row at all."""
    champion = ModelDefinition(
        id=ModelId(uuid4()), market_id=market.id, model_key=f"{market.market_key}.heuristic",
        version=1, algorithm="heuristic_logistic_v1", status=ModelStatus.CHAMPION,
    )
    return await model_repo.upsert(champion)


async def _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60):
    """Real, resolvable BTTS outcomes — half positive, half negative, with enough distinct
    feature values to avoid ZERO_VARIANCE_FEATURE/SEVERE_CLASS_IMBALANCE quality flags."""
    for i in range(n):
        prediction = Prediction(
            id=PredictionId(uuid4()), market_id=market.id, model_id=ModelId(uuid4()), subject_ref=f"fx-{i}",
            value="positive", probability=0.6, confidence=CONFIDENCE, explanation=ExplanationBundle(),
            feature_snapshot={"feature_a": float(i % 20), "feature_b": float((i * 3) % 17)},
            model_version="1", status=PredictionStatus.PUBLISHED, generated_at=T0,
        )
        await prediction_repo.record(prediction)
        error = 0.0 if i < n // 2 else 1.0  # half "matched", half "missed" -> ~50/50 real label split
        await prediction_outcome_repo.record(
            PredictionOutcome(
                id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
                actual_value="btts_yes" if error == 0.0 else "btts_no", error=error, evaluated_at=T0,
            )
        )


@pytest.fixture
def orchestrator(market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo):
    dataset_registry = DatasetRegistryService(datasets=dataset_repo)
    return ScheduledRetrainingOrchestrator(
        markets=market_repo,
        models=model_repo,
        scheduler=RetrainingScheduler(dataset_registry=dataset_registry),
        dataset_builder=DatasetBuilder(markets=market_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo),
        dataset_registry=dataset_registry,
        model_selection=AutomaticModelSelectionService(
            training_pipeline=TrainingPipelineService(),
            model_registry=ModelRegistryService(models=model_repo),
            experiments=ExperimentTrackingService(experiments=_ExperimentRepoFake()),
            artifact_store=_InMemoryArtifactStore(),
        ),
    )


@pytest.fixture
def artifact_store():
    return _InMemoryArtifactStore()


@pytest.fixture
def comparison_repo():
    return InMemoryModelComparisonRepository()


@pytest.fixture
def orchestrator_with_comparison(market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo, artifact_store, comparison_repo):
    """Same wiring as `orchestrator`, plus the Continuous Outcome Learning Engine's
    Challenger-vs-Champion comparison pieces (`model_loader`/`evaluator`/`comparisons`) — kept as
    a separate fixture rather than always-on so every pre-existing test in this file keeps
    exercising the "not wired" fallback path unchanged."""
    dataset_registry = DatasetRegistryService(datasets=dataset_repo)
    return ScheduledRetrainingOrchestrator(
        markets=market_repo,
        models=model_repo,
        scheduler=RetrainingScheduler(dataset_registry=dataset_registry),
        dataset_builder=DatasetBuilder(markets=market_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo),
        dataset_registry=dataset_registry,
        model_selection=AutomaticModelSelectionService(
            training_pipeline=TrainingPipelineService(),
            model_registry=ModelRegistryService(models=model_repo),
            experiments=ExperimentTrackingService(experiments=_ExperimentRepoFake()),
            artifact_store=artifact_store,
        ),
        model_loader=ModelLoaderService(artifact_store=artifact_store),
        evaluator=ChallengerEvaluationService(),
        comparisons=comparison_repo,
    )


@dataclass
class _FakePreflight:
    """Duck-types `TrainingPreflightService.check()` without needing its real port dependencies
    (mappings/feature_definitions/dataset_repo) — the orchestrator only ever calls `.check(...)`,
    so a fake matching that one method is sufficient to test the gating behavior in isolation."""

    ready: bool

    async def check(self, market_key: str, now: datetime):
        from modules.predictions.application.training_preflight_service import PreflightCheck, TrainingPreflightReport

        checks = (
            (PreflightCheck("market_exists", True, "ok"),)
            if self.ready
            else (PreflightCheck("sufficient_labeled_observations", False, "only 3 labeled observations, need 30"),)
        )
        return TrainingPreflightReport(market_key=market_key, ready=self.ready, checks=checks)


def _orchestrator_with_preflight(market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo, preflight):
    dataset_registry = DatasetRegistryService(datasets=dataset_repo)
    return ScheduledRetrainingOrchestrator(
        markets=market_repo,
        models=model_repo,
        scheduler=RetrainingScheduler(dataset_registry=dataset_registry),
        dataset_builder=DatasetBuilder(markets=market_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo),
        dataset_registry=dataset_registry,
        model_selection=AutomaticModelSelectionService(
            training_pipeline=TrainingPipelineService(),
            model_registry=ModelRegistryService(models=model_repo),
            experiments=ExperimentTrackingService(experiments=_ExperimentRepoFake()),
            artifact_store=_InMemoryArtifactStore(),
        ),
        preflight=preflight,
    )


class TestScheduledRetrainingOrchestratorPreflight:
    async def test_failing_preflight_skips_training_without_calling_model_selection(
        self, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        await _seed_champion(model_repo, market)
        await dataset_repo.upsert(_stale_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=MIN_TRAINING_POOL_AFTER_HOLDOUT + 20)
        orchestrator = _orchestrator_with_preflight(
            market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo, _FakePreflight(ready=False)
        )

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.challenger is None
        assert result.skipped_reason is not None
        assert "preflight failed" in result.skipped_reason
        assert "sufficient_labeled_observations" in result.skipped_reason

    async def test_passing_preflight_lets_training_proceed(
        self, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        await _seed_champion(model_repo, market)
        await dataset_repo.upsert(_stale_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=MIN_TRAINING_POOL_AFTER_HOLDOUT + 20)
        orchestrator = _orchestrator_with_preflight(
            market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo, _FakePreflight(ready=True)
        )

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        assert outcomes[0].challenger is not None
        assert outcomes[0].skipped_reason is None

    async def test_preflight_not_wired_defaults_to_none_and_skips_the_check(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        """The plain `orchestrator` fixture never sets `preflight` — confirms the field truly
        defaults to `None` and every existing caller is unaffected by this addition."""
        market = await market_repo.upsert(_market())
        await _seed_champion(model_repo, market)
        await dataset_repo.upsert(_stale_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=MIN_TRAINING_POOL_AFTER_HOLDOUT + 20)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert outcomes[0].challenger is not None


class TestScheduledRetrainingOrchestrator:
    async def test_stale_market_with_enough_real_outcomes_produces_a_registered_challenger(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        await _seed_champion(model_repo, market)
        await dataset_repo.upsert(_stale_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.market_key == market.market_key
        assert result.should_retrain is True
        assert result.reason == "dataset stale"
        assert result.skipped_reason is None
        assert result.challenger is not None
        assert result.challenger.status is ModelStatus.CHALLENGER
        assert result.bootstrapped is False  # a live CHAMPION already existed — never auto-promoted

        persisted = await model_repo.get(result.challenger.id)
        assert persisted.status is ModelStatus.CHALLENGER

        # A new dataset version was built, validated, and system-approved — never a human gate
        # bypass, since approval is auditable via SYSTEM_APPROVER, not silently skipped.
        latest_dataset = await dataset_repo.get_latest_version(market.id)
        assert latest_dataset.version == 2
        assert latest_dataset.status is DatasetStatus.APPROVED
        assert latest_dataset.approved_by == SYSTEM_APPROVER

    async def test_fresh_market_with_no_drift_is_left_alone(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        await _seed_champion(model_repo, market)
        await dataset_repo.upsert(_fresh_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        assert outcomes[0].should_retrain is False
        assert outcomes[0].challenger is None
        # No new dataset version was built — the sweep genuinely skipped this market.
        latest_dataset = await dataset_repo.get_latest_version(market.id)
        assert latest_dataset.version == 1

    async def test_stale_market_with_too_few_real_outcomes_is_skipped_not_fabricated(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        await _seed_champion(model_repo, market)
        await dataset_repo.upsert(_stale_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=10)  # below MIN_TRAINING_SAMPLES

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.should_retrain is True
        assert result.challenger is None
        assert result.skipped_reason is not None
        assert "too_few_samples" in result.skipped_reason.lower() or "few" in result.skipped_reason.lower()

    async def test_one_markets_failure_does_not_block_the_rest_of_the_sweep(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        broken_market = await market_repo.upsert(_market(market_key="football.unmapped_market"))
        healthy_market = await market_repo.upsert(_market(market_key="football.both_teams_to_score"))
        await _seed_champion(model_repo, broken_market)
        await _seed_champion(model_repo, healthy_market)
        await dataset_repo.upsert(_stale_dataset(broken_market.id, T0))
        await dataset_repo.upsert(_stale_dataset(healthy_market.id, T0))
        # No outcome_label_mapper entry for "football.unmapped_market" -> every outcome is
        # unresolvable -> DatasetBuilder yields zero samples -> TOO_FEW_SAMPLES, not a crash.
        await _seed_outcomes(broken_market, prediction_repo, prediction_outcome_repo, n=60)
        await _seed_outcomes(healthy_market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        by_key = {o.market_key: o for o in outcomes}
        assert len(outcomes) == 2
        assert by_key["football.unmapped_market"].challenger is None
        assert by_key["football.unmapped_market"].skipped_reason is not None
        assert by_key["football.both_teams_to_score"].challenger is not None

    # -- Bootstrap: a market with no CHAMPION at all (ML-architecture consolidation, 2026-08-04) --

    async def test_market_with_no_champion_bootstraps_straight_to_champion(
        self, orchestrator, market_repo, model_repo, prediction_repo, prediction_outcome_repo
    ):
        """The "insufficient historical data" state (see `scripts/seed_football_markets.py`'s
        `NOT_YET_TRAINED_MARKET_KEYS`) — no CHAMPION, no dataset built yet. Real accumulated
        outcomes are enough to train on -> the first Challenger is auto-promoted to CHAMPION,
        the one exception to this orchestrator's human promotion gate."""
        market = await market_repo.upsert(_market())
        assert await model_repo.get_champion(market.id) is None
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.should_retrain is True
        assert result.reason == "never trained"
        assert result.skipped_reason is None
        assert result.challenger is not None
        assert result.bootstrapped is True

        persisted = await model_repo.get(result.challenger.id)
        assert persisted.status is ModelStatus.CHAMPION
        assert await model_repo.get_champion(market.id) == persisted

    async def test_market_with_no_champion_and_too_few_outcomes_is_skipped_not_promoted(
        self, orchestrator, market_repo, model_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=10)  # below MIN_TRAINING_SAMPLES

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.reason == "never trained"
        assert result.challenger is None
        assert result.bootstrapped is False
        assert result.skipped_reason is not None
        assert await model_repo.get_champion(market.id) is None  # still genuinely untrained, nothing fabricated

    async def test_market_with_no_champion_ignores_the_staleness_gate(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        """A never-trained market always gets a bootstrap attempt, even with a "fresh" dataset
        already on file (from, say, a prior failed bootstrap run) — should_retrain()'s
        staleness/drift check has no live CHAMPION to compare against and would otherwise report
        "nothing to do" forever."""
        market = await market_repo.upsert(_market())
        await dataset_repo.upsert(_fresh_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.should_retrain is True
        assert result.bootstrapped is True
        assert await model_repo.get_champion(market.id) is not None


# -- Statistical-baseline charter: live Poisson candidate wiring (Gemini Reasoning Engine) ------


class TestPoissonEligibleMarketWiring:
    """`POISSON_ELIGIBLE_MARKETS` is the single source of truth both this orchestrator and
    `StatisticalBaselineProvider` read — a typo in `market_shape`/`line`/`team` here would
    silently mistrain or silently break live baseline lookups, so its exact contents are
    verified directly rather than only indirectly through a full training run."""

    def test_covers_exactly_the_twelve_documented_markets(self):
        assert set(POISSON_ELIGIBLE_MARKETS.keys()) == {
            "football.total_goals_over_under",
            "football.total_goals_over_under_0_5",
            "football.total_goals_over_under_1_5",
            "football.total_goals_over_under_3_5",
            "football.total_goals_over_under_4_5",
            "football.home_team_total_goals",
            "football.away_team_total_goals",
            "football.correct_score",
            "football.home_clean_sheet",
            "football.away_clean_sheet",
            "football.home_win_to_nil",
            "football.away_win_to_nil",
        }

    def test_every_entry_uses_the_poisson_goals_framework_and_is_marked_baseline(self):
        for spec in POISSON_ELIGIBLE_MARKETS.values():
            assert spec.framework is MLFramework.POISSON_GOALS
            assert spec.algorithm is MLAlgorithm.POISSON_GOALS_MODEL
            assert spec.is_baseline is True

    def test_total_threshold_markets_carry_the_correct_line(self):
        expected_lines = {
            "football.total_goals_over_under": 2.5,
            "football.total_goals_over_under_0_5": 0.5,
            "football.total_goals_over_under_1_5": 1.5,
            "football.total_goals_over_under_3_5": 3.5,
            "football.total_goals_over_under_4_5": 4.5,
        }
        for market_key, line in expected_lines.items():
            spec = POISSON_ELIGIBLE_MARKETS[market_key]
            assert spec.params["market_shape"] == "total_threshold"
            assert spec.params["line"] == line

    def test_team_scoped_markets_carry_the_correct_team(self):
        expected_team = {
            "football.home_team_total_goals": "home",
            "football.away_team_total_goals": "away",
            "football.home_clean_sheet": "home",
            "football.away_clean_sheet": "away",
            "football.home_win_to_nil": "home",
            "football.away_win_to_nil": "away",
        }
        for market_key, team in expected_team.items():
            assert POISSON_ELIGIBLE_MARKETS[market_key].params["team"] == team

    def test_correct_score_has_no_line_or_team(self):
        spec = POISSON_ELIGIBLE_MARKETS["football.correct_score"]
        assert spec.params["market_shape"] == "correct_score"
        assert "line" not in spec.params
        assert "team" not in spec.params

    async def test_eligible_market_bootstrap_does_not_error_when_candidates_left_default(
        self, orchestrator, market_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        """The real regression risk of this wiring: does injecting a 12th candidate into a
        market's roster (when `candidates=None`) break the sweep? A market outside
        `POISSON_ELIGIBLE_MARKETS` (`football.both_teams_to_score`, exercised by every
        pre-existing test above) already proves the unaffected path; this proves the affected
        path completes without raising for a genuinely eligible market."""
        market = await market_repo.upsert(_market(market_key="football.total_goals_over_under"))
        await dataset_repo.upsert(_fresh_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0)  # candidates=None -> real default + Poisson injection

        assert len(outcomes) == 1
        assert outcomes[0].skipped_reason is None


class TestDixonColesEligibleMarketWiring:
    """Correct Score forensic audit (2026-08-27) — `DIXON_COLES_ELIGIBLE_MARKETS` layers a second
    Poisson-family candidate onto `football.correct_score` specifically, additive to
    `POISSON_ELIGIBLE_MARKETS`'s own injection. Verified the same way that injection already is:
    exact contents first, then a real end-to-end sweep proving the 13-candidate roster (11 default
    + plain Poisson + Dixon-Coles) doesn't break anything."""

    def test_covers_exactly_correct_score(self):
        assert set(DIXON_COLES_ELIGIBLE_MARKETS.keys()) == {"football.correct_score"}

    def test_entry_is_a_distinct_algorithm_on_the_same_framework_marked_baseline(self):
        spec = DIXON_COLES_ELIGIBLE_MARKETS["football.correct_score"]
        assert spec.framework is MLFramework.POISSON_GOALS
        assert spec.algorithm is MLAlgorithm.POISSON_DIXON_COLES_MODEL
        assert spec.algorithm is not MLAlgorithm.POISSON_GOALS_MODEL  # never conflated with the plain baseline
        assert spec.is_baseline is True

    def test_entry_enables_dixon_coles_on_the_correct_score_shape(self):
        spec = DIXON_COLES_ELIGIBLE_MARKETS["football.correct_score"]
        assert spec.params["market_shape"] == "correct_score"
        assert spec.params["dixon_coles"] is True

    async def test_correct_score_bootstrap_does_not_error_with_both_poisson_candidates_injected(
        self, orchestrator, market_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        """The real regression risk: does injecting a 13th candidate (on top of the 12th the plain
        Poisson injection already adds) break the sweep for the one market that gets both? Real
        correct-score labels + raw goal counts are seeded (unlike `_seed_outcomes`'s generic BTTS
        labels) so this market's own multiclass label recovery actually produces usable samples —
        `football.correct_score` has >2 `MARKET_OUTCOME_CATALOG` outcomes, so `DatasetBuilder`
        recovers labels from `actual_value` directly, not from a binary polarity mapping."""
        market = await market_repo.upsert(_market(market_key="football.correct_score"))
        await dataset_repo.upsert(_fresh_dataset(market.id, T0))
        labels_cycle = [("1-0", 1, 0), ("0-0", 0, 0), ("2-1", 2, 1), ("1-1", 1, 1), ("0-1", 0, 1)]
        for i in range(60):
            actual_label, home_goals, away_goals = labels_cycle[i % len(labels_cycle)]
            prediction = Prediction(
                id=PredictionId(uuid4()), market_id=market.id, model_id=ModelId(uuid4()), subject_ref=f"fx-{i}",
                value=actual_label, probability=0.2, confidence=CONFIDENCE, explanation=ExplanationBundle(),
                feature_snapshot={"feature_a": float(i % 20), "feature_b": float((i * 3) % 17)},
                model_version="1", status=PredictionStatus.PUBLISHED, generated_at=T0,
            )
            await prediction_repo.record(prediction)
            await prediction_outcome_repo.record(
                PredictionOutcome(
                    id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
                    actual_value=actual_label, error=0.0, evaluated_at=T0,
                    raw_home_goals=home_goals, raw_away_goals=away_goals,
                )
            )

        outcomes = await orchestrator.run(T0)  # candidates=None -> real default + both Poisson candidates

        assert len(outcomes) == 1
        assert outcomes[0].skipped_reason is None


class TestNegativeBinomialEligibleMarketWiring:
    """Forensic audit finding #7 (2026-08-30) — `NEGATIVE_BINOMIAL_ELIGIBLE_MARKETS` layers a
    third Poisson-family candidate onto every market `POISSON_ELIGIBLE_MARKETS` covers, additive
    to that injection (and to `DIXON_COLES_ELIGIBLE_MARKETS`'s own, on `correct_score`)."""

    def test_covers_exactly_the_same_twelve_markets_as_the_plain_poisson_candidate(self):
        assert set(NEGATIVE_BINOMIAL_ELIGIBLE_MARKETS.keys()) == set(POISSON_ELIGIBLE_MARKETS.keys())

    def test_every_entry_is_a_distinct_algorithm_on_the_same_framework_marked_baseline(self):
        for market_key, spec in NEGATIVE_BINOMIAL_ELIGIBLE_MARKETS.items():
            assert spec.framework is MLFramework.POISSON_GOALS
            assert spec.algorithm is MLAlgorithm.NEGATIVE_BINOMIAL_GOALS_MODEL
            assert spec.algorithm is not MLAlgorithm.POISSON_GOALS_MODEL  # never conflated with the plain baseline
            assert spec.is_baseline is True

    def test_every_entry_carries_the_same_market_shape_line_and_team_as_the_plain_candidate(self):
        """Derived from POISSON_ELIGIBLE_MARKETS' own params rather than hand-copied — this is the
        regression test for that: a market_shape/line/team edit to the plain candidate must reach
        this one automatically, never silently drift apart."""
        for market_key, poisson_spec in POISSON_ELIGIBLE_MARKETS.items():
            nb_spec = NEGATIVE_BINOMIAL_ELIGIBLE_MARKETS[market_key]
            assert nb_spec.params["market_shape"] == poisson_spec.params["market_shape"]
            assert nb_spec.params.get("line") == poisson_spec.params.get("line")
            assert nb_spec.params.get("team") == poisson_spec.params.get("team")

    def test_every_entry_enables_negative_binomial(self):
        for spec in NEGATIVE_BINOMIAL_ELIGIBLE_MARKETS.values():
            assert spec.params["negative_binomial"] is True

    async def test_correct_score_bootstrap_does_not_error_with_all_three_poisson_candidates_injected(
        self, orchestrator, market_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        """The real regression risk: does injecting a 14th candidate (plain Poisson + Dixon-Coles
        + Negative-Binomial, on top of the 11 default) break the sweep for the one market that
        gets all three?"""
        market = await market_repo.upsert(_market(market_key="football.correct_score"))
        await dataset_repo.upsert(_fresh_dataset(market.id, T0))
        labels_cycle = [("1-0", 1, 0), ("0-0", 0, 0), ("2-1", 2, 1), ("1-1", 1, 1), ("0-1", 0, 1)]
        for i in range(60):
            actual_label, home_goals, away_goals = labels_cycle[i % len(labels_cycle)]
            prediction = Prediction(
                id=PredictionId(uuid4()), market_id=market.id, model_id=ModelId(uuid4()), subject_ref=f"fx-{i}",
                value=actual_label, probability=0.2, confidence=CONFIDENCE, explanation=ExplanationBundle(),
                feature_snapshot={"feature_a": float(i % 20), "feature_b": float((i * 3) % 17)},
                model_version="1", status=PredictionStatus.PUBLISHED, generated_at=T0,
            )
            await prediction_repo.record(prediction)
            await prediction_outcome_repo.record(
                PredictionOutcome(
                    id=PredictionOutcomeId(uuid4()), prediction_id=prediction.id,
                    actual_value=actual_label, error=0.0, evaluated_at=T0,
                    raw_home_goals=home_goals, raw_away_goals=away_goals,
                )
            )

        outcomes = await orchestrator.run(T0)  # candidates=None -> real default + all three Poisson-family candidates

        assert len(outcomes) == 1
        assert outcomes[0].skipped_reason is None

    async def test_a_total_threshold_market_bootstraps_with_plain_and_negative_binomial_candidates(
        self, orchestrator, market_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        """Unlike Dixon-Coles (scoped to correct_score only), Negative-Binomial is injected for
        every POISSON_ELIGIBLE_MARKETS entry — covered here with a market shape Dixon-Coles never
        touches, to prove the injection genuinely reaches markets beyond correct_score."""
        market = await market_repo.upsert(_market(market_key="football.total_goals_over_under"))
        await dataset_repo.upsert(_fresh_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcomes = await orchestrator.run(T0)

        assert len(outcomes) == 1
        assert outcomes[0].skipped_reason is None


# -- Continuous Outcome Learning Engine: Challenger-vs-Champion comparison (2026-08-08) ---------


class TestChallengerVsChampionComparison:
    async def test_non_bootstrap_retrain_with_real_champion_runs_comparison_and_records_a_verdict(
        self, orchestrator_with_comparison, market_repo, model_repo, prediction_repo, prediction_outcome_repo, comparison_repo
    ):
        market = await market_repo.upsert(_market())
        assert await model_repo.get_champion(market.id) is None
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        # Bootstrap a real, artifact-backed CHAMPION first — the scenario every non-bootstrap
        # comparison assumes (a Champion this orchestrator itself already trained and promoted).
        bootstrap_outcomes = await orchestrator_with_comparison.run(T0, candidates=FAST_CANDIDATES)
        assert bootstrap_outcomes[0].bootstrapped is True
        champion = await model_repo.get_champion(market.id)
        assert champion is not None
        assert champion.artifact_ref is not None

        # New outcomes the bootstrap Champion never saw, plus enough total samples to clear
        # MIN_TRAINING_POOL_AFTER_HOLDOUT after carving a comparison holdout — and advance past
        # the 7-day staleness window so should_retrain() actually fires a second time.
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=MIN_TRAINING_POOL_AFTER_HOLDOUT + 20)
        later = T0 + timedelta(days=8)

        outcomes = await orchestrator_with_comparison.run(later, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.bootstrapped is False  # a live CHAMPION already existed
        assert result.challenger is not None
        assert result.comparison is not None
        assert result.comparison.verdict in (
            ComparisonVerdict.CHALLENGER_BETTER, ComparisonVerdict.CHAMPION_BETTER, ComparisonVerdict.INCONCLUSIVE,
        )
        assert result.comparison.champion_model_id == champion.id
        assert result.comparison.challenger_model_id == result.challenger.id
        assert result.comparison.holdout_sample_count > 0

        recorded = await comparison_repo.get_latest(market.id)
        assert recorded == result.comparison

        # A CHAMPION_BETTER verdict must have already retired the losing Challenger; anything
        # else must have left it exactly as registered (still eligible for human promotion).
        persisted_challenger = await model_repo.get(result.challenger.id)
        if result.comparison.verdict is ComparisonVerdict.CHAMPION_BETTER:
            assert persisted_challenger.status is ModelStatus.RETIRED
        else:
            assert persisted_challenger.status is ModelStatus.CHALLENGER

        # Either way, the original Champion is untouched — this comparison never auto-promotes.
        assert await model_repo.get_champion(market.id) == champion

    async def test_dataset_too_small_for_a_safe_holdout_skips_comparison_but_still_retrains(
        self, orchestrator_with_comparison, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        market = await market_repo.upsert(_market())
        await _seed_champion(model_repo, market)
        await dataset_repo.upsert(_stale_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=50)  # too few to clear the holdout margin

        outcomes = await orchestrator_with_comparison.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        result = outcomes[0]
        assert result.challenger is not None
        assert result.comparison is None

    async def test_comparison_pieces_not_wired_leaves_prior_behavior_unchanged(
        self, orchestrator, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo
    ):
        """The plain `orchestrator` fixture (no `model_loader`/`evaluator`/`comparisons`) must
        keep behaving exactly like before this feature existed — `comparison` stays `None`
        unconditionally, never raises for being unwired."""
        market = await market_repo.upsert(_market())
        await _seed_champion(model_repo, market)
        await dataset_repo.upsert(_stale_dataset(market.id, T0))
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=MIN_TRAINING_POOL_AFTER_HOLDOUT + 20)

        outcomes = await orchestrator.run(T0, candidates=FAST_CANDIDATES)

        assert len(outcomes) == 1
        assert outcomes[0].challenger is not None
        assert outcomes[0].comparison is None


class TestRepairBrokenChampion:
    """Real production incident, 2026-08-29: 40 of 53 PRODUCTION markets' registered CHAMPIONs
    pointed at artifacts that were never actually durable — GET /api/v1/admin/system/model-health
    catalogues exactly this. `repair_broken_champion` is the fix: retire the unusable row (if any)
    and force a real bootstrap-style retrain+promote, with an independent post-registration reload
    check standing in for the promotion-time artifact-integrity check `promote_to_champion`'s own
    docstring flags as not yet enforced."""

    async def test_repairs_a_champion_whose_artifact_is_missing_from_the_store(
        self, orchestrator_with_comparison, market_repo, model_repo, prediction_repo, prediction_outcome_repo,
    ):
        market = await market_repo.upsert(_market())
        broken = ModelDefinition(
            id=ModelId(uuid4()), market_id=market.id, model_key=f"{market.market_key}.svm",
            version=1, algorithm="svm", framework="sklearn", status=ModelStatus.CHAMPION,
            artifact_ref="nowhere/v1.bin",  # never actually written to the artifact store
        )
        await model_repo.upsert(broken)
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcome = await orchestrator_with_comparison.repair_broken_champion(market, T0, candidates=FAST_CANDIDATES)

        assert outcome.skipped_reason is None
        assert outcome.bootstrapped is True
        assert outcome.challenger is not None

        new_champion = await model_repo.get_champion(market.id)
        assert new_champion is not None
        assert new_champion.id == outcome.challenger.id
        assert new_champion.artifact_ref is not None
        assert new_champion.approved_by == "model-artifact-repair"

        old = await model_repo.get(broken.id)
        assert old.status is ModelStatus.RETIRED

    async def test_repairs_a_market_with_no_champion_at_all(
        self, orchestrator_with_comparison, market_repo, model_repo, prediction_repo, prediction_outcome_repo,
    ):
        market = await market_repo.upsert(_market())
        assert await model_repo.get_champion(market.id) is None
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        outcome = await orchestrator_with_comparison.repair_broken_champion(market, T0, candidates=FAST_CANDIDATES)

        assert outcome.bootstrapped is True
        champion = await model_repo.get_champion(market.id)
        assert champion is not None
        assert champion.id == outcome.challenger.id

    async def test_preflight_failure_blocks_repair(
        self, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo, artifact_store,
    ):
        market = await market_repo.upsert(_market())
        broken = ModelDefinition(
            id=ModelId(uuid4()), market_id=market.id, model_key=f"{market.market_key}.svm",
            version=1, algorithm="svm", framework="sklearn", status=ModelStatus.CHAMPION,
            artifact_ref="nowhere/v1.bin",
        )
        await model_repo.upsert(broken)
        dataset_registry = DatasetRegistryService(datasets=dataset_repo)
        orchestrator = ScheduledRetrainingOrchestrator(
            markets=market_repo, models=model_repo,
            scheduler=RetrainingScheduler(dataset_registry=dataset_registry),
            dataset_builder=DatasetBuilder(markets=market_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo),
            dataset_registry=dataset_registry,
            model_selection=AutomaticModelSelectionService(
                training_pipeline=TrainingPipelineService(),
                model_registry=ModelRegistryService(models=model_repo),
                experiments=ExperimentTrackingService(experiments=_ExperimentRepoFake()),
                artifact_store=artifact_store,
            ),
            preflight=_FakePreflight(ready=False),
        )

        outcome = await orchestrator.repair_broken_champion(market, T0, candidates=FAST_CANDIDATES)

        assert outcome.skipped_reason is not None
        assert "preflight failed" in outcome.skipped_reason
        # Never touched — a blocked repair must never retire the (still broken, but at least
        # present) existing row.
        untouched = await model_repo.get(broken.id)
        assert untouched.status is ModelStatus.CHAMPION

    async def test_artifact_that_fails_to_reload_after_registration_is_never_promoted(
        self, market_repo, model_repo, dataset_repo, prediction_repo, prediction_outcome_repo,
    ):
        """A save() that reports success is not proof of durability — the whole reason this
        method exists is a real incident where exactly that assumption was wrong. A store whose
        load() fails right after its own save() succeeded must leave the broken Champion retired
        (repair attempted) but never promote the new, equally-unloadable Challenger."""

        @dataclass
        class _WriteOnlyArtifactStore:
            async def save(self, key: str, payload: bytes) -> str:
                return key

            async def load(self, ref: str) -> bytes:
                raise FileNotFoundError(f"never actually durable: {ref}")

        market = await market_repo.upsert(_market())
        broken = ModelDefinition(
            id=ModelId(uuid4()), market_id=market.id, model_key=f"{market.market_key}.svm",
            version=1, algorithm="svm", framework="sklearn", status=ModelStatus.CHAMPION,
            artifact_ref="nowhere/v1.bin",
        )
        await model_repo.upsert(broken)
        await _seed_outcomes(market, prediction_repo, prediction_outcome_repo, n=60)

        write_only_store = _WriteOnlyArtifactStore()
        dataset_registry = DatasetRegistryService(datasets=dataset_repo)
        orchestrator = ScheduledRetrainingOrchestrator(
            markets=market_repo, models=model_repo,
            scheduler=RetrainingScheduler(dataset_registry=dataset_registry),
            dataset_builder=DatasetBuilder(markets=market_repo, predictions=prediction_repo, outcomes=prediction_outcome_repo),
            dataset_registry=dataset_registry,
            model_selection=AutomaticModelSelectionService(
                training_pipeline=TrainingPipelineService(),
                model_registry=ModelRegistryService(models=model_repo),
                experiments=ExperimentTrackingService(experiments=_ExperimentRepoFake()),
                artifact_store=write_only_store,
            ),
            model_loader=ModelLoaderService(artifact_store=write_only_store),
        )

        outcome = await orchestrator.repair_broken_champion(market, T0, candidates=FAST_CANDIDATES)

        assert outcome.skipped_reason is not None
        assert "not promoted" in outcome.skipped_reason
        # The broken row must still be exactly as it was — never retired for a repair that itself
        # couldn't produce a genuinely loadable replacement.
        still_broken = await model_repo.get(broken.id)
        assert still_broken.status is ModelStatus.CHAMPION
        assert await model_repo.get_champion(market.id) == still_broken
