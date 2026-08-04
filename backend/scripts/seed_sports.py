"""One-off local dev helper: seeds the four `sports.sports` reference rows into dev.db so
sport-scoped endpoints (`/api/v1/sports/{sport_code}/...`) resolve instead of 404ing with
"sport '<code>' not found" — nothing in the ingestion pipeline currently writes this table,
so a fresh local DB has no rows in it at all (mirrors scripts/seed_local_market.py's pattern for
prediction markets, just for the sports reference table instead).

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/seed_sports.py
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import get_engine
from modules.sports.domain.entities import Sport
from modules.sports.domain.value_objects import SportCode, SportId
from modules.sports.infrastructure.persistence.repositories import SqlAlchemySportRepository

SPORTS = [
    (SportCode.FOOTBALL, "Football"),
    (SportCode.BASKETBALL, "Basketball"),
    (SportCode.BASEBALL, "Baseball"),
    (SportCode.TABLE_TENNIS, "Table Tennis"),
]


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        sports = SqlAlchemySportRepository(session=session)

        for code, name in SPORTS:
            existing = await sports.get_by_code(code)
            if existing:
                print(f"Already seeded: {code.value}")
                continue
            sport = Sport(id=SportId(uuid4()), code=code, name=name, status="active")
            await sports.upsert(sport)
            print(f"Seeded sport {code.value} ({sport.id.value})")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
