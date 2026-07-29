"""Statistic schema contract — validates the shape of the sport-specific JSONB payloads in
``team_statistics.stat_set`` / ``player_statistics.stat_set`` (docs/database_schema.md §2)
without requiring a single relational column set across all sports.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatisticFieldSpec:
    key: str
    data_type: type
    required: bool = True


@dataclass(frozen=True)
class StatisticSchema:
    """A closed set of fields a sport plugin expects in a statistics payload."""

    fields: tuple[StatisticFieldSpec, ...]

    def validate(self, payload: dict) -> list[str]:
        """Returns a list of human-readable errors; empty list means valid."""
        errors: list[str] = []
        known_keys = {f.key for f in self.fields}

        for spec in self.fields:
            if spec.key not in payload:
                if spec.required:
                    errors.append(f"missing required field '{spec.key}'")
                continue
            value = payload[spec.key]
            if value is not None and not isinstance(value, spec.data_type):
                errors.append(
                    f"field '{spec.key}' expected {spec.data_type.__name__}, "
                    f"got {type(value).__name__}"
                )

        for key in payload:
            if key not in known_keys:
                errors.append(f"unrecognized field '{key}'")

        return errors
