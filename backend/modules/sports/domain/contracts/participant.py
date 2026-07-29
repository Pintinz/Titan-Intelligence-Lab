"""Roster contracts — how many people of what role a team fields for a sport."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RosterRules:
    """Bounds a sport plugin declares for squad composition.

    ``min_on_field`` / ``max_on_field`` describe active participants during play (e.g. 11 for
    football, 5 for basketball, 9 batting for baseball, 1 or 2 for table tennis singles/doubles).
    ``squad_size_max`` bounds the full registered roster available for selection, when the
    sport/competition enforces one (``None`` if unbounded).
    """

    min_on_field: int
    max_on_field: int
    squad_size_max: int | None = None

    def __post_init__(self) -> None:
        if self.min_on_field <= 0 or self.max_on_field <= 0:
            raise ValueError("on-field participant counts must be positive")
        if self.min_on_field > self.max_on_field:
            raise ValueError("min_on_field cannot exceed max_on_field")
