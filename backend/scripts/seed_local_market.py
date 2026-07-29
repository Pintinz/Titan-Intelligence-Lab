"""One-off local dev helper: seeds a single prediction market + heuristic model into dev.db so
the frontend's Model Center / Experiment Center have something to render during manual
verification (mirrors tests/unit/apps/test_api_ml_platform.py's ``_seed_market`` fixture helper,
just run once against the persistent local SQLite DB instead of a throwaway test engine).

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/seed_local_market.py
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import get_engine
from modules.predictions.domain.entities import MarketDefinition, ModelDefinition
from modules.predictions.domain.value_objects import (
    MarketId,
    MarketKind,
    MarketStatus,
    ModelId,
    ModelStatus,
    TargetType,
)
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyMarketRepository,
    SqlAlchemyModelRepository,
)


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        markets = SqlAlchemyMarketRepository(session=session)
        models = SqlAlchemyModelRepository(session=session)

        market = MarketDefinition(
            id=MarketId(uuid4()),
            market_key="football.match_result",
            sport_code="football",
            name="Football — Match Result",
            category="match_outcome",
            market_kind=MarketKind.BINARY,
            target_type=TargetType.CLASSIFICATION,
            status=MarketStatus.PRODUCTION,
        )
        await markets.upsert(market)

        model = ModelDefinition(
            id=ModelId(uuid4()),
            market_id=market.id,
            model_key="football.match_result.heuristic",
            version=1,
            algorithm="heuristic_logistic_v1",
            status=ModelStatus.CHAMPION,
        )
        await models.upsert(model)
        await session.commit()
        print(f"Seeded market {market.market_key} ({market.id.value}) with champion model {model.model_key}")


if __name__ == "__main__":
    asyncio.run(main())
