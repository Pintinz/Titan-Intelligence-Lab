"""PROJECT TITANIQ — Phase 3, Workstream A runner.

Real production wiring only (apps.api.composition), run once against the live dev.db. For every
football production market with a Champion: runs the existing `TrainingPreflightService` (real
leakage/parity/provenance gates, unchanged), then `CalibrationValidationService.validate_market()`
(real chronological calibration/test split, real sklearn-based sigmoid/isotonic comparison,
real persisted `CalibrationReport` rows, real versioned challenger registration when a candidate
wins). Never retrains a base classifier, never promotes anything to CHAMPION — promotion is a
separate, explicit decision a human/operator makes after reviewing this run's output.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api import composition
from modules.predictions.application.calibration_validation_service import CalibrationBlockedError
from modules.predictions.domain.value_objects import MarketStatus


async def main() -> None:
    engine = composition.get_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    results = []

    async with session_factory() as session:
        markets = await composition.SqlAlchemyMarketRepository(session=session).list_by_sport("football")
        production_markets = [m for m in markets if m.status is MarketStatus.PRODUCTION]

        preflight = composition.build_training_preflight_service(session)
        calibration_service = composition.build_calibration_validation_service(session)

        for market in sorted(production_markets, key=lambda m: m.market_key):
            entry = {"market_key": market.market_key}

            report = await preflight.check(market.market_key, now)
            entry["preflight_ready"] = report.ready
            entry["preflight_gates"] = {c.name: c.passed for c in report.checks}

            try:
                result = await calibration_service.validate_market(market.id, market.market_key, now)
                entry["status"] = "VALIDATED"
                entry["is_multiclass"] = result.is_multiclass
                entry["calibration_sample_count"] = result.calibration_sample_count
                entry["test_sample_count"] = result.test_sample_count
                entry["winner"] = result.winner.value
                entry["decision_reason"] = result.decision_reason
                entry["promoted_model_id"] = str(result.promoted_model_id) if result.promoted_model_id else None
                entry["candidates"] = [
                    {
                        "method": c.method.value,
                        "log_loss": round(c.log_loss, 6),
                        "sample_count": c.sample_count,
                        "brier_score": round(c.report.brier_score, 6) if c.report else None,
                        "expected_calibration_error": round(c.report.expected_calibration_error, 6) if c.report else None,
                        "excluded_unseen_class_count": c.excluded_unseen_class_count,
                    }
                    for c in result.candidates
                ]
            except CalibrationBlockedError as exc:
                entry["status"] = "CALIBRATION_BLOCKED"
                entry["reason"] = str(exc)

            results.append(entry)
            await session.commit()

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
