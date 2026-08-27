"""One-off, user-authorized retrain: forces a real `football.correct_score` retrain now (bypassing
only the staleness/drift gate, same as `_batch_force_retrain_football.py`) so the new venue-strength
features — just backfilled into the 828 real training predictions' `feature_snapshot` by
`refresh_correct_score_training_feature_snapshots.py` — actually reach a trained model. Includes the
Dixon-Coles candidate (`DIXON_COLES_ELIGIBLE_MARKETS`), replicating `_check_and_retrain`'s own
additive-candidate-injection logic exactly (lines 290-294 of scheduled_retraining_orchestrator.py)
rather than the older batch script's Poisson-only candidate list.

If the empirical chronological-holdout comparison (`ChallengerEvaluationService`, log-loss/Brier/
calibration priority order — the same real comparison the scheduled sweep runs) finds the Challenger
beats the current Champion, this script promotes it directly — explicitly authorized by the user's
"Full pipeline, auto-promote if the Challenger wins" selection. If the Champion wins, the
orchestrator's own `_compare_against_champion` already auto-retires the Challenger; nothing further
to do. Every branch is reported honestly, including "no holdout available for comparison".

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python -m scripts.retrain_correct_score_with_venue_strength
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_scheduled_retraining_orchestrator, get_engine
from modules.predictions.application.scheduled_retraining_orchestrator import (
    DEFAULT_CLASSIFICATION_CANDIDATES,
    DIXON_COLES_ELIGIBLE_MARKETS,
    POISSON_ELIGIBLE_MARKETS,
    _comparison_holdout,
)
from modules.predictions.domain.model_comparison import ComparisonVerdict
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyMarketRepository

MARKET_KEY = "football.correct_score"
APPROVED_BY = "claude-agent (user-authorized full pipeline, 2026-08-27)"


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        orchestrator = build_scheduled_retraining_orchestrator(session)
        markets_repo = SqlAlchemyMarketRepository(session=session)
        now = datetime.now(timezone.utc)

        market = await markets_repo.get_by_key(MARKET_KEY)
        if market is None:
            raise RuntimeError(f"market '{MARKET_KEY}' not found")

        champion = await orchestrator.models.get_champion(market.id)
        if champion is None:
            raise RuntimeError("no champion registered — this is the bootstrap case, different code path")
        print(f"current champion: v{champion.version} ({champion.algorithm}) id={champion.id.value}")

        report = await orchestrator.preflight.check(market.market_key, now)
        if not report.ready:
            blocking = ", ".join(f"{c.name}: {c.detail}" for c in report.blocking())
            print(f"ABORTED — preflight failed: {blocking}")
            return

        dataset = await orchestrator._build_validate_approve_dataset(market, now)
        print(f"dataset built: v{dataset.version}, n={len(dataset.samples)} samples")

        split = _comparison_holdout(dataset)
        training_dataset = dataset
        holdout_samples = []
        if split is not None:
            training_pool, holdout_samples = split
            training_dataset = replace(dataset, samples=training_pool)
        print(f"holdout carved: n={len(holdout_samples)}, training pool n={len(training_dataset.samples)}")

        effective_candidates = DEFAULT_CLASSIFICATION_CANDIDATES + (POISSON_ELIGIBLE_MARKETS[MARKET_KEY],)
        if MARKET_KEY in DIXON_COLES_ELIGIBLE_MARKETS:
            effective_candidates = effective_candidates + (DIXON_COLES_ELIGIBLE_MARKETS[MARKET_KEY],)
        print(f"candidate roster: {[c.algorithm.value for c in effective_candidates]}")

        next_version = await orchestrator._next_model_version(market)
        challenger, selection = await orchestrator.model_selection.select_and_register_challenger(
            market_id=market.id, dataset=training_dataset, target_type=market.target_type,
            model_key_prefix=market.market_key, next_version=next_version, now=now,
            candidates=effective_candidates,
        )
        print(f"challenger registered: v{challenger.version} ({challenger.algorithm}) id={challenger.id.value}")
        print(f"selection winner: {selection.winning_candidate.algorithm.value} — {selection.ranking_metric}={selection.ranking_value}")

        if not holdout_samples:
            await session.commit()
            print("NO HOLDOUT AVAILABLE — challenger registered but not compared; promotion requires a human review.")
            return

        comparison = await orchestrator._compare_against_champion(
            market, champion, challenger, selection.winning_model, holdout_samples, now
        )
        print(f"\n=== COMPARISON (holdout n={comparison.holdout_sample_count}) ===")
        print(f"verdict: {comparison.verdict.value}")
        print(f"decisive metric: {comparison.decisive_metric}")
        print(f"challenger {comparison.decisive_metric}: {getattr(comparison.challenger_metrics, comparison.decisive_metric)}")
        print(f"champion {comparison.decisive_metric}: {getattr(comparison.champion_metrics, comparison.decisive_metric)}")
        print(f"challenger log_loss={comparison.challenger_metrics.log_loss} brier={comparison.challenger_metrics.brier_score}")
        print(f"champion  log_loss={comparison.champion_metrics.log_loss} brier={comparison.champion_metrics.brier_score}")

        if comparison.verdict is ComparisonVerdict.CHALLENGER_BETTER:
            promoted = await orchestrator.model_selection.model_registry.promote_to_champion(
                challenger.id, approved_by=APPROVED_BY, now=now
            )
            await session.commit()
            print(f"\nPROMOTED: v{promoted.version} ({promoted.algorithm}) is now CHAMPION for {MARKET_KEY}.")
        else:
            await session.commit()
            print(f"\nCHAMPION RETAINED — v{champion.version} ({champion.algorithm}) still champion. Challenger retired.")


if __name__ == "__main__":
    asyncio.run(main())
