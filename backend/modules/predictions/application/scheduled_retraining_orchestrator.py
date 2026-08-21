"""Scheduled Retraining Orchestrator.

Audit finding (2026-08-02): `RetrainingScheduler.should_retrain()` (drift-triggered +
staleness-triggered decision logic, `training_pipeline_service.py`) and
`AutomaticModelSelectionService` (trains 11 real algorithms against a dataset, ranks by held-out
metric, registers the winner as Candidate -> Challenger, `model_selection_service.py`) are both
real and already composed in `apps/api/composition.py` — but nothing ever called them together,
and nothing called either one automatically. A manual "check retraining" button existed in the
Ops Center; Celery's beat schedule had zero periodic retraining task. This orchestrator is that
missing loop, meant to be run periodically (`scheduled_retraining_tasks.py`): for every PRODUCTION
market, ask `RetrainingScheduler` whether it needs retraining; if so, build a fresh `Dataset` and
run Automatic Model Selection against it.

Two deliberate, honest stopping points, matching gates the codebase already enforces elsewhere:

- Dataset validate()/approve() here uses a named system approver (not a human), gated only on the
  same objective `quality_issues` check `DatasetRegistryService.validate()` already performs
  (`DatasetHasQualityIssuesError` on too few samples) — this is a mechanical quality gate, not a
  judgment call, so an automated approver is honest here in a way it wouldn't be for a market's
  or model's lifecycle (which the codebase deliberately keeps human-gated, see below).
- Model promotion stops at CHALLENGER for a market that already has a live CHAMPION.
  `ModelRegistryService.promote_to_champion` already requires a human `approved_by` — replacing an
  already-serving model is never automatic here. "Automatic deployment only if metrics improve" is
  satisfied by ranking on real held-out metrics inside `AutomaticModelSelectionService`; "never
  automatically replace a production model without validation" is satisfied by leaving that
  replacement exactly where the existing Ops Center "Promote to champion" action already puts it
  — in a human's hands.

ML-architecture consolidation (2026-08-04), one narrow exception to the human-gate above:
bootstrapping a market that has never had a CHAMPION at all (the "insufficient historical data"
state — see `scripts/seed_football_markets.py`'s `NOT_YET_TRAINED_MARKET_KEYS`) is not "replacing
a production model" — there is no production model yet, only an honest gap. For that one case,
the first Challenger this orchestrator successfully trains and validates on real held-out metrics
is auto-promoted straight to CHAMPION — the "scheduled training registers the first production
model" self-learning loop, turning "insufficient historical data" into a real served prediction
the moment enough verified completed matches exist. A market that already has a live CHAMPION
never goes through this branch; its retraining stays exactly as human-gated as before.
`RetrainingScheduler.should_retrain()` is also bypassed for a never-trained market — its
staleness/drift check compares against a prior dataset that doesn't exist yet, so it would
otherwise report "nothing to do" forever; a market with no CHAMPION always gets a bootstrap
attempt on every sweep until one succeeds.

One market's failure (bad dataset, training error) is captured per-market and never blocks the
sweep from checking every other market — a scheduled sweep that silently stops at the first
problem market would starve every market after it in the iteration order.

Continuous Outcome Learning Engine (2026-08-08): the non-bootstrap branch (a market that already
has a live CHAMPION) now also runs `ChallengerEvaluationService` — the "Compare Against Current
Production Model" half of the spec this orchestrator's earlier version was missing entirely. A
chronological holdout is carved off the freshly-built dataset BEFORE the Challenger ever trains on
it (`_comparison_holdout`), so the comparison never scores the Challenger on samples it already
saw; the Champion, trained on an older dataset build, was never at risk of that either way. Both
models are scored on the identical holdout via the same log-loss/Brier/calibration priority order
`AutomaticModelSelectionService` now ranks its own candidate roster by. A CHAMPION_BETTER verdict
auto-`retire()`s the losing Challenger (touches no production traffic — safe to automate); a
CHALLENGER_BETTER verdict leaves the Challenger exactly as before, still requiring the same human
`promote_to_champion` call, but with the comparison recorded so that decision is "confirm" rather
than "re-derive by hand." Too few samples to carve a safe holdout (`_comparison_holdout` returning
`None`) falls back to the pre-existing behavior unchanged: Challenger registered, no verdict, no
auto-retire — an honest "not enough data to compare yet," never a fabricated one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from modules.predictions.application.challenger_evaluation_service import ChallengerEvaluationService
from modules.predictions.application.dataset_builder_service import DatasetBuilder
from modules.predictions.application.dataset_registry_service import DatasetHasQualityIssuesError, DatasetRegistryService
from modules.predictions.application.model_selection_service import (
    DEFAULT_CLASSIFICATION_CANDIDATES,
    AutomaticModelSelectionService,
)
from modules.predictions.application.training_pipeline_service import RetrainingScheduler
from modules.predictions.application.training_preflight_service import TrainingPreflightService
from modules.predictions.domain.dataset import Dataset
from modules.predictions.domain.entities import MarketDefinition, ModelDefinition
from modules.predictions.domain.ml_value_objects import MLAlgorithm, MLFramework
from modules.predictions.domain.model_comparison import ChallengerEvaluation, ComparisonVerdict
from modules.predictions.domain.model_selection import CandidateSpec
from modules.predictions.domain.value_objects import MarketStatus
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.ports.ml_model import TrainingSample
from modules.predictions.ports.repositories import MarketRepositoryPort, ModelComparisonRepositoryPort, ModelRepositoryPort

SYSTEM_APPROVER = "scheduled-retraining"

# Statistical-baseline charter, live wiring — a real, empirically-benchmarked
# `FootballGoalsPoissonAdapter` candidate for each of the 12 football goals/score markets it
# supports (see the adapter's own module docstring for the 5 `market_shape`s). Additive only:
# consulted below in `_check_and_retrain` solely when the caller leaves `candidates=None` (the
# normal sweep path), so an explicit operator/test override of the roster is never silently
# augmented, and every market outside this mapping is completely unaffected.
POISSON_ELIGIBLE_MARKETS: dict[str, CandidateSpec] = {
    "football.total_goals_over_under": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "total_threshold", "line": 2.5}, is_baseline=True,
    ),
    "football.total_goals_over_under_0_5": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "total_threshold", "line": 0.5}, is_baseline=True,
    ),
    "football.total_goals_over_under_1_5": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "total_threshold", "line": 1.5}, is_baseline=True,
    ),
    "football.total_goals_over_under_3_5": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "total_threshold", "line": 3.5}, is_baseline=True,
    ),
    "football.total_goals_over_under_4_5": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "total_threshold", "line": 4.5}, is_baseline=True,
    ),
    "football.home_team_total_goals": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "team_total_threshold", "line": 1.5, "team": "home"}, is_baseline=True,
    ),
    "football.away_team_total_goals": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "team_total_threshold", "line": 1.5, "team": "away"}, is_baseline=True,
    ),
    "football.correct_score": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "correct_score"}, is_baseline=True,
    ),
    "football.home_clean_sheet": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "clean_sheet", "team": "home"}, is_baseline=True,
    ),
    "football.away_clean_sheet": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "clean_sheet", "team": "away"}, is_baseline=True,
    ),
    "football.home_win_to_nil": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "win_to_nil", "team": "home"}, is_baseline=True,
    ),
    "football.away_win_to_nil": CandidateSpec(
        MLAlgorithm.POISSON_GOALS_MODEL, MLFramework.POISSON_GOALS,
        params={"market_shape": "win_to_nil", "team": "away"}, is_baseline=True,
    ),
}

# A comparison holdout is only carved off when doing so still leaves the Challenger's own training
# comfortably above `MIN_TRAINING_SAMPLES` (30) after `TrainingPipelineService`'s own internal
# 80/20 split — 45 remaining samples clears that with real margin. Below this, skip the comparison
# entirely rather than starve the Challenger's training to run a nearly-meaningless comparison.
MIN_TRAINING_POOL_AFTER_HOLDOUT = 45
COMPARISON_HOLDOUT_RATIO = 0.15
MIN_COMPARISON_HOLDOUT_SAMPLES = 10


def _comparison_holdout(dataset: Dataset) -> tuple[list[TrainingSample], list[TrainingSample]] | None:
    """Splits `dataset.samples` into (training_pool, holdout) for a Challenger-vs-Champion
    comparison. `PredictionOutcomeRepositoryPort.list_by_market` (what `DatasetBuilder` sources
    from) orders by `evaluated_at.desc()` — newest first — so the *head* of `dataset.samples` is
    the most recent history, not the tail; this takes that head as the holdout (never seen by
    training) and the older tail as the pool the Challenger actually trains on. Returns `None` when
    the dataset isn't large enough to spare a holdout without starving the Challenger's own fit."""
    samples = dataset.samples
    holdout_count = max(MIN_COMPARISON_HOLDOUT_SAMPLES, int(len(samples) * COMPARISON_HOLDOUT_RATIO))
    training_pool = samples[holdout_count:]
    if len(training_pool) < MIN_TRAINING_POOL_AFTER_HOLDOUT:
        return None
    return list(training_pool), list(samples[:holdout_count])


@dataclass(frozen=True)
class RetrainingOutcome:
    market_key: str
    should_retrain: bool
    reason: str | None = None
    challenger: ModelDefinition | None = None
    skipped_reason: str | None = None
    bootstrapped: bool = False
    """True when this run auto-promoted `challenger` straight to CHAMPION because the market had
    never had one before — the one case this orchestrator skips the human Champion-promotion
    gate (see module docstring)."""
    comparison: ChallengerEvaluation | None = None
    """Set only for a non-bootstrap retrain that had enough samples to carve a comparison holdout
    (see `_comparison_holdout`) — `None` for a bootstrap run (nothing to compare against yet) or a
    market whose dataset was too small to spare one."""


@dataclass
class ScheduledRetrainingOrchestrator:
    markets: MarketRepositoryPort
    models: ModelRepositoryPort
    scheduler: RetrainingScheduler
    dataset_builder: DatasetBuilder
    dataset_registry: DatasetRegistryService
    model_selection: AutomaticModelSelectionService
    model_loader: ModelLoaderService | None = None
    evaluator: ChallengerEvaluationService | None = None
    comparisons: ModelComparisonRepositoryPort | None = None
    """`model_loader`/`evaluator`/`comparisons` are optional (default `None`) so existing callers
    that construct this orchestrator without them keep working unchanged — the Continuous Outcome
    Learning Engine's comparison step is simply skipped (same as an insufficient-holdout market)
    when any of the three isn't wired, rather than raising."""
    preflight: TrainingPreflightService | None = None
    """Phase 3 audit fix — `TrainingPreflightService` existed since Milestone 19 but nothing ever
    called it. Optional for the same backward-compatibility reason as the three fields above: when
    wired, a market failing preflight (missing feature manifest, leakage-unsafe intelligence
    feature, insufficient labeled observations, etc.) is skipped with the blocking checks recorded
    in `skipped_reason`, never trained on data that already failed a documented gate."""

    async def run(self, now: datetime, candidates=None) -> list[RetrainingOutcome]:
        """Checks, and retrains where warranted, every PRODUCTION market — the periodic sweep a
        Celery beat task calls. ``candidates`` forwards to `AutomaticModelSelectionService`
        (None -> its own real default 11-algorithm roster); exposed here for the same reason it's
        exposed there — an operator restricting the roster for a specific run, or a test keeping
        one fast."""
        outcomes = []
        for market in await self.markets.list_by_status(MarketStatus.PRODUCTION):
            outcomes.append(await self._check_and_retrain(market, now, candidates))
        return outcomes

    async def _check_and_retrain(self, market: MarketDefinition, now: datetime, candidates=None) -> RetrainingOutcome:
        champion = await self.models.get_champion(market.id)
        is_bootstrap = champion is None

        if is_bootstrap:
            # No CHAMPION exists yet — should_retrain()'s staleness/drift check has no prior
            # dataset to compare against and would report "nothing to do" forever, so a
            # never-trained market always gets a bootstrap attempt regardless of what it says.
            reason = "never trained"
        else:
            decision = await self.scheduler.should_retrain(market.id, now)
            if not decision.get("should_retrain"):
                return RetrainingOutcome(market_key=market.market_key, should_retrain=False, reason=self._reason(decision))
            reason = self._reason(decision)

        if self.preflight is not None:
            report = await self.preflight.check(market.market_key, now)
            if not report.ready:
                blocking = ", ".join(f"{c.name}: {c.detail}" for c in report.blocking())
                return RetrainingOutcome(
                    market_key=market.market_key, should_retrain=True, reason=reason,
                    skipped_reason=f"preflight failed — {blocking}",
                )

        try:
            dataset = await self._build_validate_approve_dataset(market, now)
        except DatasetHasQualityIssuesError as exc:
            return RetrainingOutcome(
                market_key=market.market_key, should_retrain=True, reason=reason, skipped_reason=str(exc)
            )
        except Exception as exc:  # noqa: BLE001 — isolate one market's failure from the rest of the sweep
            return RetrainingOutcome(
                market_key=market.market_key, should_retrain=True, reason=reason,
                skipped_reason=f"dataset build failed: {exc}",
            )

        # Carve off a comparison holdout BEFORE training so the Challenger never trains on samples
        # its own comparison will later score it on — see module docstring and `_comparison_holdout`.
        holdout_samples: list[TrainingSample] = []
        training_dataset = dataset
        if not is_bootstrap and self.model_loader is not None and self.evaluator is not None and self.comparisons is not None:
            split = _comparison_holdout(dataset)
            if split is not None:
                training_pool, holdout_samples = split
                training_dataset = replace(dataset, samples=training_pool)

        # Additive-only Poisson injection (see `POISSON_ELIGIBLE_MARKETS`'s own comment) — only
        # when the caller left `candidates` at its default, never overriding an explicit roster.
        effective_candidates = candidates
        if candidates is None and market.market_key in POISSON_ELIGIBLE_MARKETS:
            effective_candidates = DEFAULT_CLASSIFICATION_CANDIDATES + (POISSON_ELIGIBLE_MARKETS[market.market_key],)

        try:
            next_model_version = await self._next_model_version(market)
            challenger, selection = await self.model_selection.select_and_register_challenger(
                market_id=market.id,
                dataset=training_dataset,
                target_type=market.target_type,
                model_key_prefix=market.market_key,
                next_version=next_model_version,
                now=now,
                candidates=effective_candidates,
            )
        except Exception as exc:  # noqa: BLE001 — same isolation as the dataset-build path
            return RetrainingOutcome(
                market_key=market.market_key, should_retrain=True, reason=reason,
                skipped_reason=f"model selection failed: {exc}",
            )

        if not is_bootstrap:
            comparison = None
            if holdout_samples:
                try:
                    comparison = await self._compare_against_champion(
                        market, champion, challenger, selection.winning_model, holdout_samples, now
                    )
                except Exception:  # noqa: BLE001 — a comparison failure never blocks the Challenger
                    # from being registered for human review; it just means no automated verdict.
                    comparison = None
            return RetrainingOutcome(
                market_key=market.market_key, should_retrain=True, reason=reason, challenger=challenger,
                comparison=comparison,
            )

        try:
            await self.model_selection.model_registry.promote_to_champion(
                challenger.id, approved_by=SYSTEM_APPROVER, now=now
            )
        except Exception as exc:  # noqa: BLE001 — a promotion failure still leaves a real, reviewable
            # CHALLENGER registered; report it rather than silently leaving the market untrained.
            return RetrainingOutcome(
                market_key=market.market_key, should_retrain=True, reason=reason, challenger=challenger,
                skipped_reason=f"bootstrap promotion failed: {exc}",
            )

        return RetrainingOutcome(
            market_key=market.market_key, should_retrain=True, reason=reason, challenger=challenger, bootstrapped=True
        )

    async def _compare_against_champion(
        self,
        market: MarketDefinition,
        champion: ModelDefinition,
        challenger: ModelDefinition,
        challenger_model,
        holdout_samples: list[TrainingSample],
        now: datetime,
    ) -> ChallengerEvaluation:
        """Scores `challenger_model` (already fitted in-memory — no need to reload it) and the
        current Champion (loaded fresh via `ModelLoaderService`, since only its serialized artifact
        is available here) on the identical `holdout_samples`, records the verdict, and auto-
        `retire()`s the Challenger when the Champion wins — the one comparison outcome this
        orchestrator is allowed to act on without a human (see module docstring)."""
        champion_model = await self.model_loader.load(
            champion.id, champion.framework, champion.algorithm, market.target_type, champion.artifact_ref
        )
        comparison = self.evaluator.evaluate(
            market_id=market.id,
            target_type=market.target_type,
            challenger_model_id=challenger.id,
            challenger=challenger_model,
            champion_model_id=champion.id,
            champion=champion_model,
            holdout_samples=holdout_samples,
            now=now,
        )
        await self.comparisons.record(comparison)

        if comparison.verdict is ComparisonVerdict.CHAMPION_BETTER:
            await self.model_selection.model_registry.retire(challenger.id, now)

        return comparison

    async def _build_validate_approve_dataset(self, market: MarketDefinition, now: datetime):
        latest = await self.dataset_registry.datasets.get_latest_version(market.id)
        next_version = (latest.version + 1) if latest is not None else 1
        dataset = await self.dataset_builder.build(market.id, now, next_version=next_version)
        registered = await self.dataset_registry.register(dataset)
        validated = await self.dataset_registry.validate(registered.id)
        return await self.dataset_registry.approve(validated.id, approved_by=SYSTEM_APPROVER, now=now)

    async def _next_model_version(self, market: MarketDefinition) -> int:
        existing = await self.models.list_by_market(market.id)
        return max((m.version for m in existing), default=0) + 1

    def _reason(self, decision: dict) -> str:
        if decision.get("is_stale"):
            return "dataset stale"
        if decision.get("drift", {}).get("drift_detected"):
            return "drift detected"
        return decision.get("reason", "unspecified")
