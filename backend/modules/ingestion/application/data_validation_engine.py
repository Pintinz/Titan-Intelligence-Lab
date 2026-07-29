"""Data Validation Engine (docs/roadmap.md Milestone 5). Validates normalized provider DTOs
*before* they reach a reconciler/repository — "reject invalid data before persistence."

Operates on `modules.sports.ports.provider_gateway` DTOs, not on domain entities: validation is
the gate between "provider said this" and "we persist this," so it belongs strictly before
reconciliation (docs/architecture.md §5 Provider Adapter Pattern).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from modules.sports.domain.value_objects import ProviderRef
from modules.sports.ports.provider_gateway import (
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderLineupRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
)

MIN_REASONABLE_BIRTH_YEAR = 1930
MAX_FIXTURE_DATE_SKEW = timedelta(days=3650)  # ~10 years either side — a sanity bound, not a business rule


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    issues: tuple[str, ...] = field(default_factory=tuple)

    @staticmethod
    def ok() -> "ValidationResult":
        return ValidationResult(is_valid=True)

    @staticmethod
    def failed(*issues: str) -> "ValidationResult":
        return ValidationResult(is_valid=False, issues=issues)


class DataValidationEngine:
    """Stateless — every method is a pure function of its input(s), so validation logic is
    trivially unit-testable without any repository or I/O dependency."""

    # -- schema / required fields / invalid values ------------------------------------------

    def validate_country(self, record: ProviderCountryRecord) -> ValidationResult:
        issues = []
        if not record.code or len(record.code) != 2:
            issues.append(f"country code must be 2 letters, got {record.code!r}")
        if not record.name.strip():
            issues.append("country name is required")
        return ValidationResult.failed(*issues) if issues else ValidationResult.ok()

    def validate_team(self, record: ProviderTeamRecord) -> ValidationResult:
        issues = []
        if not record.name.strip():
            issues.append("team name is required")
        if not record.short_name.strip():
            issues.append("team short_name is required")
        if not record.external_ref.external_id:
            issues.append("team external_ref.external_id is required")
        return ValidationResult.failed(*issues) if issues else ValidationResult.ok()

    def validate_player(self, record: ProviderPlayerRecord, now: datetime) -> ValidationResult:
        issues = []
        if not record.name.strip():
            issues.append("player name is required")
        if record.date_of_birth is not None:
            if record.date_of_birth > now:
                issues.append(f"date_of_birth {record.date_of_birth} is in the future")
            elif record.date_of_birth.year < MIN_REASONABLE_BIRTH_YEAR:
                issues.append(f"date_of_birth year {record.date_of_birth.year} predates {MIN_REASONABLE_BIRTH_YEAR}")
        return ValidationResult.failed(*issues) if issues else ValidationResult.ok()

    def validate_fixture(self, record: ProviderFixtureRecord, now: datetime) -> ValidationResult:
        issues = []
        if record.home_team_ref == record.away_team_ref:
            issues.append("home_team_ref and away_team_ref must differ (relationship consistency)")
        if not record.competition_ref.strip():
            issues.append("competition_ref is required (competition consistency)")
        if not record.season_label.strip():
            issues.append("season_label is required (season consistency)")
        if abs(record.scheduled_at - now) > MAX_FIXTURE_DATE_SKEW:
            issues.append(f"scheduled_at {record.scheduled_at} is implausibly far from now (date consistency)")
        for ref, label in ((record.home_team_ref, "home_team_ref"), (record.away_team_ref, "away_team_ref")):
            if ref.provider != record.external_ref.provider:
                issues.append(f"{label} provider {ref.provider!r} does not match fixture provider {record.external_ref.provider!r} (provider integrity)")
        return ValidationResult.failed(*issues) if issues else ValidationResult.ok()

    def validate_standing(self, record: ProviderStandingRecord) -> ValidationResult:
        issues = []
        if record.rank < 1:
            issues.append(f"rank must be >= 1, got {record.rank}")
        if record.points < 0:
            issues.append(f"points must be >= 0, got {record.points}")
        return ValidationResult.failed(*issues) if issues else ValidationResult.ok()

    def validate_team_statistics(self, record: ProviderTeamStatisticsRecord) -> ValidationResult:
        if not record.stat_set:
            return ValidationResult.failed("stat_set is empty (missing values)")
        return ValidationResult.ok()

    def validate_lineup(self, record: ProviderLineupRecord) -> ValidationResult:
        issues = []
        if not record.slots:
            issues.append("lineup has no slots (missing values)")
        for slot in record.slots:
            if slot.role not in ("starter", "substitute"):
                issues.append(f"unrecognized lineup role {slot.role!r} (invalid values)")
        return ValidationResult.failed(*issues) if issues else ValidationResult.ok()

    # -- batch-level: duplicates ----------------------------------------------------------------

    def find_duplicate_refs(self, refs: list[ProviderRef]) -> list[str]:
        """Duplicate external_refs within a single fetch batch — a provider integrity signal
        distinct from per-record validation, since it only makes sense across the whole batch."""
        seen: dict[ProviderRef, int] = {}
        for ref in refs:
            seen[ref] = seen.get(ref, 0) + 1
        return [f"duplicate provider ref {ref.provider}:{ref.external_id} appears {count} times" for ref, count in seen.items() if count > 1]
