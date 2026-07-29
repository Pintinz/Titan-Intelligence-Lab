"""Batch + Async Prediction (Milestone 9.1 Model Serving). Realtime single-subject prediction
already exists (`PredictionCacheService.get_or_generate()`, Milestone 9) — these two services
compose it rather than reimplement generation:

- `BatchPredictionService.generate_batch()` is a thin `asyncio.gather` fan-out over
  `get_or_generate()` for many subjects at once — one bad request returns as an `Exception` object
  in that position rather than failing the whole batch.
- `AsyncPredictionQueueService` is a Prediction Queue: `enqueue()` records a request and returns a
  request id immediately; `process_next()` is the worker-side call that actually runs generation
  (in production this body is a Celery task, reusing Milestone 5's queue infrastructure — same
  adapter-swap posture as every other capability port, docs/decisions.md ADR-008) — swappable
  without this service's public shape (`enqueue`/`poll`) changing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from modules.features.domain.value_objects import EntityType
from modules.predictions.application.prediction_cache_service import PredictionCacheService
from modules.predictions.domain.entities import Prediction


class RequestNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class PredictionRequest:
    request_id: str
    market_key: str
    entity_type: EntityType
    entity_id: str
    subject_ref: str
    requested_at: datetime


@dataclass
class BatchPredictionService:
    cache_service: PredictionCacheService

    async def generate_batch(
        self, requests: list[tuple[str, EntityType, str, str]], now: datetime
    ) -> list[Prediction | Exception]:
        async def _one(market_key: str, entity_type: EntityType, entity_id: str, subject_ref: str):
            try:
                return await self.cache_service.get_or_generate(market_key, entity_type, entity_id, subject_ref, now)
            except Exception as exc:  # noqa: BLE001 — one bad request must not fail the whole batch
                return exc

        return list(await asyncio.gather(*(_one(*request) for request in requests)))


@dataclass
class AsyncPredictionQueueService:
    """A process-wide singleton (its pending/results state must outlive any single HTTP
    request). ``cache_service`` is deliberately NOT stored here: it holds a
    `PredictionCacheService` built on an `AsyncSession` that is itself request-scoped, so
    `process_next()` takes a fresh one per call instead — the queue's own state (this class)
    stays alive across requests; the database session it uses to actually run generation does not
    (docs/decisions.md ADR-007-adjacent session-lifecycle discipline)."""

    _pending: dict = field(default_factory=dict)  # request_id -> PredictionRequest, FIFO by insertion
    _results: dict = field(default_factory=dict)  # request_id -> Prediction | Exception

    def enqueue(self, market_key: str, entity_type: EntityType, entity_id: str, subject_ref: str, now: datetime) -> str:
        request_id = str(uuid4())
        self._pending[request_id] = PredictionRequest(request_id, market_key, entity_type, entity_id, subject_ref, now)
        return request_id

    async def process_next(self, cache_service: PredictionCacheService, now: datetime) -> str | None:
        """Dequeues and runs exactly one pending request — returns its request id, or ``None`` if
        the queue is empty. Called repeatedly by a worker loop (or once per Celery task
        invocation in production), each time with a freshly-built ``cache_service``."""
        if not self._pending:
            return None

        request_id, request = next(iter(self._pending.items()))
        del self._pending[request_id]

        try:
            result = await cache_service.get_or_generate(
                request.market_key, request.entity_type, request.entity_id, request.subject_ref, now
            )
        except Exception as exc:  # noqa: BLE001 — the caller polls for either a Prediction or this Exception
            result = exc

        self._results[request_id] = result
        return request_id

    def poll(self, request_id: str) -> Prediction | Exception | None:
        """Returns ``None`` while still queued, the `Prediction` (or `Exception`) once
        `process_next()` has handled it, or raises if ``request_id`` was never enqueued."""
        if request_id in self._pending:
            return None
        if request_id not in self._results:
            raise RequestNotFoundError(request_id)
        return self._results[request_id]

    def pending_count(self) -> int:
        return len(self._pending)
