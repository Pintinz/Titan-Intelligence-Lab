"""Freshness classification (spec §26 "Context Freshness") — a real CURRENT/STALE/UNKNOWN
3-state verdict derived from the SAME continuous freshness score every quality engine already
computes (`FeatureQualityEngine._freshness_score`, `IngestionDataQualityEngine`'s identical
decay formula) — not a new decay formula invented in parallel. "Stale" here means exactly what
those engines already mean by a decayed score, just exposed as the categorical verdict a caller
actually needs to render ("Availability data unavailable" vs. a raw number nobody asked for).
"""

from __future__ import annotations

from enum import Enum


class FreshnessStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


def classify_freshness(score: float | None) -> FreshnessStatus:
    """``score`` is the same 0-100 continuous freshness score every quality engine stores/exposes
    (100 while within TTL, decaying to 0 by the engine's own stale-at horizon). ``None`` — no
    observation exists at all — is UNKNOWN, never silently treated as CURRENT or STALE; anything
    below the perfect-freshness ceiling is STALE, matching how these engines already define
    "within TTL" as the only state that counts as genuinely current."""
    if score is None:
        return FreshnessStatus.UNKNOWN
    return FreshnessStatus.CURRENT if score >= 100.0 else FreshnessStatus.STALE
