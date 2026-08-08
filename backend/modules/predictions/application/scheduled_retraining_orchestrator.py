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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.predictions.application.dataset_builder_service import DatasetBuilder
from modules.predictions.application.dataset_registry_service import DatasetHasQualityIssuesError, DatasetRegistryService
from modules.predictions.application.model_selection_service import AutomaticModelSelectionService
from modules.predictions.application.training_pipeline_service import RetrainingScheduler
from modules.predictions.domain.entities import MarketDefinition, ModelDefinition
from modules.predictions.domain.value_objects import MarketStatus
from modules.predictions.ports.repositories import MarketRepositoryPort, ModelRepositoryPort

SYSTEM_APPROVER = "scheduled-retraining"


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


@dataclass
class ScheduledRetrainingOrchestrator:
    markets: MarketRepositoryPort
    models: ModelRepositoryPort
    scheduler: RetrainingScheduler
    dataset_builder: DatasetBuilder
    dataset_registry: DatasetRegistryService
    model_selection: AutomaticModelSelectionService

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
        is_bootstrap = await self.models.get_champion(market.id) is None

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

        try:
            next_model_version = await self._next_model_version(market)
            challenger, _selection = await self.model_selection.select_and_register_challenger(
                market_id=market.id,
                dataset=dataset,
                target_type=market.target_type,
                model_key_prefix=market.market_key,
                next_version=next_model_version,
                now=now,
                candidates=candidates,
            )
        except Exception as exc:  # noqa: BLE001 — same isolation as the dataset-build path
            return RetrainingOutcome(
                market_key=market.market_key, should_retrain=True, reason=reason,
                skipped_reason=f"model selection failed: {exc}",
            )

        if not is_bootstrap:
            return RetrainingOutcome(market_key=market.market_key, should_retrain=True, reason=reason, challenger=challenger)

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
