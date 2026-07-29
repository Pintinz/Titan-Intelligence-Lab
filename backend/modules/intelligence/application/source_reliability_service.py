"""Source Reliability Engine (Milestone 8 "SOURCE RELIABILITY ENGINE": "Every source shall
receive: Reliability Score, Historical Accuracy, Bias Rating, Verification Status, Trust Level,
Publisher Metadata, Official / Unofficial classification. Prediction models shall consume
source reliability as a feature.").

Publisher Metadata and Official/Unofficial classification already live on `NewsSource` itself
(`publisher_metadata`, `is_official`) — this service owns the four scores that change over time
as a source's track record accumulates. Feeding the result into the Feature Store as a
prediction-model input is `FeatureStoreEnrichmentService`'s job (Milestone 8); this service only
computes and persists the score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.intelligence.domain.entities import NewsSource, SourceReliabilityScore
from modules.intelligence.domain.value_objects import SourceReliabilityId, TrustLevel, VerificationStatus
from modules.intelligence.ports.repositories import SourceReliabilityRepositoryPort

_DEFAULT_RELIABILITY = 0.5
_DEFAULT_ACCURACY = 0.5
_EWMA_ALPHA = 0.2  # weight given to each new outcome — reactive to recent behavior, not a single event


@dataclass
class SourceReliabilityService:
    reliability: SourceReliabilityRepositoryPort

    async def get_or_initialize(self, source: NewsSource, now: datetime) -> SourceReliabilityScore:
        existing = await self.reliability.get_for_source(source.id)
        if existing is not None:
            return existing
        score = SourceReliabilityScore(
            id=SourceReliabilityId(uuid4()),
            source_id=source.id,
            reliability_score=_DEFAULT_RELIABILITY,
            historical_accuracy=_DEFAULT_ACCURACY,
            bias_rating=0.0,
            verification_status=VerificationStatus.VERIFIED if source.is_official else VerificationStatus.UNVERIFIED,
            trust_level=self._classify_trust(source.is_official, _DEFAULT_RELIABILITY),
            updated_at=now,
        )
        return await self.reliability.upsert(score)

    async def record_outcome(self, source: NewsSource, was_accurate: bool, now: datetime) -> SourceReliabilityScore:
        """Nudges reliability/historical accuracy via an exponentially-weighted moving average
        toward the latest observed outcome (was a claim this source reported later confirmed or
        refuted) — a source's score tracks recent behavior more than any single stale data
        point, without discarding history entirely on one event."""
        existing = await self.get_or_initialize(source, now)
        outcome = 1.0 if was_accurate else 0.0
        new_reliability = existing.reliability_score + _EWMA_ALPHA * (outcome - existing.reliability_score)
        new_accuracy = existing.historical_accuracy + _EWMA_ALPHA * (outcome - existing.historical_accuracy)
        updated = SourceReliabilityScore(
            id=existing.id,
            source_id=source.id,
            reliability_score=new_reliability,
            historical_accuracy=new_accuracy,
            bias_rating=existing.bias_rating,
            verification_status=existing.verification_status,
            trust_level=self._classify_trust(source.is_official, new_reliability),
            updated_at=now,
        )
        return await self.reliability.upsert(updated)

    async def set_bias_rating(self, source: NewsSource, bias_rating: float, now: datetime) -> SourceReliabilityScore:
        existing = await self.get_or_initialize(source, now)
        updated = SourceReliabilityScore(
            id=existing.id,
            source_id=source.id,
            reliability_score=existing.reliability_score,
            historical_accuracy=existing.historical_accuracy,
            bias_rating=max(-1.0, min(1.0, bias_rating)),
            verification_status=existing.verification_status,
            trust_level=existing.trust_level,
            updated_at=now,
        )
        return await self.reliability.upsert(updated)

    def _classify_trust(self, is_official: bool, reliability_score: float) -> TrustLevel:
        """"Official" is a structural fact (Official/Unofficial classification), not something
        earned over time, so an official source starts at ``OFFICIAL`` trust immediately —
        but a track record that craters (below 0.2) still demotes it, so persistently wrong
        "official" sources don't keep top trust forever."""
        if is_official and reliability_score >= 0.2:
            return TrustLevel.OFFICIAL
        if reliability_score >= 0.7:
            return TrustLevel.VERIFIED
        if reliability_score >= 0.3:
            return TrustLevel.UNVERIFIED
        return TrustLevel.UNRELIABLE
