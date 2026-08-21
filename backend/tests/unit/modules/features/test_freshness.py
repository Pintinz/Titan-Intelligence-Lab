from __future__ import annotations

from modules.features.domain.freshness import FreshnessStatus, classify_freshness


def test_none_score_is_unknown():
    assert classify_freshness(None) is FreshnessStatus.UNKNOWN


def test_perfect_score_is_current():
    assert classify_freshness(100.0) is FreshnessStatus.CURRENT


def test_decayed_score_is_stale():
    assert classify_freshness(42.5) is FreshnessStatus.STALE


def test_zero_score_is_stale_not_unknown():
    """A real observation exists (a score of 0 was actually computed) — distinct from `None`
    (no observation exists at all), which is the only case that means UNKNOWN."""
    assert classify_freshness(0.0) is FreshnessStatus.STALE
