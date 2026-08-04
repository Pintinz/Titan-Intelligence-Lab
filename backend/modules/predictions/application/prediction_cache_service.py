"""Prediction Cache / Versioning / Audit (Milestone 9 Part 4 "Build:" list) — the persistence
wrapper around `PredictionEngine.generate()`. `PredictionEngine` itself is side-effect-free (it
computes and returns a `Prediction`, never persists); this service is where "No prediction
without ... audit history" (Part 4 "Rules") is actually enforced — every call either returns a
cached prediction or persists a freshly generated one plus its `PredictionAudit` row, and no
generated prediction leaves this service without one.

- **Caching**: `get_or_generate()` reuses the subject+market's most recent prediction if it's
  still within ``cache_ttl_seconds`` of its `data_freshness` — regenerating on every request would
  recompute the same features/predictor/calibration for no reason when nothing has changed.
- **Versioning**: a newly generated prediction for a subject+market that already has a
  PUBLISHED prediction marks the old one SUPERSEDED before persisting the new one — at most one
  PUBLISHED prediction per subject+market at a time, the chain the "Prediction Comparison"/
  "Prediction History" APIs (Milestone 9 Part 5) will read.
- **Confidence gate**: a freshly generated prediction only becomes PUBLISHED if its
  `ConfidenceBreakdown.composite` meets the market's own configured `confidence_threshold`
  (`MarketDefinition.confidence_threshold`) — otherwise it's persisted as DRAFT, visible to the
  Admin Control Center for a human `approve`/`reject` Admin Action (Part 6), never auto-published.
- **Audit**: every generation, publish, and void records a `PredictionAudit` row — the
  `Admin Actions` (Part 6: Approve/Reject/Activate/Deactivate/Rollback/...) this service exposes
  as `approve`/`reject`/`void` all do the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.alerts.domain.value_objects import AlertType
from modules.alerts.ports.notifier import AlertNotifierPort
from modules.features.domain.value_objects import EntityType
from modules.predictions.application.prediction_engine import PredictionEngine
from modules.predictions.domain.entities import Prediction, PredictionAudit
from modules.predictions.domain.value_objects import AuditAction, PredictionAuditId, PredictionStatus
from modules.predictions.ports.repositories import MarketRepositoryPort, PredictionAuditRepositoryPort, PredictionRepositoryPort
from modules.watchlist.domain.value_objects import WatchlistEntityType


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007)."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


class MarketNotFoundError(KeyError):
    pass


class InvalidPredictionStatusTransitionError(ValueError):
    pass


@dataclass
class PredictionCacheService:
    engine: PredictionEngine
    markets: MarketRepositoryPort
    predictions: PredictionRepositoryPort
    audits: PredictionAuditRepositoryPort
    cache_ttl_seconds: float = 300.0
    alerts: AlertNotifierPort | None = None

    async def get_or_generate(
        self,
        market_key: str,
        entity_type: EntityType,
        entity_id: str,
        subject_ref: str,
        now: datetime,
        actor: str = "prediction-engine",
    ) -> Prediction:
        market = await self.markets.get_by_key(market_key)
        if market is None:
            raise MarketNotFoundError(market_key)

        cached = await self.predictions.get_latest_for_subject(subject_ref, market.id)
        if cached is not None and cached.data_freshness is not None:
            age_seconds = (now - _ensure_aware(cached.data_freshness, now)).total_seconds()
            if 0 <= age_seconds <= self.cache_ttl_seconds:
                return cached

        return await self._generate_and_persist(market, entity_type, entity_id, subject_ref, now, actor)

    async def regenerate(
        self,
        market_key: str,
        entity_type: EntityType,
        entity_id: str,
        subject_ref: str,
        now: datetime,
        actor: str = "admin",
    ) -> Prediction:
        """Bypasses the cache TTL entirely — the "Recompute"/"Reprocess"/"Retry" Admin Action
        (Part 6): always runs the full pipeline fresh and supersedes whatever prediction
        currently exists for this subject+market."""
        market = await self.markets.get_by_key(market_key)
        if market is None:
            raise MarketNotFoundError(market_key)
        return await self._generate_and_persist(market, entity_type, entity_id, subject_ref, now, actor)

    async def _generate_and_persist(
        self, market, entity_type: EntityType, entity_id: str, subject_ref: str, now: datetime, actor: str
    ) -> Prediction:
        prediction = await self.engine.generate(market.market_key, entity_type, entity_id, subject_ref, now)
        return await self._persist_new_version(prediction, market.confidence_threshold, actor, now)

    async def approve(self, prediction: Prediction, actor: str, now: datetime) -> Prediction:
        if prediction.status not in (PredictionStatus.DRAFT, PredictionStatus.SUPERSEDED):
            raise InvalidPredictionStatusTransitionError(
                f"cannot approve prediction from status {prediction.status.value}"
            )
        prediction.status = PredictionStatus.PUBLISHED
        await self.predictions.update(prediction)
        await self._audit(AuditAction.APPROVED, actor, now, prediction)
        return prediction

    async def reject(self, prediction: Prediction, actor: str, now: datetime, reason: str = "") -> Prediction:
        if prediction.status is not PredictionStatus.DRAFT:
            raise InvalidPredictionStatusTransitionError(
                f"cannot reject prediction from status {prediction.status.value} — must be DRAFT"
            )
        prediction.status = PredictionStatus.VOIDED
        await self.predictions.update(prediction)
        await self._audit(AuditAction.REJECTED, actor, now, prediction, details={"reason": reason})
        return prediction

    async def void(self, prediction: Prediction, actor: str, now: datetime, reason: str = "") -> Prediction:
        prediction.status = PredictionStatus.VOIDED
        await self.predictions.update(prediction)
        await self._audit(AuditAction.ARCHIVED, actor, now, prediction, details={"reason": reason})
        return prediction

    async def _persist_new_version(
        self, prediction: Prediction, confidence_threshold: float, actor: str, now: datetime
    ) -> Prediction:
        previous = await self.predictions.get_latest_for_subject(prediction.subject_ref, prediction.market_id)
        was_published = previous is not None and previous.status is PredictionStatus.PUBLISHED
        if was_published:
            previous.status = PredictionStatus.SUPERSEDED
            await self.predictions.update(previous)

        if prediction.confidence.composite >= confidence_threshold:
            prediction.status = PredictionStatus.PUBLISHED

        await self.predictions.record(prediction)
        await self._audit(AuditAction.GENERATED, actor, now, prediction)

        if was_published and prediction.status is PredictionStatus.PUBLISHED and self.alerts is not None:
            await self.alerts.notify_watchers(
                WatchlistEntityType.FIXTURE,
                prediction.subject_ref,
                AlertType.PREDICTION_CHANGED,
                "Prediction updated",
                f"The prediction for {prediction.subject_ref} changed to {prediction.value}.",
                now,
            )
        return prediction

    async def _audit(
        self, action: AuditAction, actor: str, now: datetime, prediction: Prediction, details: dict | None = None
    ) -> PredictionAudit:
        audit = PredictionAudit(
            id=PredictionAuditId(uuid4()),
            action=action,
            actor=actor,
            occurred_at=now,
            prediction_id=prediction.id,
            market_id=prediction.market_id,
            model_id=prediction.model_id,
            details=details or {},
        )
        return await self.audits.record(audit)
