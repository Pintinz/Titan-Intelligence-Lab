"""Feature Calculator port (docs/roadmap.md Milestone 5 "Feature Pipeline Foundation").

Milestone 5 scope is the pipeline *architecture* only — "Do NOT implement sport-specific
engineered features yet." This Protocol is the plug point a real calculator (Milestone 6+)
implements; nothing implementing it exists yet.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class FeatureCalculatorPort(Protocol):
    feature_key: str

    async def compute(self, clean_record: dict, now: datetime) -> float | int | str | bool | None:
        """Returns the computed value, or None if it can't be computed from this record
        (e.g. missing an input the formula needs) — None is skipped, not an error."""
        ...
