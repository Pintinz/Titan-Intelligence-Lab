"""Updates the `feature_snapshot` of every already-backfilled `football.correct_score` training
`Prediction` (`backfill_correct_score_training_data.py`'s own `BACKFILL_MODEL_KEY` anchor rows)
to add `FixtureVenueStrengthCalculator`'s four features, read as-of each fixture's own kickoff —
same point-in-time-safe query pattern that script already used for `expected_home_goals`/
`expected_away_goals`. Run `backfill_venue_strength_for_completed_fixtures.py` first, or every
lookup here will honestly find nothing to add.

Additive, not destructive: existing keys (`expected_home_goals`/`expected_away_goals`) are kept —
`FootballGoalsPoissonAdapter.fit()` unions whatever feature keys are actually present across
samples, so a mixed snapshot (some samples with venue-strength, some without, matching real
coverage — `min_league_sample`/`window` thresholds mean not every fixture qualifies) is the
honest shape of this real, partial dataset, not a bug to paper over. A sample missing a given key
simply vectorizes as 0.0 for it (the existing default for an absent feature), the same
"unavailable, not fabricated" contract every other honestly-partial feature already has.

Idempotent: re-running just re-reads the same feature values and re-writes the same dict.

Two UUID formats coexist in this DB (verified live against dev.db): `fixtures.id`/`predictions.id`/
`predictions.market_id` are raw 32-hex (SQLAlchemy's default non-native Uuid storage on SQLite),
while `predictions.subject_ref` and `feature_values_offline.entity_id` are dashed (app-level
`str(FixtureId(...))`). This script matches each column against its own real on-disk format
rather than assuming one convention throughout.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python -m scripts.refresh_correct_score_training_feature_snapshots
"""

from __future__ import annotations

import asyncio
import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import get_engine
from modules.predictions.domain.value_objects import PredictionId
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyMarketRepository,
    SqlAlchemyPredictionRepository,
)

MARKET_KEY = "football.correct_score"
BACKFILL_MODEL_KEY = "football.correct_score.historical-backfill"

_VENUE_STRENGTH_KEYS = (
    "football.fixture.home_attack_strength",
    "football.fixture.home_defence_strength",
    "football.fixture.away_attack_strength",
    "football.fixture.away_defence_strength",
)


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        markets = SqlAlchemyMarketRepository(session=session)
        predictions = SqlAlchemyPredictionRepository(session=session)

        market = await markets.get_by_key(MARKET_KEY)
        if market is None:
            raise RuntimeError(f"market '{MARKET_KEY}' not found")
        market_id_raw = market.id.value.hex

        rows = (
            await session.execute(
                text(
                    """
                    SELECT p.id, p.subject_ref, f.scheduled_at
                    FROM predictions p
                    JOIN models m ON m.id = p.model_id
                    JOIN fixtures f ON f.id = REPLACE(p.subject_ref, '-', '')
                    WHERE p.market_id = :market_id AND m.model_key = :model_key
                    """
                ),
                {"market_id": market_id_raw, "model_key": BACKFILL_MODEL_KEY},
            )
        ).all()
        print(f"{len(rows)} backfilled training predictions to refresh")

        updated = 0
        added_values = 0
        for prediction_id_raw, subject_ref_dashed, scheduled_at in rows:
            addition: dict[str, float] = {}
            for feature_key in _VENUE_STRENGTH_KEYS:
                value_row = (
                    await session.execute(
                        text(
                            """
                            SELECT v.value FROM feature_values_offline v
                            WHERE v.feature_key = :feature_key AND v.entity_id = :entity_id AND v.as_of <= :cutoff
                            ORDER BY v.as_of DESC LIMIT 1
                            """
                        ),
                        {"feature_key": feature_key, "entity_id": subject_ref_dashed, "cutoff": scheduled_at},
                    )
                ).first()
                if value_row is not None and value_row[0] is not None:
                    addition[feature_key] = json.loads(value_row[0])["v"]

            if not addition:
                continue

            prediction = await predictions.get(PredictionId(uuid.UUID(hex=prediction_id_raw)))
            if prediction is None:
                continue
            prediction.feature_snapshot = {**prediction.feature_snapshot, **addition}
            await predictions.update(prediction)
            updated += 1
            added_values += len(addition)

        await session.commit()
        print(f"predictions updated: {updated}")
        print(f"venue-strength values added across all snapshots: {added_values}")


if __name__ == "__main__":
    asyncio.run(main())
