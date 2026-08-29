"""User-authorized full pipeline, generalized from `retrain_correct_score_with_venue_strength.py`
across every football PRODUCTION market with a live Champion (excluding `football.correct_score`,
already run separately, and `football.match_result`, which has zero predictions on file and no
Champion — a market that appears unused, not one worth bootstrap-training blind).

For each market: forces a real retrain now (bypassing only the staleness/drift gate, same as
`_batch_force_retrain_football.py`), replicating `_check_and_retrain`'s own additive-candidate
logic exactly (POISSON_ELIGIBLE_MARKETS / DIXON_COLES_ELIGIBLE_MARKETS, both real dicts from
scheduled_retraining_orchestrator.py — most of these 17 markets are not Poisson-eligible and get
the AutomaticModelSelectionService's own default roster instead). Runs the same empirical
chronological-holdout comparison the scheduled sweep runs, and promotes ONLY when the verdict is
`challenger_better` — explicitly authorized by the user's "Full pipeline, auto-promote if the
Challenger wins" selection, now extended to this market set. `inconclusive`/`champion_better`
leaves the Champion exactly as-is (the orchestrator's own `_compare_against_champion` already
auto-retires a `champion_better` Challenger).

One market's failure never blocks the rest — same isolation posture as the older batch script.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python -m scripts.retrain_football_markets_with_promotion
"""

from __future__ import annotations

import asyncio
import traceback
from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_scheduled_retraining_orchestrator, get_engine
from scripts.production_safety_guard import require_confirmation_outside_development
from modules.predictions.application.scheduled_retraining_orchestrator import (
    DEFAULT_CLASSIFICATION_CANDIDATES,
    DIXON_COLES_ELIGIBLE_MARKETS,
    POISSON_ELIGIBLE_MARKETS,
    _comparison_holdout,
)
from modules.predictions.domain.model_comparison import ComparisonVerdict
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyMarketRepository

APPROVED_BY = "claude-agent (user-authorized full pipeline, 2026-08-27)"

MARKET_KEYS = [
    "football.both_teams_to_score",
    "football.total_goals_over_under",
    "football.total_goals_over_under_0_5",
    "football.total_goals_over_under_1_5",
    "football.total_goals_over_under_3_5",
    "football.total_goals_over_under_4_5",
    "football.home_team_total_goals",
    "football.away_team_total_goals",
    "football.home_win_to_nil",
    "football.away_win_to_nil",
    "football.home_clean_sheet",
    "football.away_clean_sheet",
    "football.first_half_winner",
    "football.second_half_winner",
    "football.first_half_goals",
    "football.first_half_both_teams_to_score",
    "football.match_winner",
]


async def run_one(orchestrator, markets_repo, market_key: str, now: datetime) -> str:
    market = await markets_repo.get_by_key(market_key)
    if market is None:
        return f"{market_key}: SKIPPED — market not found"

    champion = await orchestrator.models.get_champion(market.id)
    if champion is None:
        return f"{market_key}: SKIPPED — no champion yet (bootstrap case, different code path)"

    report = await orchestrator.preflight.check(market.market_key, now)
    if not report.ready:
        blocking = ", ".join(f"{c.name}: {c.detail}" for c in report.blocking())
        return f"{market_key}: SKIPPED — preflight failed: {blocking}"

    dataset = await orchestrator._build_validate_approve_dataset(market, now)

    split = _comparison_holdout(dataset)
    training_dataset = dataset
    holdout_samples = []
    if split is not None:
        training_pool, holdout_samples = split
        training_dataset = replace(dataset, samples=training_pool)

    effective_candidates = None
    if market.market_key in POISSON_ELIGIBLE_MARKETS:
        effective_candidates = DEFAULT_CLASSIFICATION_CANDIDATES + (POISSON_ELIGIBLE_MARKETS[market.market_key],)
        if market.market_key in DIXON_COLES_ELIGIBLE_MARKETS:
            effective_candidates = effective_candidates + (DIXON_COLES_ELIGIBLE_MARKETS[market.market_key],)

    next_version = await orchestrator._next_model_version(market)
    challenger, selection = await orchestrator.model_selection.select_and_register_challenger(
        market_id=market.id, dataset=training_dataset, target_type=market.target_type,
        model_key_prefix=market.market_key, next_version=next_version, now=now, candidates=effective_candidates,
    )

    if not holdout_samples:
        return (
            f"{market_key}: challenger v{challenger.version} ({challenger.algorithm}) registered, "
            f"dataset n={len(dataset.samples)} — no holdout available for comparison, NOT promoted"
        )

    comparison = await orchestrator._compare_against_champion(
        market, champion, challenger, selection.winning_model, holdout_samples, now
    )
    summary = (
        f"{market_key}: challenger v{challenger.version} ({challenger.algorithm}) vs champion v{champion.version} "
        f"({champion.algorithm}) — dataset n={len(dataset.samples)}, holdout n={comparison.holdout_sample_count} — "
        f"verdict={comparison.verdict.value} — challenger {comparison.decisive_metric}="
        f"{getattr(comparison.challenger_metrics, comparison.decisive_metric)} vs champion="
        f"{getattr(comparison.champion_metrics, comparison.decisive_metric)}"
    )

    if comparison.verdict is ComparisonVerdict.CHALLENGER_BETTER:
        promoted = await orchestrator.model_selection.model_registry.promote_to_champion(
            challenger.id, approved_by=APPROVED_BY, now=now
        )
        summary += f" — PROMOTED v{promoted.version} to CHAMPION"
    else:
        summary += " — champion retained"

    return summary


async def main() -> None:
    require_confirmation_outside_development(__file__)
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    results = []
    for market_key in MARKET_KEYS:
        async with session_factory() as session:
            orchestrator = build_scheduled_retraining_orchestrator(session)
            markets_repo = SqlAlchemyMarketRepository(session=session)
            now = datetime.now(timezone.utc)
            try:
                result = await run_one(orchestrator, markets_repo, market_key, now)
                await session.commit()
            except Exception as exc:  # noqa: BLE001 — one market's failure must never stop the batch
                await session.rollback()
                result = f"{market_key}: FAILED — {exc}"
                traceback.print_exc()
            results.append(result)
            print(result, flush=True)

    print("\n=== SUMMARY ===")
    for r in results:
        print(r)


if __name__ == "__main__":
    asyncio.run(main())
