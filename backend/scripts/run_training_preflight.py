"""Milestone 19 Phase 2/4: read-only CLI entry point for `TrainingPreflightService`. Prints the
itemized readiness verdict for one football market (or every genuinely-trained one) against live
`dev.db` state — the same 12 checks described in
`modules/predictions/application/training_preflight_service.py` and
`docs/milestone19_preimplementation_audit.md` §16/§21.

Never writes anything: `TrainingPreflightService` only reads existing repositories and calls the
already-read-only `DatasetBuilder.build()`. A future Milestone 20 attempt should run this first
and treat a non-READY verdict as a hard stop, not something to route around.

Usage:
    TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/run_training_preflight.py football.both_teams_to_score
    TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/run_training_preflight.py --all-trained-football
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_training_preflight_service, get_engine
from modules.predictions.application.training_preflight_service import TrainingPreflightReport

# The 14 markets Milestone 17/19 confirmed have real labels/features (`prediction_outcomes` > 0)
# — the only markets for which a preflight verdict is meaningful today.
_GENUINELY_TRAINED_FOOTBALL_MARKETS = (
    "football.correct_score",
    "football.total_goals_over_under",
    "football.total_goals_over_under_0_5",
    "football.total_goals_over_under_1_5",
    "football.total_goals_over_under_3_5",
    "football.total_goals_over_under_4_5",
    "football.home_win_to_nil",
    "football.home_team_total_goals",
    "football.home_clean_sheet",
    "football.away_win_to_nil",
    "football.away_team_total_goals",
    "football.away_clean_sheet",
    "football.match_winner",
    "football.both_teams_to_score",
)


def _print_report(report: TrainingPreflightReport) -> None:
    verdict = "READY" if report.ready else "BLOCKED"
    print(f"\n{report.market_key}: {verdict}")
    for check in report.checks:
        mark = "PASS" if check.passed else "FAIL"
        print(f"  [{mark}] {check.name}: {check.detail}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("market_key", nargs="?", help="e.g. football.both_teams_to_score")
    parser.add_argument(
        "--all-trained-football", action="store_true",
        help="run against all 14 markets Milestone 17/19 confirmed are genuinely trained",
    )
    args = parser.parse_args()

    if not args.market_key and not args.all_trained_football:
        parser.error("pass a market_key or --all-trained-football")

    market_keys = _GENUINELY_TRAINED_FOOTBALL_MARKETS if args.all_trained_football else (args.market_key,)

    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        service = build_training_preflight_service(session)
        now = datetime.now(timezone.utc)
        ready_count = 0
        for market_key in market_keys:
            report = await service.check(market_key, now)
            _print_report(report)
            ready_count += int(report.ready)

    print(f"\n{ready_count}/{len(market_keys)} market(s) READY for training.")


if __name__ == "__main__":
    asyncio.run(main())
