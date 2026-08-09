"""Continuous Outcome Learning Engine — Candidate-vs-Champion comparison domain (2026-08-08).

`ScheduledRetrainingOrchestrator` already trained a fresh Challenger for every PRODUCTION market
on a schedule (see its own module docstring), but for a market that already has a live CHAMPION it
never scored that Challenger against the Champion's own real performance — the "controlled
retraining" half of the spec ("Compare Against Current Production Model ... Candidate Better? YES
-> Deploy NO -> Reject") had no automated decision at all, only a human clicking through the Ops
Center to eyeball numbers. `ChallengerEvaluationService` (application layer) is that missing
comparison; this module is its result shape.

Deliberately narrower than the spec's literal "YES -> Deploy": `ModelRegistryService.promote_to_champion`
already requires a human `approved_by` for a market that has a live CHAMPION (see
`scheduled_retraining_orchestrator.py`'s own docstring for why that gate exists and stays), so a
CHALLENGER_BETTER verdict does not auto-promote — it surfaces the verdict prominently (Ops Center,
`/api/v1/admin/ml/*`) so the human's decision is "confirm what the engine already found," not "go
derive the comparison by hand." A CHAMPION_BETTER verdict *is* fully automatic (`retire()`ing the
losing Challenger touches no production traffic), directly satisfying "if a newly trained model
performs worse: KEEP CURRENT PRODUCTION MODEL. Do not automatically deploy it."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from modules.predictions.domain.value_objects import ChallengerEvaluationId, MarketId, ModelId


class ComparisonVerdict(str, Enum):
    CHALLENGER_BETTER = "challenger_better"
    CHAMPION_BETTER = "champion_better"
    # No champion to compare against, too few holdout samples, or every metric's relative change
    # fell within the noise band (`MIN_RELATIVE_IMPROVEMENT`) — an honest "couldn't tell" outcome,
    # treated the same as CHAMPION_BETTER for the auto-retire decision (never replace a working
    # model on an inconclusive signal), but recorded distinctly so a human reviewing history can
    # tell "the challenger genuinely lost" apart from "we couldn't tell."
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ComparisonMetrics:
    """Scored on the SAME held-out sample set for both models (`ChallengerEvaluationService`) —
    only populated fields are ones the target type / class shape actually supports (spec §8's
    priority order: Log Loss, then Brier Score, then Calibration, for probability predictions;
    MAE for regression). `brier_score`/`expected_calibration_error` stay `None` for a multiclass
    classification model — both assume a binary (probability, outcome) sample shape that a
    multiclass model's `distribution` output doesn't reduce to without inventing a convention
    nobody asked for; `log_loss` alone already generalizes to any number of classes."""

    log_loss: float | None = None
    brier_score: float | None = None
    expected_calibration_error: float | None = None
    mae: float | None = None


@dataclass(frozen=True)
class ChallengerEvaluation:
    id: ChallengerEvaluationId
    market_id: MarketId
    challenger_model_id: ModelId
    champion_model_id: ModelId | None
    challenger_metrics: ComparisonMetrics
    champion_metrics: ComparisonMetrics | None
    verdict: ComparisonVerdict
    decisive_metric: str
    """Which `ComparisonMetrics` field the verdict — the first metric, in spec §8's priority
    order, whose relative change between the two models exceeded the noise band. ``"none"`` when
    there was no champion to compare against at all."""
    holdout_sample_count: int
    evaluated_at: datetime
