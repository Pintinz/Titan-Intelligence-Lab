"""Mobile V1 monetization (spec: "TITANIQ MOBILE V1 — ADMOB REWARDED PREDICTION MONETIZATION").
Server-authoritative prediction credits: 5 free lifetime, +2 per verified AdMob rewarded-ad
completion, repeatable indefinitely. Every consume/grant goes through this one service — the
router, not any frontend button, is the single enforcement point (spec's own "ONE authoritative
backend credit check" requirement).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from modules.predictions.domain.entities import (
    INITIAL_FREE_PREDICTIONS,
    REWARDED_AD_CREDIT_GRANT,
    PredictionCredit,
    PredictionRewardEvent,
)
from modules.predictions.domain.value_objects import PredictionRewardEventId
from modules.predictions.ports.repositories import PredictionCreditRepositoryPort, PredictionRewardEventRepositoryPort


@dataclass
class PredictionCreditService:
    credits: PredictionCreditRepositoryPort
    reward_events: PredictionRewardEventRepositoryPort

    async def get_entitlement(self, user_id: UUID, now: datetime) -> PredictionCredit:
        """Lazily initializes a first-time user's balance to `INITIAL_FREE_PREDICTIONS` — reading
        entitlement is what a user does before ever generating anything, so this (not the
        generate endpoint) is the real "first eligible access" moment spec Phase 2 describes."""
        return await self.credits.get_or_initialize(user_id, INITIAL_FREE_PREDICTIONS, now)

    async def consume_for_generation(self, user_id: UUID, now: datetime) -> PredictionCredit:
        """Raises `PredictionCreditExhaustedError` when the user has 0 available predictions —
        callers must call this and let the exception propagate BEFORE attempting generation, in
        the same request-scoped transaction generation itself runs in. That's what makes "don't
        consume a credit for a failed generation" correct without any explicit refund logic here:
        `apps.api.composition.get_session()` only commits on a clean return; if generation then
        raises for any reason, the whole transaction — including this consume — rolls back
        automatically."""
        return await self.credits.consume(user_id, INITIAL_FREE_PREDICTIONS, now)

    async def grant_rewarded_ad(
        self,
        user_id: UUID,
        provider_event_id: str,
        now: datetime,
        provider: str = "admob",
        credits: int = REWARDED_AD_CREDIT_GRANT,
    ) -> tuple[PredictionCredit, bool]:
        """Returns `(credit, granted)`. `granted=False` for a duplicate `provider_event_id` — a
        replayed or duplicate-delivered callback — in which case `credit` is the user's current
        (unchanged) balance, never a fabricated "yes it worked" response."""
        event = PredictionRewardEvent(
            id=PredictionRewardEventId(uuid4()),
            user_id=user_id,
            provider=provider,
            reward_type="prediction_unlock",
            credits_granted=credits,
            provider_event_id=provider_event_id,
            status="granted",
            created_at=now,
        )
        _, created = await self.reward_events.record(event)
        if not created:
            current = await self.credits.get_or_initialize(user_id, INITIAL_FREE_PREDICTIONS, now)
            return current, False
        updated = await self.credits.grant(user_id, credits, INITIAL_FREE_PREDICTIONS, now)
        return updated, True
