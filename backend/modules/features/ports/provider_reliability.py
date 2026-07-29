"""Cross-module port: lets FeatureQualityEngine report "Provider Reliability" for a feature's
``source_provider_key`` without modules/features importing modules/admin directly. The
composition root wires the real implementation (backed by
modules.admin.application.health_intelligence_engine.HealthIntelligenceEngine) — see
docs/decisions.md ADR-016.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ProviderReliabilityPort(Protocol):
    async def reliability_score(self, provider_key: str, now: datetime) -> float | None: ...
