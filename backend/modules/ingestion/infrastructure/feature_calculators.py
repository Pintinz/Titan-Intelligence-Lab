"""Real `FeatureCalculatorPort` implementations against Milestone 5's `FeaturePipeline`
(Milestone 9 task: "Milestone 6+ registers the first real calculators against this same
pipeline" — this is where that finally happens, for features computable from a single
``clean_record`` dict with no repository/historical lookup).

Each calculator below is parametrized rather than hardcoded to one feature — the same handful of
classes serve every sport and every odds/schedule-shaped record, consistent with the
"reusable computational strategy, not one class per feature" posture used throughout Milestone 9
(the `MarketKind` taxonomy, the two generic `PredictorPort` implementations). Every calculator
documents exactly which ``clean_record`` keys it reads; a record missing them returns ``None``
(skipped, not an error — `FeaturePipeline.run()`'s own documented contract).

Features needing a historical window (team form, head-to-head, rest days) can't be computed from
one record — those are `PredictionContextBuilder`-adjacent windowed feature engineering services
(Milestone 9 task #137), a different mechanism entirely, not this pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — applied
    defensively here too, since ``scheduled_at`` may have round-tripped through such a store
    before reaching this calculator."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


def _as_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


@dataclass
class ImpliedProbabilityCalculator:
    """Converts one outcome's decimal odds into an implied probability — a real, provider-
    supplied market signal that needs no history at all. Expects
    ``clean_record["odds"][odds_key]`` to be decimal odds > 1.0 (e.g. 2.5 for an even-money-ish
    outcome); returns ``1 / odds``.
    """

    feature_key: str
    odds_key: str

    async def compute(self, clean_record: dict, now: datetime) -> float | None:
        odds = _as_number(clean_record.get("odds", {}).get(self.odds_key))
        if odds is None or odds <= 1.0:
            return None
        return 1.0 / odds


@dataclass
class OddsOverroundCalculator:
    """Bookmaker overround (the "vig") across a set of mutually exclusive outcomes —
    ``sum(1/odds_i) - 1`` — a real measure of market efficiency/liquidity for this fixture's
    odds line. Expects every key in ``odds_keys`` to be present under
    ``clean_record["odds"]`` with decimal odds > 1.0; missing or invalid any one and it returns
    ``None`` rather than compute against a partial outcome set."""

    feature_key: str
    odds_keys: tuple[str, ...]

    async def compute(self, clean_record: dict, now: datetime) -> float | None:
        odds_map = clean_record.get("odds", {})
        values = [_as_number(odds_map.get(key)) for key in self.odds_keys]
        if any(value is None or value <= 1.0 for value in values):
            return None
        return sum(1.0 / value for value in values) - 1.0


@dataclass
class HoursUntilKickoffCalculator:
    """Hours between ``now`` and ``clean_record["scheduled_at"]`` — negative once the fixture
    has started. Accepts either a `datetime` or an ISO-8601 string (provider normalization may
    leave either, depending on which stage produced ``clean_record``)."""

    feature_key: str = "fixture.hours_until_kickoff"

    async def compute(self, clean_record: dict, now: datetime) -> float | None:
        scheduled_at = clean_record.get("scheduled_at")
        if isinstance(scheduled_at, str):
            try:
                scheduled_at = datetime.fromisoformat(scheduled_at)
            except ValueError:
                return None
        if not isinstance(scheduled_at, datetime):
            return None
        scheduled_at = _ensure_aware(scheduled_at, now)
        return (scheduled_at - now).total_seconds() / 3600.0


@dataclass
class AttendanceRatioCalculator:
    """Attendance as a fraction of venue capacity, capped at 1.0 — a real crowd-support proxy
    correlated with home-advantage magnitude. Expects numeric
    ``clean_record["attendance"]``/``clean_record["venue_capacity"]``; a non-positive or missing
    capacity returns ``None``."""

    feature_key: str = "fixture.attendance_ratio"

    async def compute(self, clean_record: dict, now: datetime) -> float | None:
        attendance = _as_number(clean_record.get("attendance"))
        capacity = _as_number(clean_record.get("venue_capacity"))
        if attendance is None or capacity is None or capacity <= 0:
            return None
        return min(attendance / capacity, 1.0)
