"""One-off local dev helper: retires the legacy `football.match_result` market.

`football.match_result` predates the real market catalog (`market_outcome_registry.py`) — it was
hand-seeded by `scripts/seed_local_market.py` as a plain `MarketKind.BINARY` row with no catalog
entry, no real outcome-label contract, and no resolver. Its "AI Verdict" tile has always shown
the raw generic predictor value ("positive"/"negative") rather than a real label, because
`outcome_label_mapper.map_generic_value_to_real_label` correctly refuses to invent a label for a
market with no catalog entry. `football.match_winner` (built 2026-08-02, genuinely
`MarketKind.HOME_DRAW_AWAY`, a real catalog entry, a real resolver) answers the exact same
question — "who wins this match" — properly, making this market redundant as well as broken-
looking.

Uses the real `MarketRegistryService.deprecate()` lifecycle transition (PRODUCTION -> DEPRECATED)
rather than deleting the row — `PredictionEngine`/the market selector both already only serve
`status=production` markets, so this is enough to make the tile disappear from the frontend
without destroying the market definition or any predictions already recorded against it.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/retire_legacy_match_result_market.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_market_registry_service, get_engine

MARKET_KEY = "football.match_result"


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        registry = build_market_registry_service(session)
        market = await registry.deprecate(MARKET_KEY, datetime.now(timezone.utc))
        await session.commit()
        print(f"Deprecated {market.market_key} — status is now {market.status.value}.")


if __name__ == "__main__":
    asyncio.run(main())
