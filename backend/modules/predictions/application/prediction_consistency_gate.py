"""Pre-Gemini Prediction-Explanation Consistency Gate (spec §23) — checked as the very first
step inside both opt-in explanation subsystems (`ContextualReasoningService.review()`,
`FootballExplanationService.explain()`) before either ever calls Gemini or does any real work.
If the base `Prediction` being explained has drifted out of sync with the market's current
state, calling Gemini would risk narrating a prediction that no longer reflects what TitanIQ's
own current pipeline would produce — so the Gemini call is skipped entirely and a real,
persisted diagnostic (`BLOCKED_INCONSISTENT_EVIDENCE: <failed checks>`) is returned instead.

Most other §23 checks (prediction/probability/scoreline consistency, attribution consistency)
are structurally guaranteed by construction, not something this gate needs to re-verify:
`Prediction.value`/`probability`/`probability_distribution` are produced together atomically
inside one `PredictionEngine.generate()` call, and both explanation subsystems compute their own
attribution/baseline fresh from that same `Prediction.feature_snapshot` against that same model
— there is no code path that could desync them independently of what this gate actually checks.
This gate covers the checks that genuinely CAN drift between when a prediction was generated (or
served from cache) and when a caller later requests an explanation for it: Champion/model
currency, provenance, temporal safety, and feature parity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from modules.predictions.domain.entities import MarketDefinition, Prediction
from modules.predictions.ports.repositories import ModelRepositoryPort

DEFAULT_MAX_PREDICTION_AGE = timedelta(hours=48)

# spec §22 "Correct-Score Consistency" — a real, well-formed scoreline is either "OTHER" (the
# finite-grid catch-all, `market_outcome_registry._correct_score_grid()`) or "{home}-{away}" with
# non-negative integers. Never a live risk for the market's own served prediction (the value comes
# straight from `MARKET_OUTCOME_CATALOG["football.correct_score"].allowed_values`), but a real,
# cheap, zero-fabrication guard against ever handing Gemini a scoreline it could narrate
# inconsistently (§22's exact failure mode: "Expected Away Goals of 2.40 supports 1-0" for a score
# that structurally can't be what the payload's own base_prediction says).
_CORRECT_SCORE_MARKET_KEY = "football.correct_score"
_SCORELINE_PATTERN = re.compile(r"^\d+-\d+$")


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """Same fix as modules.ingestion.application.sync_orchestrator._ensure_aware and its other
    duplicates — SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007)."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


@dataclass(frozen=True)
class ConsistencyCheckResult:
    passed: bool
    failed_checks: tuple[str, ...] = field(default_factory=tuple)

    @property
    def reason(self) -> str | None:
        if self.passed:
            return None
        return "BLOCKED_INCONSISTENT_EVIDENCE: " + ", ".join(self.failed_checks)


@dataclass
class PredictionConsistencyGate:
    models: ModelRepositoryPort
    max_prediction_age: timedelta = DEFAULT_MAX_PREDICTION_AGE

    async def check(self, prediction: Prediction, market: MarketDefinition, now: datetime) -> ConsistencyCheckResult:
        failed: list[str] = []

        if prediction.model_id is None:
            return ConsistencyCheckResult(passed=False, failed_checks=("no_associated_model",))

        model = await self.models.get(prediction.model_id)
        if model is None:
            return ConsistencyCheckResult(passed=False, failed_checks=("model_definition_missing",))

        champion = await self.models.get_champion(market.id)
        if champion is None or champion.id != prediction.model_id:
            failed.append("model_no_longer_champion")

        if not model.is_genuinely_trained():
            failed.append("model_provenance_missing")

        if not prediction.feature_snapshot:
            failed.append("empty_feature_snapshot")

        if prediction.generated_at is not None:
            age = now - _ensure_aware(prediction.generated_at, now)
            if age > self.max_prediction_age:
                failed.append("prediction_too_stale")

        if market.market_key == _CORRECT_SCORE_MARKET_KEY:
            value = str(prediction.value)
            if value != "OTHER" and not _SCORELINE_PATTERN.match(value):
                failed.append("malformed_correct_score_value")

        return ConsistencyCheckResult(passed=not failed, failed_checks=tuple(failed))
