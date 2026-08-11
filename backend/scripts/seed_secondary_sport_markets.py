"""One-off local dev helper: runs `BasketballMarketSeeder`, `BaseballMarketSeeder`, and
`TableTennisMarketSeeder` against dev.db — the same missing-invocation gap `seed_football_markets.py`
already fixed for football (see that script's docstring, audit finding 2026-08-02).

Deliberately does NOT seed placeholder CHAMPION models the way `seed_football_markets.py` does for
football. Football has real historical fixtures (even if feature coverage is partial) backing its
placeholder champions. Basketball/baseball/table_tennis do not: basketball's only fixtures in dev.db
are synthetic MockSportsDataProvider test artifacts (not real games), and baseball/table_tennis have
zero fixtures at all (backend Milestone 3 data audit, 2026-08-10). Seeding a CHAMPION for any of
these markets right now would mean every prediction served is the generic weighted-formula predictor
running against feature values computed from no real underlying data — closer to a fabricated
prediction than an honest one. Leaving these markets with no CHAMPION is what makes
`PredictionContextBuilder.build()` raise `NoChampionModelError`, surfaced by the API as the honest
"insufficient historical data" response — the same posture football's NOT_YET_TRAINED_MARKET_KEYS
markets already use.

This script only does what was asked: register the market/feature/mapping catalog so the Market
Registry reflects what `market_seeding.py` already defines in code for these three sports. Champion
seeding is a separate decision, once each sport has a real provider wired and real data flowing.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/seed_secondary_sport_markets.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import (
    build_baseball_market_seeder,
    build_basketball_market_seeder,
    build_table_tennis_market_seeder,
    get_engine,
)
from modules.predictions.baseball.market_seeding import MARKETS as BASEBALL_MARKETS
from modules.predictions.basketball.market_seeding import MARKETS as BASKETBALL_MARKETS
from modules.predictions.table_tennis.market_seeding import MARKETS as TABLE_TENNIS_MARKETS


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        now = datetime.now(timezone.utc)

        basketball_seeder = build_basketball_market_seeder(session)
        await basketball_seeder.seed(now)

        baseball_seeder = build_baseball_market_seeder(session)
        await baseball_seeder.seed(now)

        table_tennis_seeder = build_table_tennis_market_seeder(session)
        await table_tennis_seeder.seed(now)

        await session.commit()
        print(
            f"Seeded {len(BASKETBALL_MARKETS)} basketball markets, "
            f"{len(BASEBALL_MARKETS)} baseball markets, "
            f"{len(TABLE_TENNIS_MARKETS)} table_tennis markets into the live Market Registry. "
            f"No CHAMPION models were seeded (see module docstring) — every market will return "
            f"'insufficient historical data' until real data + a trained/promoted model exists."
        )


if __name__ == "__main__":
    asyncio.run(main())
